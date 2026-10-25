"""Usage events and the Staff page's analytics. Questions are stored redacted; there are no names or rooms here.

Events: `question` (every message to the concierge), `unanswered` (the FAQ search found nothing, or the answer says
it doesn't know), `view` (a guest opened an activity's details on the schedule, or the concierge listed it),
`request` (a booking request was created). Analytics are counts over these plus the booking_requests table.
"""

import re
from collections import Counter
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from concierge import config
from concierge.db import activities, booking_requests, events
from concierge.pii import scrub_text

DONT_KNOW = re.compile(
    r"\b(?:I don'?t know|I'?m not sure|don'?t have (?:that|any) information|isn'?t covered|not covered|"
    r"couldn'?t find|ask the front desk|check with the front desk)\b",
    re.IGNORECASE,
)


def log(
    engine: Engine,
    kind: str,
    visitor_id: str = "",
    prop: str = "",
    activity_name: str = "",
    detail: str = "",
):
    now = config.now()
    with engine.begin() as conn:
        conn.execute(
            events.insert().values(
                ts=now.isoformat(timespec="seconds"),
                visitor_id=visitor_id or None,
                kind=kind,
                property=prop or None,
                activity_name=activity_name or None,
                detail=scrub_text(detail or "")[:300] or None,
            )
        )


def unanswered(turn) -> bool:
    return bool(turn.faq_empty or DONT_KNOW.search(turn.answer or ""))


def record_turn(engine: Engine, turn, visitor_id: str) -> None:
    """All events for one concierge turn."""
    log(
        engine,
        "question",
        visitor_id,
        turn.property,
        detail=turn.understood_as or turn.question,
    )
    if unanswered(turn):
        log(
            engine,
            "unanswered",
            visitor_id,
            turn.property,
            detail=turn.understood_as or turn.question,
        )
    for name in dict.fromkeys(turn.activities_seen):
        log(engine, "view", visitor_id, turn.property, activity_name=name)


def _since(days: int) -> str:
    return (config.now() - timedelta(days=days)).isoformat(timespec="seconds")


def normalize(question: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (question or "").lower()))


def top_questions(engine: Engine, prop: str, days: int = 30, n: int = 10) -> list[dict]:
    q = select(events.c.detail).where(
        events.c.kind == "question",
        events.c.property == prop,
        events.c.ts >= _since(days),
    )
    with engine.connect() as conn:
        counts = Counter(normalize(r.detail) for r in conn.execute(q) if r.detail)
    return [{"question": k, "times": v} for k, v in counts.most_common(n)]


def unanswered_questions(engine: Engine, prop: str, days: int = 30, n: int = 20) -> list[dict]:
    q = (
        select(events.c.ts, events.c.detail)
        .where(
            events.c.kind == "unanswered",
            events.c.property == prop,
            events.c.ts >= _since(days),
        )
        .order_by(events.c.ts.desc())
        .limit(n)
    )
    with engine.connect() as conn:
        return [{"when": r.ts, "question": r.detail} for r in conn.execute(q)]


def viewed_vs_requested(engine: Engine, prop: str, days: int = 30) -> list[dict]:
    """Per activity name: views, requests, approved; including activities nobody looked at ('ignored')."""
    since = _since(days)
    with engine.connect() as conn:
        names = [
            r.name for r in conn.execute(select(activities.c.name).where(activities.c.property == prop).distinct())
        ]
        views = dict(
            conn.execute(
                select(events.c.activity_name, func.count())
                .where(
                    events.c.kind == "view",
                    events.c.property == prop,
                    events.c.ts >= since,
                )
                .group_by(events.c.activity_name)
            ).all()
        )
        reqs = conn.execute(
            select(activities.c.name, booking_requests.c.status, func.count())
            .join(activities, activities.c.id == booking_requests.c.activity_id)
            .where(activities.c.property == prop, booking_requests.c.created_at >= since)
            .group_by(activities.c.name, booking_requests.c.status)
        ).all()
    requested, approved = Counter(), Counter()
    for name, status, count in reqs:
        requested[name] += count
        if status == "APPROVED":
            approved[name] += count
    rows = [
        {
            "activity": n,
            "views": views.get(n, 0),
            "requests": requested[n],
            "approved": approved[n],
            "ignored": views.get(n, 0) == 0 and requested[n] == 0,
        }
        for n in sorted(names)
    ]
    return sorted(rows, key=lambda r: (-r["views"], -r["requests"], r["activity"]))


def peak_hours(engine: Engine, prop: str, days: int = 30) -> dict[int, int]:
    q = select(events.c.ts).where(
        events.c.kind == "question",
        events.c.property == prop,
        events.c.ts >= _since(days),
    )
    with engine.connect() as conn:
        hours = Counter(int(r.ts[11:13]) for r in conn.execute(q))
    return {h: hours.get(h, 0) for h in range(24)}
