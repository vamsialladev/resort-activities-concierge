"""Shared guardrails, request tracing and the cross-app ops log (hotel-ai-platform), wired for the concierge.

    with ops.start(visitor) as trace:                one trace per guest message; the reference shows on errors
        v = ops.check_message(text)                  before the rewrite and the model
        ...agent.respond(): the rewrite, each model turn and each tool call are spans...
        o = ops.check_answer(answer, turn)           after the model, against this turn's tool results
        ops.finish(trace, turn, status)              one ops_request_log row + the spans, PII removed first

The Staff page is this app's Admin page (ADMIN_PASSWORD, with STAFF_PASSWORD still accepted): its Traces tab is
the shared ops view.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from hotelplatform import guardrails, jsonlog, oplog, tracing, version

from concierge import config

APP = "resort-activities-concierge"
APP_VERSION = "1.1.0"
ROOT = Path(__file__).resolve().parents[2]
MONTHLY_COST_CAP_USD = float(os.getenv("MONTHLY_COST_CAP_USD", "15.00"))

INPUT_POLICY = guardrails.InputPolicy(max_chars=1000, languages=("en", "es"))
# Answers quote activity listings and FAQ passages, not numbered citations, so a citation isn't required; promises
# (a booking "confirmed", a fee "waived") are checked against this turn's tool results, so the FAQ's own "free of
# charge up to 4 hours before" stays a policy statement. Checked on the saved eval answers: 0 of 228 changed.
OUTPUT_POLICY = guardrails.OutputPolicy(require_citation=False, numbers="off", promises="block", pii_leak="redact")


@lru_cache(maxsize=1)
def store() -> oplog.OpsStore:
    """One per process; nothing connects until the first row (the keep-awake visit never gets that far)."""
    url = config._secret("DATABASE_URL").replace("postgres://", "postgresql://", 1)
    return oplog.OpsStore(APP, url=url, log_dir=ROOT / "logs", retention_days=30)


@lru_cache(maxsize=1)
def running_version() -> str:
    return version.version_string(APP_VERSION, ROOT)


def configure_logs() -> None:
    jsonlog.configure(APP, running_version())


def start(visitor: str | None):
    return tracing.new_trace(APP, session_id=visitor)


def check_message(text: str) -> guardrails.Verdict:
    return guardrails.check_input(text, INPUT_POLICY)


def check_answer(answer: str, tool_texts: list[str], question: str) -> guardrails.Verdict:
    return guardrails.check_output(answer, OUTPUT_POLICY, sources=tool_texts, input_text=question)


def safety_flags(trace) -> list[str]:
    flags = set()
    for span in trace.spans if trace is not None else []:
        if span.name.startswith("guardrails."):
            stage = span.name.split(".", 1)[1]
            flags.update(span.attributes.get("flags") or [])
            flags.update(f"{stage}:{r}" for r in span.attributes.get("reasons") or [])
    return sorted(flags)


def finish(trace, turn=None, status: str = "ok", error_type: str | None = None, request_type: str = "chat") -> bool:
    """Write the ops row for one message. Never raises, never blocks."""
    if trace is None:
        return False
    try:
        usage = getattr(turn, "usage", None) or {"input_tokens": 0, "output_tokens": 0}
        from concierge import limits

        row = oplog.request_row(
            trace,
            request_type=request_type,
            status=status,
            latency_ms=round(getattr(turn, "seconds", 0.0) * 1000, 1) or trace.elapsed_ms(),
            error_type=error_type,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            cost_usd=limits.cost_usd(usage),
            model=config.LLM_MODEL if usage.get("calls") else None,
            tool_calls=[
                {"tool": s.name.removeprefix("Tool: "), "seconds": s.seconds}
                for s in getattr(turn, "steps", [])
                if s.name.startswith("Tool: ")
            ],  # fmt: skip
            sources=list(dict.fromkeys(getattr(turn, "sources", []))),
            safety_flags=safety_flags(trace),
            version=running_version(),
            data={
                "question": getattr(turn, "question", None),
                "understood_as": getattr(turn, "understood_as", None),
                "answer": getattr(turn, "answer", None),
                "requests": getattr(turn, "requests", []),
            },  # fmt: skip
        )
        if status == "capped":
            jsonlog.cap_hit(error_type or "cap", trace_id=trace.trace_id)
        return store().submit(trace, row)
    except Exception:
        return False


def tool_text(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)[:8000]


def dependencies() -> dict[str, str]:
    return {
        "anthropic": "configured" if config._secret("ANTHROPIC_API_KEY") else "missing key",
        "database": "Neon Postgres" if config._secret("DATABASE_URL") else "SQLite (local file)",
        "ops log": store().health()["status"],
        "embeddings": "bge-small (fastembed)",
        "model": config.LLM_MODEL,
    }


def caps() -> dict[str, float]:
    return {"cost_cap_day": config.DAILY_COST_CAP_USD, "cost_cap_month": MONTHLY_COST_CAP_USD}
