# Decisions

Each one: context, decision, tradeoff, result.

## 1. Streamlit on Community Cloud with Neon, not FastAPI on Render

- **Context:** the plan (PROMPTS.md P2) said FastAPI, server-sent events and a hand-built front end on Render's
  $7/month Starter instance. The owner chose not to pay for hosting and asked for a multi-page Streamlit app on
  Streamlit Community Cloud (free), with Neon's free Postgres for anything that must persist.
- **Decision:** four Streamlit pages (Today & Tomorrow, Concierge chat, Staff, About), SQLAlchemy Core over Neon
  via `DATABASE_URL`, and a local SQLite file whenever `DATABASE_URL` isn't set, so tests, CI and anyone cloning
  the repo never need Neon.
- **Tradeoff:** no embeddable chat widget and no custom front end; Streamlit Cloud sleeps when idle (the keep-awake
  workflow pings it) and its free tier has about 1 GB of memory. Streaming still works (`st.write_stream`).
- **Result:** $0 a month to host. The same code runs on Postgres and SQLite; the tests run on SQLite.

## 2. A small pool and a retry for Neon's cold start

- **Context:** Neon's free tier suspends the database after a few idle minutes; the first connection then waits
  while it wakes, and a pooled connection can be closed underneath the app.
- **Decision:** pool of 2 + 2 overflow, `pool_pre_ping`, `pool_recycle=300`, a 10 s connect timeout, and
  `db.connect()` retrying 4 times (1 s, 2 s, 4 s). Every page shows "Waking up the database..." while it waits, and
  a friendly "refresh in a few seconds" if it still can't connect.
- **Tradeoff:** a cold visitor may wait several seconds once.
- **Result:** measured from this machine: first connection 1.8 s. Retry logic is unit-tested with a fake engine.

## 3. Hybrid retrieval (BM25 + embeddings, RRF), because it fits and it finds paraphrases

- **Context:** the owner's rule: hybrid if it fits Streamlit Cloud's memory, otherwise BM25 with the trade-off
  measured.
- **Decision:** fastembed (ONNX, no PyTorch) with BAAI/bge-small-en-v1.5, fused with BM25 by reciprocal rank
  fusion (k=60), filtered by property. If the model can't load, retrieval falls back to BM25 and logs it. The index
  warms up in a background thread when the app starts.
- **Tradeoff:** measured on this machine: process memory 34 MB with BM25 → 294 MB with the model loaded; 10.6 s to
  load; 0.5 ms → 13.8 ms per search. Comfortably inside 1 GB.
- **Result:** on 30 labelled questions that share words with the documents, both modes found the right passage in
  the top 4 (30/30; MRR 0.93 BM25, 0.95 hybrid). That alone wouldn't justify 260 MB, so I wrote 6 meaning-only
  paraphrases ("my little one is allergic to peanuts", "can I bring my pup"), added after that first measurement
  and labelled as such: BM25 0/6, hybrid 5/6 (missed "I feel dizzy and out of breath up here" → Altitude). Guests
  write like the paraphrases, so hybrid is on. CI gates both: 30/30 keyword in both modes, at least 5/6 paraphrases
  with embeddings.

## 4. The model proposes; the guest's own "yes" and a person decide

- **Context:** "never confirm a booking, refund or free item" is the engagement's hard rule, and a request the guest
  didn't ask for is a bad surprise at the activities desk.
- **Decision:** no tool can confirm, charge or refund. `create_booking_request` writes `PENDING`, and it refuses
  unless `guest_confirmed` is true AND the guest's latest message says yes ("yes", "sure", "go ahead", "request
  it", "sí") without a "no / wait / not yet". Staff approve or decline on the Staff page; approval re-checks
  capacity and books the places in one transaction, and the guest's chat gets an update.
- **Tradeoff:** "Book the kids club for my two kids" doesn't create a request on its own: the concierge confirms
  the details and asks first. One extra turn.
- **Result:** unit tests for the consent check (including a model that calls the tool unprompted); eval cases b01,
  b04 and h03 create exactly one request for the right session and party size; b02, b03, b10, h10 create none.

## 5. Anonymous visitors, redacted storage

- **Context:** conversations should come back later and be shareable, without accounts or personal data.
- **Decision:** a random visitor ID in the page address (`?v=...`); conversations and messages in the database;
  every stored message, title and analytics event goes through the stage 1 redaction first (emails, phones, card
  numbers, booking references, names after "my name is"). Share links use a separate random token and show the
  stored (redacted) text read-only.
- **Tradeoff:** a reopened conversation shows "[name]" or a booking pseudonym where the guest typed one; anyone with
  the `?v=` address sees that visitor's list (documented in SECURITY.md).
- **Result:** tests plant a name, email, phone and booking reference and check none reaches the database.

## 6. Follow-ups rewritten, but a plain "yes" isn't

- **Context:** "What about the afternoon?" needs the earlier turn. "Yes please" is an answer, not a question.
- **Decision:** the stage 1/8 rewrite (one short Haiku call, only when a cheap rule says it's a follow-up), shown as
  "Understood as". Short affirmative replies skip it, so the consent check sees the guest's own words. The agent
  also gets the last 6 turns as plain text.
- **Tradeoff:** an extra call on follow-ups; earlier tool results aren't re-sent, so the model sometimes calls a
  tool again (cheap, and the data is fresh).
- **Result:** follow-up cases m01–m06 and h09: 15/15 dev and 3/3 held-out across 3 runs.

## 7. Analytics from real use only

- **Context:** the Staff page needs top questions, unanswered questions, viewed vs requested, ignored activities
  and peak times. Seeding fake usage would make the dashboard look busy and be untrue.
- **Decision:** events are written by real use of the demo (questions, "unanswered" when the FAQ search found
  nothing or the answer says it doesn't know, views from the schedule and from activities the concierge listed,
  requests). An empty dashboard says so.
- **Tradeoff:** a fresh deployment shows empty charts until people use it.
- **Result:** unit tests check each query on planted events.

## 8. Daily caps in the database

- **Context:** stages 7 and 8 keep their daily counters in a file, which resets when Streamlit Cloud restarts.
- **Decision:** a `usage_daily` row per day in the same database, updated after each message.
- **Tradeoff:** one extra write per message.
- **Result:** with Neon, the caps survive restarts.

## 9. Score the model before the grader (pilot run, then the real runs)

- **Context:** a new grader has bugs, and every failed check costs a read of the answer.
- **Decision:** one pilot pass over the 61 dev cases first, every failure read by hand, then 3 dev runs and 3
  held-out runs. Saved answers are re-scored without the model whenever the grader changes; every report is kept.
- **Tradeoff:** about $0.04 for the pilot.
- **Result:** pilot 93% (57/61): one wrong label (a trek with only one place left; the concierge was right to say
  so) and three patterns that matched the wrong thing ("08:00" at the end of yoga, "18:00" in "cancelled by
  18:00", a refusal containing "helicopter tour at"). Dev after fixes: 100% (183/183). Held-out: 84% as measured,
  93% after the same kind of fix ("I can't tell guests the spa is free" is a refusal): claims are now judged per
  sentence, skipping negated ones, with the real phrasings as tests. The two held-out cases with the dev bug
  shapes were fixed before their first run. One real miss stays: h11, the cooking class age is only on the
  activity and the model searched only the FAQ.

## 10. The eval's temporary database on Windows

- **Context:** the first 3-run dev eval crashed in run 2: Windows still held the SQLite file when the temporary
  folder was deleted.
- **Decision:** dispose the engine and ignore cleanup errors for the temporary folder.
- **Tradeoff:** a few small files can be left in the temp folder.
- **Result:** the re-run finished; the crashed run saved nothing (results are written at the end), so no number
  from it is reported.

## 11. Shared guardrails and tracing; the Staff page is this app's Admin page (2026-10-25)
- **Context:** the final plan adds guardrails, a red team, tracing and one ops log to every hotel app, and an Admin
  page (for the concierge, the Staff page) behind `ADMIN_PASSWORD` with a lockout.
- **Decision:** wire hotel-ai-platform v0.1.3 in `src/concierge/ops.py`; the rewrite, each model turn and each tool
  call are spans. The Staff page reads `ADMIN_PASSWORD` (the older `STAFF_PASSWORD` still works), uses the shared
  5-try lockout, stays out of the menu until staff sign in at `/staff`, doesn't exist without a password, and gets a
  Traces tab. The FAQ quarantine also uses the shared patterns.
- **Trade-off:** keep-awake visits stop before the database is touched (so Neon sleeps), which means a keep-awake
  visit doesn't warm the schedule either.
- **Result:** red team: shared 48/48; own held-out 15/18, three listed gaps that the tools already stop. Saved eval
  answers: the output check changes 0 of 228; the FAQ passages the model reads are identical before and after.

## 12. Hotel-wide policy over MCP, as the guest role (2026-10-26)
- **Context:** guests ask the concierge about pets, check-out, parking and the loyalty programme. Those rules live in
  the hotel group's documents, served by the stage 7 tool server. Copying them into the concierge's FAQ would drift.
- **Decision:** a `hotel_policy` tool calls `search_policy` on hotel-tools-mcp over an MCP session (in-memory
  transport, the server in-process, because Streamlit Community Cloud runs one service), as the **guest** role, so
  the server's role checks, tenant scope, rate limit and audit log apply. Passages come back quarantined and are
  cited like FAQ passages.
- **Trade-off:** in-process, not over the network: the same code would talk to a remote MCP server, but the demo
  doesn't show one. The pin is a commit archive until the stage 7 PR is merged and tagged.
- **Result:** connecting as a guest found a real gap in stage 7: `search_policy` returned a "CONFIDENTIAL - INTERNAL
  STAFF USE ONLY" passage to guests. Fixed there (hotel-tools-mcp decision 13). It also found my own data
  contradicting itself: this FAQ said dogs only in cabins, the hotel's pet policy says any size, up to 2 per room.
  The FAQ now agrees and points to the policy (decision 15).

## 13. Every answer as AG-UI events (2026-10-26)
- **Context:** the plan asks for AG-UI events for the step timeline.
- **Decision:** `src/concierge/agui.py` builds each run's events with the official `ag-ui-protocol` types and stores
  them with the answer; the Steps panel is drawn from them (`agui.timeline`), and guest and staff decisions are
  CUSTOM events. Schema: [AGUI_EVENTS.md](AGUI_EVENTS.md).
- **Trade-off:** stored, not streamed: Streamlit can't serve an SSE endpoint. An AG-UI client could replay a run, not
  watch it live.
- **Result:** a test that validates every stored event against the official types and checks their order found the
  answer's text message closing after `STATE_SNAPSHOT`; fixed, and the test fails without the fix.

## 14. AP2 sandbox mandates for paid activities (2026-10-26)
- **Context:** the plan asks for an AP2 sandbox with a spend limit and a human approval; no real money anywhere.
- **Decision:** a paid request gets Intent, Cart (signed) and Payment mandates with the official AP2 field names; the
  total comes from the database; only the guest's button authorises it; staff can't approve the booking before
  that; $300 a day per conversation; carts expire in 15 minutes. HMAC stand-ins for AP2's signatures. The official
  SDK isn't installed in the app (exact pins on pydantic and cryptography). [AP2_SANDBOX.md](AP2_SANDBOX.md).
- **Trade-off:** a sandbox proves the approval flow, not a payment integration.
- **Result:** red team 11 payment cases, each stopped for the right reason. The control case (a normal approval)
  first failed and showed that 6 attack cases had "passed" because the activity didn't run that day; the runner now
  fails a case whose setup fails. The first eval run showed one answer telling the guest to "reply" to approve; the
  tool's note now names the button.

## 15. Guest-services hand-off over A2A, with a fallback (2026-10-26)
- **Context:** room moves, complaints and billing belong to the stage 2 Guest Request Agent, which drafts a reply
  and staff tasks for review.
- **Decision:** a `guest_services` tool sends the request over A2A (official `a2a-sdk`: agent card, JSON-RPC, bearer
  token) to stage 2's A2A server, with the property and the guest's words (contact details already replaced), no
  name or room. The concierge gets back whether it was handed off, a reference and what was understood, never the
  draft (that's for staff). If `A2A_URL`/`A2A_TOKEN` aren't set, the SDK isn't installed, or the agent fails or
  times out, the tool returns a fallback and the concierge points to the front desk.
- **Trade-off:** the free live demo always takes the fallback: Streamlit Community Cloud can't host stage 2's A2A
  server. `a2a-sdk` is optional (`requirements-agents.txt`), so the live app doesn't install it.
- **Result:** tested against an in-process A2A server (handed off, failed task, agent down, not configured) and
  against stage 2's real server app with its process stubbed (right token handed off, wrong token fell back). Two
  dev labels from before the new tools were updated: a19 (the dog rule above) and a27 (a late check-out now gets a
  cited policy answer instead of "ask the front desk").
