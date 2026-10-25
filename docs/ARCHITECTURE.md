# Architecture

## System

```mermaid
flowchart LR
    G[Guest<br/>room QR code] --> UI[Streamlit pages<br/>Today & Tomorrow, Concierge chat]
    S[Staff] --> SP[Staff page<br/>password, approve/decline,<br/>analytics, QR codes]
    UI --> LIM[limits.py<br/>per visit, per minute,<br/>daily questions and cost]
    LIM --> RW[rewrite.py<br/>follow-up to standalone<br/>Claude Haiku 5.5, if needed]
    RW --> AG[agent.py<br/>tool loop, max 6 turns<br/>Claude Haiku 5.5, streamed]
    AG --> T[tools.py<br/>search_activities, check_availability,<br/>get_guest_booking, create_booking_request,<br/>search_faq]
    T --> RET[retrieval.py<br/>BM25 + bge-small, RRF<br/>property filter, guard.quarantine]
    T --> DB[(Neon Postgres or SQLite<br/>activities, stays, booking_requests,<br/>conversations, messages, events, usage_daily)]
    RET --> DOCS[data/docs<br/>FAQ and policies]
    AG --> CH[chats.py<br/>redacted messages,<br/>share tokens]
    CH --> DB
    AG --> AN[analytics.py<br/>redacted events]
    AN --> DB
    SP --> ST[staff.py<br/>decide: book places,<br/>notice to the guest]
    ST --> DB
```

## A message, start to finish

```mermaid
sequenceDiagram
    actor G as Guest
    participant UI as Concierge page
    participant A as agent.respond
    participant L as Claude Haiku 5.5
    participant T as tools
    participant D as Database
    G->>UI: "My family has two kids. What can we do tomorrow morning?"
    UI->>UI: limits.blocked() (visit, minute, day)
    UI->>A: message, last 6 turns, property, room
    A->>L: rules + date + tools + conversation (stream)
    L-->>A: tool_use search_activities(tomorrow, kids, morning)
    A->>T: search_activities
    T->>D: SELECT activities for the property and date
    D-->>A: Turtle talk 08:30, Kids club 09:30 (ages, places, price)
    A->>L: tool_result
    L-->>A: tool_use search_faq("kids club policy")
    A->>T: search_faq (hybrid, property-filtered, quarantined)
    A->>L: tool_result (passages with cite_as)
    L-->>UI: answer with times, ages and [Kids Club Policy ...] (streamed)
    G->>UI: "Yes, please request the kids club for our two kids."
    UI->>A: message (not rewritten: it's a yes)
    L-->>A: check_availability, then create_booking_request(guest_confirmed=true)
    A->>T: create_booking_request: checks the guest's own "yes", the places left
    T->>D: INSERT booking_requests status=PENDING
    UI->>D: messages (redacted), events, usage_daily
    Note over UI,D: Staff page: approve -> places booked, notice in the guest's chat
```

## Components

| Module | Job |
|---|---|
| `app.py` | Navigation, the shared-conversation view |
| `pages/schedule.py` | Today & Tomorrow with filters, "starting in the next hour", finished sessions, into the chat |
| `pages/concierge.py` | Chat: streaming, steps, sources, history, share link, staff updates (refreshes every 20 s) |
| `pages/staff.py` | Sign-in, pending requests, analytics, room QR codes |
| `pages/about.py` | What it is, how to try it, the latest eval reports |
| `src/concierge/agent.py` | The tool-use loop and the system prompt |
| `src/concierge/tools.py` | The five tools, their schemas, the consent check |
| `src/concierge/retrieval.py` | Passages from `data/docs`, BM25 + embeddings + RRF, quarantine |
| `src/concierge/rewrite.py` | Follow-up → standalone question |
| `src/concierge/db.py` | Tables, engine (pool, pre-ping), `connect()` with retries |
| `src/concierge/seed.py` | Weekly templates → 14-day schedule; demo stays re-dated around today |
| `src/concierge/chats.py` | Conversations, redacted messages, share tokens |
| `src/concierge/staff.py` | Password check, approve/decline, the guest notice |
| `src/concierge/analytics.py` | Events and the Staff page's queries |
| `src/concierge/limits.py` | Session and daily limits (daily counters in the database) |
| `src/concierge/qr.py` | Room QR codes (segno) |
| `eval/run_eval.py` | Agent eval (76 cases), retrieval eval (36 questions), re-scoring |

## Scaling path

1. Connection pooling through Neon's pooler endpoint, and more Streamlit replicas behind it; limits are already in
   the database, so they hold across replicas.
2. A `hotel_group_id` on every table and row-level security, for more than one hotel group.
3. Embeddings computed once at build time and stored (pgvector) instead of at every start.
4. The tools behind the stage 7 MCP server, so staff tools and guest tools share one role-checked layer.
