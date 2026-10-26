# AG-UI events

Every concierge answer is recorded as a run of [AG-UI](https://docs.ag-ui.com) events, built with the official
`ag-ui-protocol` Python types (`ag_ui.core`, v1.0.0). Code: [`src/concierge/agui.py`](../src/concierge/agui.py).

The events are saved with the assistant message (`meta.events`, JSON, camelCase as on the wire). The page's step
timeline is drawn from them by `agui.timeline()`, so what the page shows is exactly what an AG-UI client would get.
The Streamlit app doesn't stream them over HTTP: Streamlit Community Cloud serves only the app. An AG-UI server
endpoint (SSE) is **Roadmap**.

## One guest message = one run

| Order | Event type | Fields used | When |
|---|---|---|---|
| 1 | `RUN_STARTED` | `threadId`, `runId`, `timestamp`, `metadata.message` (first 500 characters) | the message arrives |
| 2 | `STEP_STARTED` / `STEP_FINISHED` | `stepName: "rewrite_follow_up"`, `metadata.result` | a follow-up was rewritten into a standalone question |
| 3 | `TOOL_CALL_START` | `toolCallId`, `toolCallName`, `timestamp` | the model calls a tool |
| 4 | `TOOL_CALL_ARGS` | `toolCallId`, `delta` (the arguments as JSON) | |
| 5 | `TOOL_CALL_END` | `toolCallId`, `timestamp` | |
| 6 | `TOOL_CALL_RESULT` | `toolCallId`, `messageId`, `content` (the result summary the timeline shows, JSON, first 4,000 characters), `role: "tool"` | |
| 7 | `CUSTOM` `human_approval_requested` | `value`: the payment block (mandate ID, total, merchant, expiry) | a paid request needs the guest's approval |
| 8 | `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` | `messageId`, `role: "assistant"`, `delta` | the answer streams |
| 9 | `STATE_SNAPSHOT` | `snapshot`: `requests`, `sources`, `stop` | the end of the run |
| 10 | `RUN_FINISHED` (or `RUN_ERROR` with `message`) | `threadId`, `runId`, `result` | |

Rows 3 to 8 repeat for each model turn (at most 6): text, when a turn has any, comes before that turn's tool calls.

## Decisions after the run

These happen later, outside the run, and are saved as single `CUSTOM` events on the conversation's notices:

| Name | Who | Value |
|---|---|---|
| `human_approval_granted` | the guest, in the chat | `mandate_id`, `request_id`, `status: "AUTHORIZED"`, `total_usd` |
| `human_approval_declined` | the guest, in the chat | `mandate_id`, `request_id`, `status: "DECLINED"`, `total_usd` |
| `staff_decision` | staff, on the Staff page | `request_id`, `status: "APPROVED"` or `"DECLINED"` |

## What is never in an event

- Secrets: none reach the agent.
- The guest's contact details: the input guardrail replaces them before the model, so tool arguments and results
  don't carry them. The original message is stored redacted.

## Tests

`tests/test_agui.py` checks a run's event order, that every event validates against the official types, and that
`timeline()` rebuilds the steps; `tests/test_pages.py` checks the page draws the timeline from stored events and that a paid request shows the
payment approval.
