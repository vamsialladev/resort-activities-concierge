"""The concierge's run as AG-UI events (official `ag-ui-protocol` types), and the step timeline rendered from them.

One guest message is one run on the conversation's thread:

    RUN_STARTED
      STEP_STARTED / STEP_FINISHED        "rewrite" (a follow-up turned into a standalone question)
      TEXT_MESSAGE_START / _CONTENT / _END the answer, streamed
      TOOL_CALL_START / _ARGS / _END      each tool the model calls
      TOOL_CALL_RESULT                    its structured result (the short summary the timeline shows)
      CUSTOM human_approval_requested     a paid request's payment waits for the guest (AP2 sandbox)
      STATE_SNAPSHOT                      requests sent and sources searched, at the end
    RUN_FINISHED (or RUN_ERROR)

Later, outside the run, the guest's and the staff's decisions are CUSTOM events too: human_approval_granted /
human_approval_declined (the guest, for a payment) and staff_decision (approve / decline a request).

The events are stored with the assistant message (JSON, camelCase like the wire format), and `timeline()` turns them
back into the steps the page shows, so what the page draws is exactly what an AG-UI client would receive.
"""

import json
import time
import uuid

from ag_ui.core import (
    CustomEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

APPROVAL_REQUESTED = "human_approval_requested"
APPROVAL_GRANTED = "human_approval_granted"
APPROVAL_DECLINED = "human_approval_declined"
STAFF_DECISION = "staff_decision"


def _ms() -> int:
    return int(time.time() * 1000)


class RunEvents:
    """Collects one run's events. `events` is the list of JSON-ready dicts (camelCase, as on the wire)."""

    def __init__(self, thread_id: str | None = None, run_id: str | None = None):
        self.thread_id = thread_id or uuid.uuid4().hex[:12]
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.events: list[dict] = []
        self._message_id: str | None = None

    def _add(self, event) -> None:
        self.events.append(json.loads(event.model_dump_json(by_alias=True, exclude_none=True)))

    def run_started(self, message: str) -> None:
        self._add(RunStartedEvent(thread_id=self.thread_id, run_id=self.run_id, timestamp=_ms(),
                                  metadata={"message": message[:500]}))  # fmt: skip

    def step(self, name: str, started_ms: int, result: dict | None = None) -> None:
        self._add(StepStartedEvent(step_name=name, timestamp=started_ms))
        self._add(StepFinishedEvent(step_name=name, timestamp=_ms(), metadata={"result": result or {}}))

    def text(self, delta: str) -> None:
        if not delta:
            return
        if self._message_id is None:
            self._message_id = uuid.uuid4().hex[:12]
            self._add(TextMessageStartEvent(message_id=self._message_id, role="assistant", timestamp=_ms()))
        self._add(TextMessageContentEvent(message_id=self._message_id, delta=delta))

    def text_end(self) -> None:
        if self._message_id is not None:
            self._add(TextMessageEndEvent(message_id=self._message_id, timestamp=_ms()))
            self._message_id = None

    def tool(self, name: str, args: dict, result: dict, started_ms: int) -> None:
        call_id = uuid.uuid4().hex[:12]
        self._add(ToolCallStartEvent(tool_call_id=call_id, tool_call_name=name, timestamp=started_ms))
        self._add(ToolCallArgsEvent(tool_call_id=call_id, delta=json.dumps(args, default=str)))
        self._add(ToolCallEndEvent(tool_call_id=call_id, timestamp=_ms()))
        self._add(ToolCallResultEvent(message_id=uuid.uuid4().hex[:12], tool_call_id=call_id,
                                      content=json.dumps(result, default=str)[:4000], role="tool"))  # fmt: skip

    def custom(self, name: str, value: dict) -> None:
        self._add(CustomEvent(name=name, value=value, timestamp=_ms()))

    def state(self, snapshot: dict) -> None:
        self._add(StateSnapshotEvent(snapshot=snapshot, timestamp=_ms()))

    def finished(self, result: dict | None = None) -> None:
        self.text_end()
        self._add(RunFinishedEvent(thread_id=self.thread_id, run_id=self.run_id, timestamp=_ms(), result=result))

    def error(self, message: str) -> None:
        self.text_end()
        self._add(RunErrorEvent(message=message[:300], timestamp=_ms()))


def custom_event(name: str, value: dict) -> dict:
    """A standalone CUSTOM event (a decision made after the run), JSON-ready."""
    return json.loads(CustomEvent(name=name, value=value, timestamp=_ms()).model_dump_json(by_alias=True))


def timeline(events: list[dict]) -> list[dict]:
    """The step timeline the page shows, rebuilt from the events alone: [{name, input, result, seconds}]."""
    steps, starts, calls = [], {}, {}
    for e in events:
        kind = e.get("type")
        if kind == "STEP_STARTED":
            starts[e["stepName"]] = e.get("timestamp", 0)
        elif kind == "STEP_FINISHED":
            began = starts.pop(e["stepName"], e.get("timestamp", 0))
            steps.append({"name": e["stepName"].replace("_", " ").capitalize(), "input": {},
                          "result": (e.get("metadata") or {}).get("result", {}),
                          "seconds": round((e.get("timestamp", 0) - began) / 1000, 2)})  # fmt: skip
        elif kind == "TOOL_CALL_START":
            calls[e["toolCallId"]] = {"name": f"Tool: {e['toolCallName']}", "start": e.get("timestamp", 0)}
        elif kind == "TOOL_CALL_ARGS":
            calls[e["toolCallId"]]["input"] = json.loads(e.get("delta") or "{}")
        elif kind == "TOOL_CALL_END":
            calls[e["toolCallId"]]["seconds"] = round(
                (e.get("timestamp", 0) - calls[e["toolCallId"]]["start"]) / 1000, 2
            )
        elif kind == "TOOL_CALL_RESULT":
            c = calls.pop(e["toolCallId"])
            steps.append({"name": c["name"], "input": c.get("input", {}), "result": json.loads(e["content"]),
                          "seconds": c.get("seconds", 0.0)})  # fmt: skip
        elif kind == "CUSTOM" and e.get("name") == APPROVAL_REQUESTED:
            steps.append({"name": "Waiting for the guest to approve the payment (sandbox)", "input": {},
                          "result": e.get("value", {}), "seconds": 0.0})  # fmt: skip
    return steps
