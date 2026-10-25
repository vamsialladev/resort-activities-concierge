"""Spending and abuse limits for the public demo. Checked before any model call; nothing is sent when one is hit.

- per browser session: MAX_QUESTIONS_PER_SESSION questions, and RATE_LIMIT_PER_MINUTE in any 60 seconds
- per day, across every visitor: DAILY_QUESTION_CAP questions and DAILY_COST_CAP_USD of model spend

The daily counters are a row per day in the database (usage_daily), so with Neon they survive app restarts and
apply across replicas. Cost is counted from token usage at PRICE_IN_PER_M / PRICE_OUT_PER_M.
"""

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from concierge import config
from concierge.db import usage_daily


def cost_usd(usage: dict) -> float:
    return (
        usage.get("input_tokens", 0) * config.PRICE_IN_PER_M + usage.get("output_tokens", 0) * config.PRICE_OUT_PER_M
    ) / 1e6


def today_totals(engine: Engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(select(usage_daily).where(usage_daily.c.day == config.today().isoformat())).first()
    return {"questions": row.questions, "cost_usd": row.cost_usd} if row else {"questions": 0, "cost_usd": 0.0}


def blocked(engine: Engine, session_times: list[float], asked: int, now: float) -> str | None:
    if asked >= config.MAX_QUESTIONS_PER_SESSION:
        return f"This demo answers {config.MAX_QUESTIONS_PER_SESSION} messages per visit. Thanks for trying it!"
    if sum(1 for t in session_times if now - t < 60) >= config.RATE_LIMIT_PER_MINUTE:
        return "That's a lot of messages in a minute. Give it a few seconds and try again."
    totals = today_totals(engine)
    if totals["questions"] >= config.DAILY_QUESTION_CAP or totals["cost_usd"] >= config.DAILY_COST_CAP_USD:
        return "The concierge has reached today's limit for the demo. It resets tomorrow; the schedule still works."
    return None


def record(engine: Engine, usage: dict) -> dict:
    day = config.today().isoformat()
    cost = cost_usd(usage)
    with engine.begin() as conn:
        row = conn.execute(select(usage_daily).where(usage_daily.c.day == day)).first()
        if row is None:
            conn.execute(usage_daily.insert().values(day=day, questions=1, cost_usd=round(cost, 6)))
            return {"questions": 1, "cost_usd": round(cost, 6)}
        conn.execute(
            update(usage_daily)
            .where(usage_daily.c.day == day)
            .values(
                questions=usage_daily.c.questions + 1,
                cost_usd=usage_daily.c.cost_usd + cost,
            )
        )
    return today_totals(engine)
