# AP2 sandbox: payment approval for paid activities

**Sandbox only.** No payment processor, no card, no wallet, no real money. The point is the approval flow: an agent
can prepare a payment, but only the guest can authorise it, and only staff can confirm the booking after that.

Code: [`src/concierge/ap2_sandbox.py`](../src/concierge/ap2_sandbox.py). Field names follow the official AP2 models
([google-agentic-commerce/AP2](https://github.com/google-agentic-commerce/AP2) v0.2.0,
`code/sdk/python/ap2/models/mandate.py`).

## The flow

```mermaid
sequenceDiagram
    participant G as Guest (chat)
    participant C as Concierge agent
    participant T as create_booking_request (code)
    participant S as Staff page
    G->>C: "Yes, book the massage tomorrow at 14:00"
    C->>T: activity_id, party_size, guest_confirmed
    T->>T: guest's own words say yes? places left? under the daily limit?
    T->>T: Intent + Cart (signed by the merchant) + Payment mandate, total from the database
    T-->>C: PENDING request + payment AWAITING_GUEST
    C-->>G: "Request sent; please approve the payment below"
    G->>G: Approve payment (sandbox) button
    Note over G: signature, merchant, totals, expiry and limit re-checked
    G-->>S: payment AUTHORIZED
    S->>S: Approve (refused while the payment isn't AUTHORIZED)
    S-->>G: "approved" notice in the chat
```

## The three mandates

| Mandate | What it holds | Who creates it |
|---|---|---|
| `IntentMandate` | the guest's words (first 300 characters), allowed merchant, SKU, refundability, expiry | the tool, in code |
| `CartMandate` | item, party size, total from the database, 15-minute expiry, `merchant_authorization` (signature) | the tool, as the "merchant" |
| `PaymentMandate` | mandate ID, request ID, total, merchant, timestamp; `user_authorization` once the guest approves | the tool; the guest's button signs it |

Signatures are HMAC-SHA256 stand-ins for AP2's JWTs and verifiable credentials (`AP2_SANDBOX_KEY`, a new random key
per process if unset). The official AP2 SDK isn't installed in the app: it pins exact versions of pydantic and
cryptography and lists pytest as a runtime dependency, which a live Streamlit app shouldn't take on.

## Rules, each tested

| Rule | Where | Test |
|---|---|---|
| The amount comes from the database (price × party size), never from text | `tools.create_booking_request`, `ap2_sandbox.prepare` | `tests/test_ap2_sandbox.py`, red team p01, eval n05 |
| Only the resort's activities desk is a merchant | `ap2_sandbox.verify`; the tool has no merchant argument | red team p08 |
| At most `SANDBOX_SPEND_LIMIT_USD` (default $300) authorised per conversation per day | checked when the request is made and again on approval | red team p02, p03; eval n06 |
| Nothing is authorised without the guest pressing Approve | `ap2_sandbox.decide` is called only by the page's button, never by a tool | red team p11 |
| Staff can't approve a paid request until the payment is authorised | `staff.decide` | red team p04 |
| A changed cart is refused | signature check in `verify` | red team p05 |
| Only the conversation that made the payment can approve it | `decide` | red team p06 |
| A cart expires after 15 minutes | `decide` | red team p07 |
| The normal path still works (control) | | red team p09 |

The model has no tool that approves, charges or refunds. It can only create a PENDING request, and the guest's
latest message must say yes (checked in code).

## What a real deployment would add (Roadmap)

- A real payment processor's test mode first, then live keys only after a security review.
- AP2's verifiable credentials instead of HMAC stand-ins, with a key per merchant in a key management service.
- Refunds and cancellations as their own human-approved flow.
