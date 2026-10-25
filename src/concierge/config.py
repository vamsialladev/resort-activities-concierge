"""Settings, from environment variables or Streamlit secrets (README: Configuration). Secrets never have defaults."""

import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _secret(name: str) -> str:
    """Environment first, then Streamlit secrets (Streamlit Cloud), else empty. Never logged."""
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, "")) if hasattr(st, "secrets") else ""
    except Exception:  # noqa: BLE001 - no secrets file locally is normal
        return ""


def _float(name: str, default: str) -> float:
    return float(os.getenv(name) or default)


DATA_DIR = ROOT / "data"
DOCS_DIR = DATA_DIR / "docs"
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", DATA_DIR / "concierge.db"))
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "low")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
RESORT_TZ = ZoneInfo(os.getenv("RESORT_TZ", "America/New_York"))
SCHEDULE_DAYS = 14
RETRIEVAL = os.getenv("RETRIEVAL", "hybrid")  # hybrid (BM25 + embeddings, RRF) | bm25
EMBED_CACHE_DIR = Path(os.getenv("EMBED_CACHE_DIR", ROOT / ".cache" / "fastembed"))
TOP_K = int(os.getenv("TOP_K", "4"))
MAX_QUESTIONS_PER_SESSION = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "25"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "6"))
DAILY_QUESTION_CAP = int(os.getenv("DAILY_QUESTION_CAP", "400"))
DAILY_COST_CAP_USD = _float("DAILY_COST_CAP_USD", "1.50")
# Used for the daily cost cap only. Defaults: Claude Haiku 5.5 list price, USD per million tokens (2026-10).
PRICE_IN_PER_M = _float("PRICE_IN_PER_M", "0.10")
PRICE_OUT_PER_M = _float("PRICE_OUT_PER_M", "0.50")
DEMO_VIDEO_URL = os.getenv("DEMO_VIDEO_URL", "")
APP_URL = os.getenv("APP_URL", "")  # the public address, for QR codes; the page's own address is used if empty
REPO_URL = "https://github.com/vamsialladev/resort-activities-concierge"
PORTFOLIO_URL = "https://vamsialla.com"
PROPERTIES = {"beach-resort": "Beach Resort", "mountain-lodge": "Mountain Lodge"}


def database_url() -> str:
    """DATABASE_URL (Neon Postgres) when set; otherwise a local SQLite file, so tests and CI never need Neon."""
    url = _secret("DATABASE_URL")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url or f"sqlite:///{SQLITE_PATH.as_posix()}"


def staff_password() -> str:
    return _secret("STAFF_PASSWORD")


def today() -> date:
    """The resort's today. CONCIERGE_TODAY pins it (the eval uses 2026-11-02 so its answers never go stale)."""
    pinned = os.getenv("CONCIERGE_TODAY", "")
    return date.fromisoformat(pinned) if pinned else datetime.now(RESORT_TZ).date()


def now() -> datetime:
    pinned = os.getenv("CONCIERGE_NOW", "")
    return datetime.fromisoformat(pinned) if pinned else datetime.now(RESORT_TZ).replace(tzinfo=None)
