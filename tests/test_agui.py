"""A run's AG-UI events: order, validity against the official types, and the timeline rebuilt from them."""

from ag_ui.core import Event
from pydantic import TypeAdapter

from concierge import agui

EVENT = TypeAdapter(Event)


def a_run():
    ev = agui.RunEvents("thread1", "run1")
    ev.run_started("What can the kids do tomorrow?")
    ev.step("rewrite_follow_up", 1000, {"standalone": "Kids activities tomorrow"})
    ev.text("Let me check. ")
    ev.text_end()  # the agent closes a turn's text before its tool calls
    ev.tool("search_activities", {"date": "tomorrow"}, {"activities": ["09:30 Kids club"]}, 1000)
    ev.custom(agui.APPROVAL_REQUESTED, {"mandate_id": "PM-1", "total_usd": 120.0})
    ev.text("Kids club is at 09:30.")
    ev.text_end()
    ev.state({"requests": [], "sources": [], "stop": "end_turn"})
    ev.finished({"answer_chars": 22})
    return ev.events


def test_event_order_and_every_event_is_a_valid_ag_ui_event():
    events = a_run()
    kinds = [e["type"] for e in events]
    assert kinds[0] == "RUN_STARTED" and kinds[-1] == "RUN_FINISHED" and kinds[-2] == "STATE_SNAPSHOT"
    assert kinds.index("TOOL_CALL_START") < kinds.index("TOOL_CALL_ARGS") < kinds.index("TOOL_CALL_END")
    assert kinds.index("TOOL_CALL_END") < kinds.index("TOOL_CALL_RESULT")
    assert kinds.count("TEXT_MESSAGE_START") == kinds.count("TEXT_MESSAGE_END") == 2  # one per turn, each closed
    for e in events:
        EVENT.validate_python(e)  # the stored camelCase JSON parses back into the official types


def test_the_timeline_comes_back_from_the_events_alone():
    steps = agui.timeline(a_run())
    assert [s["name"] for s in steps] == [
        "Rewrite follow up",
        "Tool: search_activities",
        "Waiting for the guest to approve the payment (sandbox)",
    ]
    assert steps[1]["input"] == {"date": "tomorrow"} and steps[1]["result"] == {"activities": ["09:30 Kids club"]}


def test_an_error_closes_the_open_message():
    ev = agui.RunEvents()
    ev.run_started("hi")
    ev.text("Partial")
    ev.error("model timed out")
    assert [e["type"] for e in ev.events][-2:] == ["TEXT_MESSAGE_END", "RUN_ERROR"]


def test_decisions_after_the_run_are_custom_events():
    e = agui.custom_event(agui.STAFF_DECISION, {"request_id": "REQ-1", "status": "APPROVED"})
    assert e["type"] == "CUSTOM" and e["name"] == "staff_decision"
    EVENT.validate_python(e)


def test_the_real_agent_loop_emits_a_closed_message_before_the_final_state(tctx):
    from concierge import agent
    from tests.fakes import FakeModel, text, tool

    model = FakeModel(tool("search_faq", {"query": "spa"}), text("The spa opens at 09:00."))
    turn = agent.run("When does the spa open?", tctx(), [], model)
    kinds = [e["type"] for e in turn.agui.events]
    assert kinds[-3:] == ["TEXT_MESSAGE_END", "STATE_SNAPSHOT", "RUN_FINISHED"]
    assert kinds.count("TEXT_MESSAGE_START") == kinds.count("TEXT_MESSAGE_END")
    for e in turn.agui.events:
        EVENT.validate_python(e)
