"""Tests run on a temporary SQLite file with a pinned date. They never read DATABASE_URL (even if .env has the Neon
line) and never call the model."""

import os

os.environ["DATABASE_URL"] = ""  # set before config loads .env (load_dotenv never overrides an existing variable)
os.environ["CONCIERGE_TODAY"] = "2026-11-02"  # a Monday
os.environ["CONCIERGE_NOW"] = "2026-11-02T08:15:00"
os.environ["STAFF_PASSWORD"] = ""
os.environ["RETRIEVAL"] = "bm25"  # unit tests stay fast; the hybrid path has its own test with a fake embedder

from datetime import date  # noqa: E402

import pytest  # noqa: E402

from concierge import config, db, seed, tools  # noqa: E402

TODAY = date(2026, 11, 2)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setattr(config, "database_url", lambda: url)
    eng = db.make_engine(url)
    seed.ensure_window(eng, TODAY)
    yield eng
    eng.dispose()


@pytest.fixture
def tctx(engine):
    def make(prop="beach-resort", last="", conversation_id=""):
        return tools.ToolContext(engine, prop, conversation_id=conversation_id, last_user_message=last, today=TODAY)

    return make


@pytest.fixture(autouse=True)
def fresh_gate_counters():
    """The Staff lockout also counts per process (hotel-ai-platform admin_gate): reset it between tests."""
    from hotelplatform import admin_gate

    admin_gate.reset_process_counters()
    yield
    admin_gate.reset_process_counters()


@pytest.fixture(autouse=True)
def ops_log_in_tmp(tmp_path, monkeypatch):
    """The shared ops store writes JSONL files without DATABASE_URL; tests write to a temp folder instead."""
    from hotelplatform import oplog

    from concierge import ops

    store = oplog.OpsStore("resort-activities-concierge", url="", log_dir=tmp_path / "ops")
    monkeypatch.setattr(ops, "store", lambda: store)
    yield store


@pytest.fixture(autouse=True)
def no_guess_delay(monkeypatch):
    """The Staff sign-in waits a second after a wrong password; tests don't."""
    from concierge import config

    monkeypatch.setattr(config, "GUESS_DELAY_S", 0.0)
