"""The guest-services hand-off over A2A, against an in-process A2A server shaped like the stage 2 agent's."""

import json

import httpx
import pytest

from concierge import a2a_client, tools

a2a = pytest.importorskip("a2a")
from a2a.helpers import get_data_parts, new_task_from_user_message, new_text_message  # noqa: E402
from a2a.server.agent_execution import AgentExecutor  # noqa: E402
from a2a.server.request_handlers import DefaultRequestHandler  # noqa: E402
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes  # noqa: E402
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater  # noqa: E402
from a2a.types import (  # noqa: E402
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    TaskState,
)
from google.protobuf import struct_pb2  # noqa: E402
from starlette.applications import Starlette  # noqa: E402

URL = "http://guest-agent.test"
SEEN = []


class FakeGuestAgent(AgentExecutor):
    def __init__(self, fail=False):
        self.fail = fail

    async def execute(self, context, event_queue):
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        SEEN.append(next(iter(get_data_parts(context.message.parts))))
        if self.fail:
            await updater.update_status(state=TaskState.TASK_STATE_FAILED, message=new_text_message("No."))
            return
        payload = struct_pb2.Struct()
        payload.update(
            {
                "outcome": "drafted",
                "escalate": True,
                "requests": [{"summary": "Move to a quieter room", "kind": "room", "status": "needs_staff"}],
                "draft": "We are sorry about the noise; a manager will call you.",
                "tasks": [{"id": "T1", "department": "front_desk", "title": "Offer a room move"}],
                "trace_id": "4f1c9a2e" * 4,
            }
        )
        await updater.add_artifact(parts=[Part(data=struct_pb2.Value(struct_value=payload))], name="guest_email_result")
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED, message=new_text_message("Draft ready."))

    async def cancel(self, context, event_queue):  # pragma: no cover
        raise NotImplementedError


def server(fail=False):
    card = AgentCard(
        name="Guest Request Agent",
        description="test",
        version="test",
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=URL, protocol_version="1.0")],
        skills=[AgentSkill(id="handle_guest_email", name="Handle a guest email", description="d", tags=["t"])],
    )
    handler = DefaultRequestHandler(
        agent_executor=FakeGuestAgent(fail), task_store=InMemoryTaskStore(), agent_card=card
    )
    app = Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")])
    return httpx.ASGITransport(app=app)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("A2A_URL", URL)
    monkeypatch.setenv("A2A_TOKEN", "test-token")
    SEEN.clear()


def test_handed_off_with_a_reference_and_without_the_draft(configured):
    out = a2a_client.hand_off("mountain-lodge", "Our room is noisy, can we move?", transport=server())
    assert out["handed_off"] and out["reference"] == "4f1c9a2e"
    assert out["understood"] == ["Move to a quieter room"] and out["staff_tasks"] == 1 and out["manager_review"]
    assert "noise" not in json.dumps(out)  # the draft is for staff, not the concierge
    (sent,) = SEEN
    assert sent["property"] == "mountain-lodge" and sent["sender"] == a2a_client.SENDER  # no guest identity sent


def test_a_failed_task_falls_back(configured):
    out = a2a_client.hand_off("beach-resort", "Can we move?", transport=server(fail=True))
    assert out == {"handed_off": False, "fallback": a2a_client.FALLBACK}


def test_not_configured_falls_back_without_a_call(monkeypatch):
    monkeypatch.delenv("A2A_URL", raising=False)
    monkeypatch.setattr(a2a_client.config, "_secret", lambda name: "")
    out = a2a_client.hand_off("beach-resort", "Can we move?")
    assert not out["handed_off"] and out["why"] == "not configured"


def test_agent_down_falls_back(configured):
    def down(request):
        raise httpx.ConnectError("refused")

    out = a2a_client.hand_off("beach-resort", "Can we move?", transport=httpx.MockTransport(down))
    assert not out["handed_off"] and out["fallback"] == a2a_client.FALLBACK


def test_the_tool_is_offered_and_checks_its_input(engine):
    assert "guest_services" in tools.FUNCTIONS and any(s["name"] == "guest_services" for s in tools.SCHEMAS)
    ctx = tools.ToolContext(engine, "beach-resort")
    assert tools.call(ctx, "guest_services", {"request": " "}) == {"error": "request is empty"}
