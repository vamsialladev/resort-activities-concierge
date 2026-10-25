"""The database, the synthetic schedule, and the five tools (no model)."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from concierge import config, db, retrieval, seed, tools
from concierge.db import activities, booking_requests, stays
from tests.conftest import TODAY


def test_schedule_fills_14_days_once_and_follows_weekdays(engine):
    with engine.connect() as conn:
        days = conn.execute(select(func.count(func.distinct(activities.c.date)))).scalar_one()
        monday_cruise = conn.execute(select(activities).where(activities.c.id == "BR-20261102-cruise")).first()
        tuesday_cruise = conn.execute(select(activities).where(activities.c.id == "BR-20261103-cruise")).first()
    assert days == 14 and monday_cruise is None and tuesday_cruise is not None
    assert seed.ensure_window(engine, TODAY) == 0  # idempotent
    assert seed.ensure_window(engine, date(2026, 11, 3)) > 0  # a new day rolls in


def test_fullness_is_stable_and_within_capacity():
    assert seed.fullness("BR-20261103-kids", 20) == seed.fullness("BR-20261103-kids", 20)
    assert all(0 < seed.fullness(f"x{i}", 10) <= 10 for i in range(200))


def test_stays_are_redated_around_today(engine):
    seed.ensure_window(engine, date(2026, 12, 1))
    with engine.connect() as conn:
        row = conn.execute(select(stays).where(stays.c.ref == "BR-4821")).first()
    assert row.check_in == "2026-11-30" and row.check_out == "2026-12-05"


def test_connect_retries_while_the_database_wakes_up():
    class Flaky:
        def __init__(self, fails):
            self.fails = fails

        def connect(self):
            if self.fails:
                self.fails -= 1
                raise OperationalError("SELECT 1", {}, Exception("asleep"))
            return "conn"

    slept = []
    assert db.connect(Flaky(2), sleep=slept.append) == "conn" and slept == [1, 2]
    with pytest.raises(db.WakingUp):
        db.connect(Flaky(9), attempts=3, sleep=slept.append)


def test_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db?sslmode=require")
    assert config.database_url() == "postgresql+psycopg://u:p@host/db?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", "")
    assert config.database_url().startswith("sqlite:///")


def test_search_activities_filters(tctx):
    out = tools.search_activities(tctx(), "tomorrow", "kids", "morning", "any")
    names = [a["name"] for a in out["activities"]]
    assert out["date"] == "2026-11-03" and names == [
        "Turtle talk with the marine team",
        "Kids club: sandcastle morning",
    ]
    kids = out["activities"][1]
    assert kids["ages"] == "4-11" and kids["start"] == "09:30" and kids["spots_left"] > 0
    indoor = tools.search_activities(tctx(), "today", "adults", "afternoon", "indoor")["activities"]
    assert {a["name"] for a in indoor} == {"Spa: aromatherapy massage", "Afternoon high tea"}
    assert all(a["date"] == "2026-11-02" for a in tools.search_activities(tctx("mountain-lodge"))["activities"])


def test_search_activities_rejects_bad_dates(tctx):
    for bad in ("2026-10-01", "next year", "2027-01-01"):
        assert "error" in tools.call(tctx(), "search_activities", {"date": bad})


def test_availability_and_other_property(tctx):
    out = tools.check_availability(tctx(), "BR-20261103-kids", 2)
    assert out["available"] and out["price_total_usd"] == 0.0
    assert (
        "not found"
        in tools.call(
            tctx("mountain-lodge"), "check_availability", {"activity_id": "BR-20261103-kids", "party_size": 2}
        )["error"]
    )
    assert (
        "between 1 and 20"
        in tools.call(tctx(), "check_availability", {"activity_id": "BR-20261103-kids", "party_size": 0})["error"]
    )


def test_guest_booking_needs_the_last_name_and_the_property(tctx):
    assert tools.get_guest_booking(tctx(), "br-4821", "rivera")["room"] == "214"
    for args in ({"ref": "BR-4821", "last_name": "Smith"}, {"ref": "BR-9999", "last_name": "Rivera"}):
        assert "no stay found" in tools.call(tctx(), "get_guest_booking", args)["error"]
    assert "error" in tools.call(tctx("mountain-lodge"), "get_guest_booking", {"ref": "BR-4821", "last_name": "Rivera"})
    assert "last_name" not in tools.get_guest_booking(tctx(), "BR-4821", "Rivera")


@pytest.mark.parametrize(
    "message",
    ["What can we do tomorrow?", "No, not yet", "Please tell me about the spa", "wait, what does it cost?"],
)
def test_a_request_needs_the_guests_own_yes(tctx, message):
    args = {"activity_id": "BR-20261103-kids", "party_size": 2, "guest_confirmed": True, "stay_ref": "", "note": ""}
    assert "ask the guest to confirm first" in tools.call(tctx(last=message), "create_booking_request", args)["error"]


def test_a_confirmed_request_is_pending_and_never_booked(tctx, engine):
    args = {"activity_id": "BR-20261103-kids", "party_size": 2, "guest_confirmed": True, "stay_ref": "not provided"}
    out = tools.create_booking_request(tctx(last="Yes, please book it", conversation_id="c1"), **args, note="")
    assert out["status"] == "PENDING" and out["request_id"].startswith("REQ-")
    with engine.connect() as conn:
        req = conn.execute(select(booking_requests)).first()
        booked = conn.execute(select(activities.c.booked).where(activities.c.id == "BR-20261103-kids")).scalar_one()
    assert req.status == "PENDING" and req.stay_ref is None and req.conversation_id == "c1"
    assert booked == seed.fullness("BR-20261103-kids", 20)  # unchanged until staff approve
    unconfirmed = dict(args, guest_confirmed=False)
    assert "error" in tools.call(tctx(last="yes"), "create_booking_request", unconfirmed)


def test_a_request_cant_exceed_the_places_left(tctx):
    left = tools.check_availability(tctx(), "BR-20261102-spa", 1)["spots_left"]
    args = {
        "activity_id": "BR-20261102-spa",
        "party_size": left + 1,
        "guest_confirmed": True,
        "stay_ref": "",
        "note": "",
    }
    assert "places left" in tools.call(tctx(last="yes"), "create_booking_request", args)["error"]


def test_yes_detection():
    yes = ["yes", "Yes please", "sure, book it", "Sí, por favor", "request it please", "sounds good", "go ahead"]
    no = ["no thanks", "not yet", "Please tell me about the spa", "what time?", "don't book it", "yes... no wait"]
    assert all(tools.guest_said_yes(m) for m in yes) and not any(tools.guest_said_yes(m) for m in no)


def test_faq_search_is_property_filtered_and_strips_planted_instructions(tctx):
    out = tools.search_faq(tctx(), "spa staff notes towels")
    assert out["instructions_removed"] == 1
    assert all("SYSTEM NOTICE" not in p["text"] and "free this week" not in p["text"] for p in out["passages"])
    ml = tools.search_faq(tctx("mountain-lodge"), "kids club ages")["passages"]
    assert ml and all(p["property"] in ("mountain-lodge", "shared") for p in ml)
    assert ml[0]["cite_as"] == "Kids Club Policy - Mountain Lodge > Ages and supervision"
    assert "error" in tools.call(tctx(), "search_faq", {"query": "  "})


def test_hybrid_fuses_two_rankings_with_rrf():
    import numpy as np

    passages = retrieval.load()

    class Fake:
        def embed(self, texts):
            v = np.array([[1.0 if "cruise" in t.lower() else 0.0, 1.0] for t in texts])
            return v / np.linalg.norm(v, axis=1, keepdims=True)

    ix = retrieval.Index(passages, mode="hybrid", embedder=Fake())
    hits = ix.search("boat trip at sunset", "beach-resort", k=3)
    assert hits[0].section == "Sunset cruise"


def test_unknown_tool_and_bad_arguments(tctx):
    assert tools.call(tctx(), "search_faq", {"nope": 1}) == {"error": "invalid call to search_faq"}
    assert tools.call(tctx(), "delete_everything", {}) == {"error": "invalid call to delete_everything"}
