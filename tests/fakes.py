"""A stand-in for the Anthropic client: queued messages, recorded requests, no network."""

from contextlib import contextmanager
from types import SimpleNamespace


def usage():
    return SimpleNamespace(input_tokens=100, output_tokens=20)


def text(content: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=content)], stop_reason="end_turn", usage=usage())


def tool(name: str, args: dict, uid: str = "tu_1", say: str = ""):
    blocks = ([SimpleNamespace(type="text", text=say)] if say else []) + [
        SimpleNamespace(type="tool_use", id=uid, name=name, input=args)
    ]
    return SimpleNamespace(content=blocks, stop_reason="tool_use", usage=usage())


class FakeModel:
    """`stream()` returns the next queued message (its text in two chunks); `create()` (the rewrite call) returns
    the next queued rewrite string."""

    def __init__(self, *messages, rewrites=()):
        self.queue, self.rewrites, self.requests = list(messages), list(rewrites), []
        self.messages = self

    @contextmanager
    def stream(self, **request):
        self.requests.append(request)
        message = self.queue.pop(0)
        content = "".join(b.text for b in message.content if b.type == "text")
        chunks = [content[: len(content) // 2], content[len(content) // 2 :]] if content else []
        yield SimpleNamespace(text_stream=iter(chunks), get_final_message=lambda: message)

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.rewrites.pop(0))], usage=usage())
