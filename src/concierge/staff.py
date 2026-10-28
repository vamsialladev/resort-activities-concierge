"""The staff side: sign-in, pending requests (approve / decline), and the guest notice in their chat.

Sign-in is one shared password (STAFF_PASSWORD), compared in constant time; without it set, the Staff page stays
locked. Approving re-checks capacity and adds the party to the session's booked count in the same transaction; the
guest's conversation gets a notice ("Update from the activities desk: ... approved"). SSO would replace the
shared password in a real deployment (docs/DECISIONS.md).
"""

import hmac

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from concierge import agui, ap2_sandbox, chats, config
from concierge.db import activities, booking_requests


class DecisionError(ValueError):
    pass


def check_password(given: str, expected: str | None = None) -> bool:
    expected = config.staff_password() if expected is None else expected
    return bool(expected) and hmac.compare_digest((given or "").encode(), expected.encode())


def requests(engine: Engine, status: str | None = "PENDING", limit: int = 100) -> list[dict]:
    q = (
        select(
            booking_requests,
            activities.c.name,
            activities.c.date,
            activities.c.start,
            activities.c.property,
            activities.c.price_usd,
            activities.c.capacity,
            activities.c.booked,
        )
        .join(activities, activities.c.id == booking_requests.c.activity_id)
        .order_by(booking_requests.c.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(booking_requests.c.status == status)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q)]


def decide(engine: Engine, request_id: str, approve: bool, staff_note: str = "") -> dict:
    with engine.begin() as conn:
        req = conn.execute(select(booking_requests).where(booking_requests.c.id == request_id)).first()
        if req is None:
            raise DecisionError("request not found")
        if req.status != "PENDING":
            raise DecisionError(f"request is already {req.status}")
        act = conn.execute(select(activities).where(activities.c.id == req.activity_id)).first()
        status = "APPROVED" if approve else "DECLINED"
        mandate = ap2_sandbox.for_request(engine, request_id)
        if approve and mandate is not None and mandate.status != "AUTHORIZED":
            raise DecisionError(f"the guest hasn't approved the payment yet ({mandate.status}, sandbox)")
        if approve:
            if act.capacity - act.booked < req.party_size:
                raise DecisionError(f"only {max(act.capacity - act.booked, 0)} places left")
            conn.execute(update(activities).where(activities.c.id == act.id).values(booked=act.booked + req.party_size))
        conn.execute(
            update(booking_requests)
            .where(booking_requests.c.id == request_id)
            .values(
                status=status,
                decided_at=config.now().isoformat(timespec="seconds"),
                staff_note=(staff_note or "")[:300],
            )
        )
    when = f"{act.date} at {act.start}"
    if approve:
        price = f", ${act.price_usd * req.party_size:.0f} charged to your room" if act.price_usd else ""
        text = f"Update from the activities desk: {act.name} on {when} for {req.party_size} is approved{price}."
    else:
        text = f"Update from the activities desk: we couldn't approve {act.name} on {when}."
    if staff_note:
        text += f" Note: {staff_note[:200]}"
    if req.conversation_id:
        chats.add_message(
            engine,
            req.conversation_id,
            "notice",
            text,
            {"request_id": request_id, "status": status,
             # the staff decision as an AG-UI CUSTOM event on the guest's thread (docs/AGUI_EVENTS.md)
             "events": [agui.custom_event(agui.STAFF_DECISION, {"request_id": request_id, "status": status})]},
        )  # fmt: skip
    return {"request_id": request_id, "status": status, "notice": text}
