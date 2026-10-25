"""Every page runs for real (Streamlit AppTest) on a temporary database, with the agent's model replaced."""

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from concierge import agent, chats, config, staff, tools
from tests.conftest import TODAY

ROOT = config.ROOT


def fake_respond(message, ctx, history=None, client=None, on_step=None, turn=None, room=""):
    step = agent.Step("Tool: search_activities", {"date": "tomorrow"}, {"activities": ["09:30 Kids club"]})
    turn.steps.append(step)
    if on_step:
        on_step(step)
    turn.activities_seen.append("Kids club: sandcastle morning")
    turn.sources.append("Kids Club Policy - Beach Resort > Ages and supervision")
    if tools.guest_said_yes(message):
        args = {"activity_id": "BR-20261103-kids", "party_size": 2, "guest_confirmed": True, "stay_ref": "", "note": ""}
        ctx.last_user_message = message
        turn.requests.append(tools.create_booking_request(ctx, **args)["request_id"])
    turn.usage = {"input_tokens": 10, "output_tokens": 5, "calls": 2}
    turn.answer = f"Kids club at 09:30 ({len(history or [])} earlier turns)."
    yield turn.answer


@pytest.fixture
def app(engine, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setattr(agent, "respond", fake_respond)

    def make(page=None, **query):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        for k, v in query.items():
            at.query_params[k] = v
        at.run()
        if page:
            at.switch_page(page).run()
        return at

    yield make
    st.cache_resource.clear()


def test_schedule_with_filters_and_qr_context(app):
    at = app(property="mountain-lodge", room="12")
    assert not at.exception
    assert "Mountain Lodge" in at.title[0].value
    assert any("Room 12" in c.value for c in at.sidebar.caption)
    assert any("Guided morning trek" in m.value for m in at.markdown)
    at.toggle[0].set_value(True).run()
    assert not any("Yoga in the loft" in m.value for m in at.markdown)  # ages 12+ hidden for kids
    assert any("Kids club: nature explorers" in m.value for m in at.markdown)


def test_finished_sessions_and_the_next_hour_banner(app):
    at = app()
    assert any("Starting in the next hour" in i.value and "Turtle talk" in i.value for i in at.info)
    yoga = next(b for b in at.button if b.key == "a-BR-20261102-yoga")
    assert yoga.disabled  # 07:00-08:00 is over at 08:15


def test_concierge_saves_reopens_and_shares(app, engine):
    at = app("pages/concierge.py")
    at.chat_input[0].set_value("What can we do tomorrow morning?").run()
    assert not at.exception
    assert any("Kids club at 09:30 (0 earlier turns)" in m.value for m in at.markdown)
    assert any(e.label.startswith("Steps: 1") for e in at.expander)
    assert any("Sources searched" in c.value for c in at.caption)
    visitor = at.session_state["visitor"]
    assert at.query_params["v"] == [visitor] or at.query_params["v"] == visitor
    at.chat_input[0].set_value("Yes please").run()
    assert any("PENDING until staff approve it" in c.value for c in at.caption)
    assert any("(1 earlier turns)" in m.value for m in at.markdown)
    (conv,) = chats.list_for(engine, visitor)
    next(b for b in at.button if b.label == "Share this conversation").click().run()
    url = next(c.value for c in at.code if "?share=" in c.value)
    shared = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    shared.query_params["share"] = url.split("?share=", 1)[1]
    shared.run()
    assert "shared conversation" in shared.title[0].value and not shared.chat_input
    # a new visit with the same address finds the conversation again
    again = app("pages/concierge.py", v=visitor)
    next(b for b in again.sidebar.button if conv["title"] in b.label).click().run()
    assert any("(1 earlier turns)" in m.value for m in again.markdown)


def test_staff_is_locked_without_a_password(app):
    at = app("pages/staff.py")
    assert any("isn't set up" in i.value for i in at.info)


def test_staff_sign_in_approve_and_guest_sees_it_once(app, engine, monkeypatch):
    monkeypatch.setattr(config, "staff_password", lambda: "test-only-password")
    guest = app("pages/concierge.py")
    guest.chat_input[0].set_value("Yes please").run()
    at = app("pages/staff.py")
    at.text_input[0].input("wrong")
    at.button[0].click().run()  # a form sends its values with the submit
    assert any("didn't work" in e.value for e in at.error)
    at.text_input[0].input("test-only-password")
    at.button[0].click().run()
    assert any("Kids club: sandcastle morning" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not staff.requests(engine)
    guest.run()
    notices = [s for s in guest.success if "approved" in s.value]
    assert len(notices) == 1
    at.tabs[1].run()
    assert any("Top questions" in h.value for h in at.subheader)


def test_about_and_damaged_share_link(app):
    at = app("pages/about.py")
    assert any("BR-4821" in m.value for m in at.markdown)
    bad = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    bad.query_params["share"] = "nope"
    bad.run()
    assert any("damaged" in w.value for w in bad.warning)


def test_the_eval_date_is_pinned():
    assert config.today() == TODAY
