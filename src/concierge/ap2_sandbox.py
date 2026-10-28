"""AP2-style payment mandates for paid activities. **Sandbox only: no payment processor, no real money.**

When the concierge sends a booking request for a paid activity, it also prepares the three AP2 mandates:

    IntentMandate   what the guest asked for, in their own words, with an expiry
    CartMandate     the activities desk's cart (item, party size, total from the database), signed by the "merchant"
    PaymentMandate  the payment for that cart, waiting for the guest's own approval in the chat

The field names follow the official AP2 models (github.com/google-agentic-commerce/AP2, v0.2.0,
code/sdk/python/ap2/models/mandate.py). The official SDK isn't imported here: it pins exact versions of pydantic and
cryptography (and pytest as a runtime dependency), which a live Streamlit app shouldn't take on; the Protocols Lab uses
the SDK itself. Signatures here are HMAC-SHA256 stand-ins for AP2's JWTs and verifiable credentials.

Rules, each tested:
- the amount always comes from the activity's price x party size in the database, never from text the guest or a
  document wrote (an injected "charge $1" or "pay $5,000 to ..." changes nothing);
- the only merchant is the resort's activities desk;
- a conversation can't authorise more than SANDBOX_SPEND_LIMIT_USD a day;
- nothing is authorised without the guest pressing Approve, and staff can't approve a paid request until it is;
- a cart expires after 15 minutes.
"""

import hashlib
import hmac
import json
import os
import secrets
import uuid
import weakref
from datetime import datetime, timedelta

from sqlalchemy import Column, MetaData, String, Table, Text, func, select, update
from sqlalchemy.engine import Engine

from concierge import config

MERCHANT = "Resort Activities Desk (sandbox)"
ALLOWED_MERCHANTS = (MERCHANT,)
SPEND_LIMIT_USD = float(os.getenv("SANDBOX_SPEND_LIMIT_USD", "300"))
CART_MINUTES = 15
SANDBOX_NOTE = "Sandbox: no payment processor, no real money."
_KEY = (os.getenv("AP2_SANDBOX_KEY") or secrets.token_hex(32)).encode()  # per process unless set

metadata = MetaData()
mandates = Table(
    "payment_mandates",
    metadata,
    Column("id", String(20), primary_key=True),  # PM-XXXXXXXX
    Column("request_id", String(16), nullable=False, index=True),
    Column("conversation_id", String(16), index=True),
    Column("intent", Text, nullable=False),  # IntentMandate JSON
    Column("cart", Text, nullable=False),  # CartMandate JSON (contents + merchant_authorization)
    Column("payment", Text, nullable=False),  # PaymentMandate JSON (+ user_authorization once approved)
    Column("total_usd", String(16), nullable=False),
    Column("status", String(16), nullable=False, index=True),  # AWAITING_GUEST | AUTHORIZED | DECLINED | EXPIRED
    Column("created_at", String(19), nullable=False),
    Column("decided_at", String(19)),
)


class MandateError(ValueError):
    pass


_READY: "weakref.WeakSet[Engine]" = weakref.WeakSet()  # engines, not ids: a disposed engine's id can be reused


def ensure(engine: Engine) -> None:
    """Create the table once per engine (a Neon round trip only the first time)."""
    if engine not in _READY:
        metadata.create_all(engine)
        _READY.add(engine)


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign(obj) -> str:
    return hmac.new(_KEY, _canonical(obj), hashlib.sha256).hexdigest()


def _now(now: datetime | None) -> datetime:
    return (now or config.now()).replace(microsecond=0)


def spent_today(engine: Engine, conversation_id: str | None, now: datetime | None = None) -> float:
    ensure(engine)
    day = _now(now).date().isoformat()
    with engine.connect() as conn:
        rows = conn.execute(
            select(mandates.c.total_usd).where(
                mandates.c.conversation_id == conversation_id,
                mandates.c.status == "AUTHORIZED",
                func.substr(mandates.c.decided_at, 1, 10) == day,
            )
        ).all()
    return round(sum(float(r.total_usd) for r in rows), 2)


def prepare(engine: Engine, request_id: str, activity, party_size: int, guest_words: str,
            conversation_id: str | None, now: datetime | None = None) -> dict:  # fmt: skip
    """The three mandates for a paid request, waiting for the guest. `activity` is the database row."""
    ensure(engine)
    now = _now(now)
    total = round(float(activity.price_usd) * int(party_size), 2)  # from the database only
    if total <= 0:
        return {"status": "free", "note": "No payment needed."}
    if spent_today(engine, conversation_id, now) + total > SPEND_LIMIT_USD:
        raise MandateError(
            f"over the sandbox spending limit of ${SPEND_LIMIT_USD:.0f} a day for this conversation; staff can help"
        )
    expiry = (now + timedelta(minutes=CART_MINUTES)).isoformat()
    intent = {
        "user_cart_confirmation_required": True,
        "natural_language_description": (guest_words or "")[:300],
        "merchants": [MERCHANT],
        "skus": [activity.id],
        "requires_refundability": True,
        "intent_expiry": expiry,
    }
    contents = {
        "id": f"cart-{uuid.uuid4().hex[:8]}",
        "user_cart_confirmation_required": True,
        "payment_request": {
            "method_data": [{"supported_methods": "sandbox-room-charge"}],
            "details": {
                "id": request_id,
                "display_items": [
                    {"label": f"{activity.name} x {party_size}", "amount": {"currency": "USD", "value": total}}
                ],  # fmt: skip
                "total": {"label": "Total", "amount": {"currency": "USD", "value": total}},
            },
        },
        "cart_expiry": expiry,
        "merchant_name": MERCHANT,
    }
    cart = {"contents": contents, "merchant_authorization": sign(contents)}
    mandate_id = f"PM-{uuid.uuid4().hex[:8].upper()}"
    payment = {
        "payment_mandate_contents": {
            "payment_mandate_id": mandate_id,
            "payment_details_id": request_id,
            "payment_details_total": {"label": "Total", "amount": {"currency": "USD", "value": total}},
            "merchant_agent": MERCHANT,
            "timestamp": now.isoformat(),
        },
        "user_authorization": None,
    }
    with engine.begin() as conn:
        conn.execute(mandates.insert().values(
            id=mandate_id, request_id=request_id, conversation_id=conversation_id, intent=json.dumps(intent),
            cart=json.dumps(cart), payment=json.dumps(payment), total_usd=f"{total:.2f}", status="AWAITING_GUEST",
            created_at=now.isoformat(),
        ))  # fmt: skip
    note = "The guest approves it with the Approve payment button under your answer (a typed reply doesn't approve it)."
    return {"mandate_id": mandate_id, "status": "AWAITING_GUEST", "total_usd": total, "merchant": MERCHANT,
            "expires": expiry, "note": f"{note} {SANDBOX_NOTE}"}  # fmt: skip


def get(engine: Engine, mandate_id: str):
    ensure(engine)
    with engine.connect() as conn:
        return conn.execute(select(mandates).where(mandates.c.id == mandate_id)).first()


def for_request(engine: Engine, request_id: str):
    ensure(engine)
    with engine.connect() as conn:
        return conn.execute(select(mandates).where(mandates.c.request_id == request_id)).first()


def awaiting(engine: Engine, conversation_id: str) -> list:
    ensure(engine)
    with engine.connect() as conn:
        return conn.execute(select(mandates).where(mandates.c.conversation_id == conversation_id,
                                                  mandates.c.status == "AWAITING_GUEST")).all()  # fmt: skip


def verify(row) -> None:
    """The cart is unchanged since the merchant signed it, the merchant is allowed, the totals agree."""
    cart = json.loads(row.cart)
    if not hmac.compare_digest(cart["merchant_authorization"], sign(cart["contents"])):
        raise MandateError("cart signature doesn't match: the cart was changed")
    if cart["contents"]["merchant_name"] not in ALLOWED_MERCHANTS:
        raise MandateError("merchant not allowed")
    total = cart["contents"]["payment_request"]["details"]["total"]["amount"]["value"]
    paid = json.loads(row.payment)["payment_mandate_contents"]["payment_details_total"]["amount"]["value"]
    if abs(float(total) - float(paid)) > 0.001 or abs(float(total) - float(row.total_usd)) > 0.001:
        raise MandateError("payment total doesn't match the cart")


def decide(engine: Engine, mandate_id: str, conversation_id: str, approve: bool, now: datetime | None = None) -> dict:
    """The guest's own decision, from the chat (never from the model)."""
    now = _now(now)
    row = get(engine, mandate_id)
    if row is None or row.conversation_id != conversation_id:
        raise MandateError("payment not found in this conversation")
    if row.status != "AWAITING_GUEST":
        raise MandateError(f"payment is already {row.status}")
    if not approve:
        return _set(engine, row, "DECLINED", now)
    if datetime.fromisoformat(json.loads(row.cart)["contents"]["cart_expiry"]) < now:
        _set(engine, row, "EXPIRED", now)
        raise MandateError("this payment request expired; ask the concierge again")
    verify(row)
    if spent_today(engine, conversation_id, now) + float(row.total_usd) > SPEND_LIMIT_USD:
        raise MandateError(f"over the sandbox spending limit of ${SPEND_LIMIT_USD:.0f} a day")
    payment = json.loads(row.payment)
    payment["user_authorization"] = sign(
        {"mandate": payment["payment_mandate_contents"], "approved_at": now.isoformat()}
    )
    with engine.begin() as conn:
        conn.execute(update(mandates).where(mandates.c.id == row.id).values(payment=json.dumps(payment)))
    return _set(engine, row, "AUTHORIZED", now)


def _set(engine: Engine, row, status: str, now: datetime) -> dict:
    with engine.begin() as conn:
        conn.execute(update(mandates).where(mandates.c.id == row.id).values(status=status, decided_at=now.isoformat()))
    return {"mandate_id": row.id, "request_id": row.request_id, "status": status, "total_usd": float(row.total_usd)}
