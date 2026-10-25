"""Conversations and messages in the database, per anonymous visitor. Personal data is removed before writing.

A visitor is a random ID in the page address (`?v=...`): no sign-in, no cookie, no name. Bookmark the address and
your past conversations come back; anyone with the address sees them too, which is why nothing personal is stored.
Every message passes through pii.scrub_text first (emails, phones, card numbers, booking references, names after
"my name is"...), so a reopened or shared conversation holds the redacted text. The live conversation keeps the
original text in the browser session for the agent's context.

Sharing makes a random token; `?share=<token>` shows the conversation read-only and never calls the model.
"""

import json
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from concierge import config
from concierge.db import conversations, messages
from concierge.pii import scrub_text


def _now() -> str:
    return config.now().isoformat(timespec="seconds")


def new_visitor_id() -> str:
    return secrets.token_urlsafe(9)


def create(engine: Engine, visitor_id: str, prop: str, room: str, title: str) -> str:
    cid = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        conn.execute(
            conversations.insert().values(
                id=cid,
                visitor_id=visitor_id,
                property=prop,
                room=room or None,
                title=scrub_text(title)[:80],
                created_at=_now(),
                updated_at=_now(),
            )
        )
    return cid


def add_message(
    engine: Engine,
    conversation_id: str,
    role: str,
    content: str,
    meta: dict | None = None,
) -> None:
    meta = meta or {}
    clean_meta = {k: (scrub_text(v) if isinstance(v, str) else v) for k, v in meta.items()}
    with engine.begin() as conn:
        conn.execute(
            messages.insert().values(
                conversation_id=conversation_id,
                role=role,
                content=scrub_text(content or ""),
                meta=json.dumps(clean_meta, ensure_ascii=False, default=str),
                created_at=_now(),
            )
        )
        conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(updated_at=_now()))


def list_for(engine: Engine, visitor_id: str, limit: int = 20) -> list[dict]:
    q = (
        select(conversations)
        .where(conversations.c.visitor_id == visitor_id)
        .order_by(conversations.c.updated_at.desc())
        .limit(limit)
    )
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q)]


def load(engine: Engine, conversation_id: str, visitor_id: str | None = None) -> tuple[dict | None, list[dict]]:
    """The conversation and its messages. With visitor_id, only if it belongs to that visitor."""
    with engine.connect() as conn:
        conv = conn.execute(select(conversations).where(conversations.c.id == conversation_id)).first()
        if conv is None or (visitor_id is not None and conv.visitor_id != visitor_id):
            return None, []
        rows = conn.execute(
            select(messages).where(messages.c.conversation_id == conversation_id).order_by(messages.c.id)
        )
        msgs = [{**dict(r._mapping), "meta": json.loads(r.meta or "{}")} for r in rows]
    return dict(conv._mapping), msgs


def share_token(engine: Engine, conversation_id: str) -> str:
    with engine.begin() as conn:
        token = conn.execute(
            select(conversations.c.share_token).where(conversations.c.id == conversation_id)
        ).scalar_one_or_none()
        if not token:
            token = secrets.token_urlsafe(12)
            conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(share_token=token))
    return token


def by_token(engine: Engine, token: str) -> tuple[dict | None, list[dict]]:
    if not token or len(token) > 24:
        return None, []
    with engine.connect() as conn:
        cid = conn.execute(select(conversations.c.id).where(conversations.c.share_token == token)).scalar_one_or_none()
    return load(engine, cid) if cid else (None, [])


def turns(msgs: list[dict]) -> list[dict]:
    """User/assistant pairs (notices skipped) as agent history: {"question", "answer"}."""
    out, pending = [], None
    for m in msgs:
        if m["role"] == "user":
            pending = m["meta"].get("understood_as") or m["content"]
        elif m["role"] == "assistant" and pending is not None:
            out.append({"question": pending, "answer": m["content"]})
            pending = None
    return out


def share_url(base_url: str, token: str) -> str:
    base = (base_url or "").split("?", 1)[0].split("#", 1)[0]
    return f"{base}?share={token}"
