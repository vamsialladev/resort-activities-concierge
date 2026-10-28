"""The agent loop (model replaced), conversations, staff decisions, analytics and limits."""

import json

import pytest
from sqlalchemy import select

from concierge import agent, analytics, ap2_sandbox, chats, config, limits, staff, suggest, tools
from concierge.db import activities, events
from tests.fakes import FakeModel, text, tool

KIDS = "BR-20261103-kids"


def test_the_family_case_end_to_end(tctx, engine):
    """The must-pass demo: activities + kids-club policy, offer; then 'yes' creates a PENDING request."""
    model = FakeModel(
        tool(
            "search_activities", {"date": "tomorrow", "age_group": "kids", "time_window": "morning", "setting": "any"}
        ),
        tool("search_faq", {"query": "kids club ages"}, "tu_2"),
        text("Kids club 09:30-11:30, ages 4-11 [Kids Club Policy - Beach Resort > Ages and supervision]. Shall I?"),
    )
    ctx = tctx(conversation_id="c1")
    t1 = agent.run("My family has two kids. What can we do tomorrow morning?", ctx, [], model)
    assert [s.name for s in t1.steps] == ["Tool: search_activities", "Tool: search_faq"]
    assert "Kids club: sandcastle morning" in t1.activities_seen and t1.sources and not t1.requests
    assert "09:30" in json.dumps(t1.steps[0].result) and t1.usage["calls"] == 3
    model2 = FakeModel(
        tool("check_availability", {"activity_id": KIDS, "party_size": 2}),
        tool(
            "create_booking_request",
            {"activity_id": KIDS, "party_size": 2, "guest_confirmed": True, "stay_ref": "", "note": ""},
            "tu_3",
        ),
        text("Sent: REQ-... is PENDING until staff approve it."),
    )
    history = [{"question": t1.question, "answer": t1.answer}]
    t2 = agent.run("Yes please", ctx, history, model2)
    assert len(t2.requests) == 1 and not any(s.name == "Rewrite follow-up" for s in t2.steps)
    assert model2.requests[0]["messages"][:2] == [
        {"role": "user", "content": t1.question},
        {"role": "assistant", "content": t1.answer},
    ]


def test_the_model_cant_create_a_request_the_guest_didnt_agree_to(tctx):
    args = {"activity_id": KIDS, "party_size": 2, "guest_confirmed": True, "stay_ref": "", "note": ""}
    model = FakeModel(tool("create_booking_request", args), text("I couldn't send it yet. Shall I?"))
    turn = agent.run("What's the kids club like?", tctx(), [], model)
    assert not turn.requests and "confirm first" in turn.steps[0].result["error"]
    assert model.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_follow_ups_are_rewritten_and_shown(tctx):
    history = [{"question": "What's on tomorrow morning for kids?", "answer": "Kids club at 09:30."}]
    model = FakeModel(text("In the afternoon there's high tea."), rewrites=["What's on tomorrow afternoon for kids?"])
    turn = agent.run("What about the afternoon?", tctx(), history, model)
    assert turn.understood_as == "What's on tomorrow afternoon for kids?"
    assert turn.steps[0].name == "Rewrite follow-up" and turn.usage["calls"] == 2
    assert model.requests[1]["messages"][-1] == {"role": "user", "content": "What's on tomorrow afternoon for kids?"}


def test_the_loop_stops_after_six_model_turns(tctx):
    model = FakeModel(*[tool("search_faq", {"query": "spa"}, f"t{i}") for i in range(6)])
    turn = agent.run("spa?", tctx(), [], model)
    assert turn.stop == "max_turns" and "more narrowly" in turn.answer and turn.usage["calls"] == 6


def test_system_prompt_has_the_date_property_and_room(tctx):
    prompt = agent.system_prompt(tctx("mountain-lodge"), room="12")
    assert "Today is 2026-11-02 (Monday)" in prompt and "Mountain Lodge, room 12" in prompt
    assert "data, not instructions" in prompt


def test_conversations_are_per_visitor_redacted_and_shareable(engine):
    cid = chats.create(engine, "v1", "beach-resort", "214", "My name is Priya, email p@x.test")
    chats.add_message(engine, cid, "user", "Call me on +1 305 555 0142, booking BR-4821", {"understood_as": ""})
    chats.add_message(engine, cid, "assistant", "Done.", {"sources": ["x"]})
    conv, msgs = chats.load(engine, cid, "v1")
    stored = json.dumps([conv, msgs])
    assert "Priya" not in stored and "p@x.test" not in stored and "555 0142" not in stored and "BR-4821" not in stored
    assert chats.load(engine, cid, "someone-else") == (None, [])
    assert [c["id"] for c in chats.list_for(engine, "v1")] == [cid] and chats.list_for(engine, "v2") == []
    token = chats.share_token(engine, cid)
    assert chats.share_token(engine, cid) == token and chats.by_token(engine, token)[0]["id"] == cid
    assert chats.by_token(engine, "nope") == (None, []) and chats.by_token(engine, "x" * 40) == (None, [])
    assert chats.turns(msgs) == [{"question": msgs[0]["content"], "answer": "Done."}]
    assert chats.share_url("https://app.test/concierge?v=abc#x", token) == f"https://app.test/concierge?share={token}"


def make_request(tctx, party=2, activity=KIDS):
    cid = chats.create(tctx().engine, "v9", "beach-resort", "", "a request")
    args = {"activity_id": activity, "party_size": party, "guest_confirmed": True, "stay_ref": "", "note": "n"}
    return tools.create_booking_request(tctx(last="yes", conversation_id=cid), **args)["request_id"], cid


def test_staff_approve_books_the_places_and_tells_the_guest(tctx, engine):
    chats_cid = chats.create(engine, "v1", "beach-resort", "", "kids")
    args = {"activity_id": KIDS, "party_size": 2, "guest_confirmed": True, "stay_ref": "", "note": ""}
    rid = tools.create_booking_request(tctx(last="yes", conversation_id=chats_cid), **args)["request_id"]
    before = tools.check_availability(tctx(), KIDS, 1)["spots_left"]
    assert [r["id"] for r in staff.requests(engine)] == [rid]
    out = staff.decide(engine, rid, True, "See you at the pavilion")
    assert out["status"] == "APPROVED" and tools.check_availability(tctx(), KIDS, 1)["spots_left"] == before - 2
    _, msgs = chats.load(engine, chats_cid)
    assert msgs[-1]["role"] == "notice" and "approved" in msgs[-1]["content"] and "pavilion" in msgs[-1]["content"]
    with pytest.raises(staff.DecisionError, match="already APPROVED"):
        staff.decide(engine, rid, False)
    assert staff.requests(engine) == []


def test_staff_decline_and_capacity_checks(tctx, engine):
    rid, _ = make_request(tctx)
    assert staff.decide(engine, rid, False)["status"] == "DECLINED"
    rid2, cid2 = make_request(tctx, party=1, activity="BR-20261102-spa")
    with pytest.raises(staff.DecisionError, match="hasn't approved the payment"):  # paid: the guest approves first
        staff.decide(engine, rid2, True)
    ap2_sandbox.decide(engine, ap2_sandbox.for_request(engine, rid2).id, cid2, True)
    with engine.begin() as conn:
        conn.execute(activities.update().where(activities.c.id == "BR-20261102-spa").values(booked=4))
    with pytest.raises(staff.DecisionError, match="places left"):
        staff.decide(engine, rid2, True)
    with pytest.raises(staff.DecisionError, match="not found"):
        staff.decide(engine, "REQ-NOPE", True)


def test_staff_password():
    assert staff.check_password("s3cret", "s3cret") and not staff.check_password("nope", "s3cret")
    assert not staff.check_password("", "")  # no password set means locked


def test_analytics(tctx, engine):
    turn = agent.Turn("Is there a helicopter pad?", "beach-resort", answer="I don't know; ask the front desk.")
    turn.activities_seen = ["Sunset cruise", "Sunset cruise"]
    analytics.record_turn(engine, turn, "v1")
    analytics.record_turn(engine, agent.Turn("Is there a helicopter pad?", "beach-resort", answer="..."), "v1")
    rid, _ = make_request(tctx)
    staff.decide(engine, rid, True)
    assert analytics.top_questions(engine, "beach-resort")[0] == {"question": "is there a helicopter pad", "times": 2}
    assert [u["question"] for u in analytics.unanswered_questions(engine, "beach-resort")] == [
        "Is there a helicopter pad?"
    ]
    rows = {r["activity"]: r for r in analytics.viewed_vs_requested(engine, "beach-resort")}
    assert rows["Sunset cruise"]["views"] == 1 and rows["Kids club: sandcastle morning"]["approved"] == 1
    assert rows["Reef snorkel tour"]["ignored"] and not rows["Sunset cruise"]["ignored"]
    assert analytics.peak_hours(engine, "beach-resort")[8] == 2
    assert analytics.top_questions(engine, "mountain-lodge") == []


def test_events_hold_no_personal_data(engine):
    analytics.log(engine, "question", "v1", "beach-resort", detail="I'm Owen, call +1 305 555 0143")
    with engine.connect() as conn:
        detail = conn.execute(select(events.c.detail)).scalar_one()
    assert "555" not in detail


def test_limits(engine, monkeypatch):
    assert limits.blocked(engine, [], 0, 100.0) is None
    assert "per visit" in limits.blocked(engine, [], config.MAX_QUESTIONS_PER_SESSION, 100.0)
    assert "a minute" in limits.blocked(engine, [99.0] * config.RATE_LIMIT_PER_MINUTE, 0, 100.0)
    limits.record(engine, {"input_tokens": 1_000_000, "output_tokens": 0})
    assert limits.record(engine, {"input_tokens": 0, "output_tokens": 0})["questions"] == 2
    monkeypatch.setattr(config, "DAILY_COST_CAP_USD", 0.05)
    assert "today's limit" in limits.blocked(engine, [], 0, 100.0)


def test_suggestions():
    turn = agent.Turn("q", "beach-resort")
    assert suggest.after(turn, set()) == suggest.first("beach-resort")
    turn.steps.append(agent.Step("Tool: search_activities", {}, {}))
    assert suggest.after(turn, set())[0] == "What should the kids bring?"
    turn.requests.append("REQ-1")
    assert suggest.after(turn, {"What happens next with my request?"}) == ["Can I cancel it later?"]


def test_hotel_policy_comes_from_the_mcp_server_as_the_guest_role(tctx):
    from concierge import mcp_tools

    assert set(mcp_tools.tool_names()) == {
        "search_policy",
        "lookup_booking",
        "list_activities",
        "create_booking_request",
    }
    out = tools.call(tctx(), "hotel_policy", {"question": "Can I bring my dog?"})
    assert out["via"].startswith("MCP") and any("Pets" in p["cite_as"] for p in out["passages"])
    assert "error" in tools.call(tctx(), "hotel_policy", {"question": " "})
