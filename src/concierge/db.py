"""The database: Neon Postgres when DATABASE_URL is set, a local SQLite file otherwise (tests, CI, other machines).

Free-tier friendly: a small connection pool (2 + 2 overflow), `pool_pre_ping` so a connection Neon closed while
the database slept is replaced, and `connect()` retries with a short backoff while Neon wakes up (its free tier
suspends after a few idle minutes; the first connection can take a few seconds). The page shows "Waking up the
database..." meanwhile.

Tables (SQLAlchemy Core, created by `init()` / `python scripts/seed.py`):
activities, stays, booking_requests, conversations, messages, events, usage_daily.
"""

import time
from collections.abc import Callable

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from concierge import config

metadata = MetaData()

activities = Table(
    "activities",
    metadata,
    Column("id", String(40), primary_key=True),  # e.g. BR-20261103-tea
    Column("property", String(20), nullable=False, index=True),
    Column("date", String(10), nullable=False, index=True),  # YYYY-MM-DD
    Column("start", String(5), nullable=False),  # HH:MM
    Column("end", String(5), nullable=False),
    Column("name", String(80), nullable=False),
    Column("category", String(20), nullable=False),  # kids | wellness | food | adventure | water | evening
    Column("description", Text, nullable=False),
    Column("location", String(60), nullable=False),
    Column("indoor", Boolean, nullable=False),
    Column("min_age", Integer, nullable=False),
    Column("max_age", Integer),  # NULL = no upper limit
    Column("price_usd", Float, nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("booked", Integer, nullable=False),
)
stays = Table(
    "stays",
    metadata,
    Column("ref", String(12), primary_key=True),  # e.g. BR-4821
    Column("property", String(20), nullable=False),
    Column("last_name", String(40), nullable=False),  # synthetic; used only to verify, never returned
    Column("room", String(8), nullable=False),
    Column("check_in", String(10), nullable=False),
    Column("check_out", String(10), nullable=False),
    Column("adults", Integer, nullable=False),
    Column("children", Integer, nullable=False),
)
booking_requests = Table(
    "booking_requests",
    metadata,
    Column("id", String(16), primary_key=True),  # REQ-XXXXXXXX
    Column("activity_id", String(40), ForeignKey("activities.id"), nullable=False),
    Column("conversation_id", String(16), index=True),
    Column("stay_ref", String(12)),
    Column("party_size", Integer, nullable=False),
    Column("note", Text, nullable=False, default=""),
    Column("status", String(10), nullable=False, index=True),  # PENDING | APPROVED | DECLINED
    Column("created_at", String(19), nullable=False),
    Column("decided_at", String(19)),
    Column("staff_note", Text),
)
conversations = Table(
    "conversations",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("visitor_id", String(24), nullable=False, index=True),  # anonymous, random; no personal data
    Column("property", String(20), nullable=False),
    Column("room", String(8)),
    Column("title", String(80), nullable=False),
    Column("created_at", String(19), nullable=False),
    Column("updated_at", String(19), nullable=False),
    Column("share_token", String(24), unique=True),
)
messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "conversation_id",
        String(16),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    ),
    Column("role", String(10), nullable=False),  # user | assistant | notice
    Column("content", Text, nullable=False),  # personal data removed before it's written
    Column("meta", Text, nullable=False, default="{}"),  # JSON: understood_as, sources, steps, suggestions
    Column("created_at", String(19), nullable=False),
)
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(19), nullable=False, index=True),
    Column("visitor_id", String(24)),
    Column("kind", String(12), nullable=False, index=True),  # question | unanswered | view | request
    Column("property", String(20)),
    Column("activity_name", String(80)),
    Column("detail", Text),  # a question, redacted
)
usage_daily = Table(
    "usage_daily",
    metadata,
    Column("day", String(10), primary_key=True),
    Column("questions", Integer, nullable=False),
    Column("cost_usd", Float, nullable=False),
)


class WakingUp(RuntimeError):
    """The database didn't answer after the retries (Neon still waking, or the network is down)."""


def make_engine(url: str | None = None) -> Engine:
    url = url or config.database_url()
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_timeout=20,
        connect_args={"connect_timeout": 10, "application_name": "resort-concierge"},
    )


def connect(engine: Engine, attempts: int = 4, sleep: Callable[[float], None] = time.sleep):
    """A connection, retrying while Neon wakes up (1 s, 2 s, 4 s). Raises WakingUp after the last attempt."""
    for i in range(attempts):
        try:
            return engine.connect()
        except OperationalError as exc:
            if i == attempts - 1:
                raise WakingUp("the database didn't answer; it may be waking up") from exc
            sleep(2**i)
    raise WakingUp("no attempts")  # pragma: no cover


def init(engine: Engine) -> None:
    metadata.create_all(engine)
