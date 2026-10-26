"""Guest-services hand-off: the concierge passes non-activity requests to the stage 2 Guest Request Agent over A2A.

The concierge handles activities. A room move, a complaint, a billing question or a special arrangement belongs to
the hotel's guest request agent, which checks the booking and policy, drafts a reply and proposes staff tasks for a
person to review. The concierge reaches it the way any agent would: it reads the agent card, then sends one A2A
message (JSON-RPC, `Authorization: Bearer $A2A_TOKEN`) with the property and the guest's message, already scrubbed of
contact details by the input guardrail. No name, email or room number is sent.

The concierge tells the guest it was passed on, never what the draft says: the draft is for staff review.

Fallback: when A2A_URL or A2A_TOKEN isn't set (the free live demo: Streamlit Community Cloud can't host the agent's
A2A server), the optional a2a-sdk isn't installed, or the agent doesn't answer in time, the tool says so and the
concierge points the guest to the front desk. A down agent never breaks a concierge answer.
"""

import asyncio
import os

from concierge import config

TIMEOUT_S = float(os.getenv("A2A_TIMEOUT_S", "20"))
FALLBACK = "Guest services can't be reached from this concierge right now. Ask the guest to contact the front desk."
SENDER = "concierge@resort.test"  # the concierge itself; the agent finds no guest booking for it, by design


def settings() -> tuple[str, str]:
    return os.getenv("A2A_URL", "").rstrip("/"), config._secret("A2A_TOKEN")


async def send(url: str, token: str, data: dict, transport=None, timeout: float = TIMEOUT_S) -> dict:
    """One A2A message; returns the final task as a plain dict. `transport` lets tests use an in-process server."""
    import httpx
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.helpers import new_data_message
    from a2a.types import Role, SendMessageRequest
    from google.protobuf.json_format import MessageToDict

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=url, headers=headers, timeout=timeout, transport=transport) as http:
        card = await A2ACardResolver(httpx_client=http, base_url=url).get_agent_card()
        client = await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))
        try:
            request = SendMessageRequest(message=new_data_message(data, role=Role.ROLE_USER))
            events = [MessageToDict(e[0] if isinstance(e, tuple) else e) async for e in client.send_message(request)]
        finally:
            await client.close()
    return next((e["task"] for e in reversed(events) if "task" in e), {})


def outcome(task: dict) -> dict:
    """What the concierge model may see: whether it was handed off, what was understood, never the draft."""
    state = task.get("status", {}).get("state", "")
    data = next((p["data"] for a in task.get("artifacts", []) for p in a.get("parts", []) if "data" in p), None)
    if state != "TASK_STATE_COMPLETED" or not isinstance(data, dict):
        return {"handed_off": False, "fallback": FALLBACK}
    return {
        "handed_off": True,
        "reference": str(data.get("trace_id") or "")[:8],
        "understood": [r.get("summary", "") for r in data.get("requests", []) if isinstance(r, dict)][:5],
        "staff_tasks": len(data.get("tasks", [])),
        "manager_review": bool(data.get("escalate")),
        "note": "Guest services staff review this and reply. Don't promise any outcome.",
    }


def hand_off(prop: str, message: str, transport=None) -> dict:
    url, token = settings()
    if not (url and token):
        return {"handed_off": False, "fallback": FALLBACK, "why": "not configured"}
    data = {"property": prop, "sender": SENDER, "subject": "From the activities concierge", "body": message[:2000]}
    try:
        return outcome(asyncio.run(send(url, token, data, transport=transport)))
    except ImportError:
        return {"handed_off": False, "fallback": FALLBACK, "why": "a2a-sdk not installed"}
    except Exception as exc:  # noqa: BLE001 - a down or slow agent is a fallback, not an error page
        return {"handed_off": False, "fallback": FALLBACK, "why": type(exc).__name__}
