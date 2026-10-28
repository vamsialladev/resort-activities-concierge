# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.1.0] - 2026-10-25
### Added
- Shared guardrails, tracing and ops log from [hotel-ai-platform](https://github.com/vamsialladev/hotel-ai-platform)
  v0.1.2 (`src/concierge/ops.py`, decision 11): input check before the rewrite and the model, output check on the
  answer against the turn's tool results, one trace per message (rewrite, model turns, tool calls), "Reference: ..."
  on errors, Staff → Traces, JSON startup logs, privacy note in the sidebar.
- Red-team suite in CI (`scripts/run_redteam.py`, docs/RED_TEAM.md) and a CycloneDX SBOM artifact.
### Changed
- Staff page: `ADMIN_PASSWORD` (STAFF_PASSWORD still accepted), shared 5-try lockout, hidden until signed in, absent
  without a password.
- FAQ quarantine also uses the shared patterns (red-team rt31).
- `?source=keepawake` visits stop before the database is touched.

## [1.0.0] - 2026-10-24

### Added

- Today & Tomorrow schedule for both properties (14 days from weekly templates), filters for kids, time of day and
  indoor/outdoor, "starting in the next hour", finished sessions marked.
- Concierge chat (Claude Haiku 5.5, five tools): activities with real times, ages, places and prices; cited FAQ
  answers (hybrid BM25 + embeddings, RRF); booking requests that stay PENDING and need the guest's own "yes";
  follow-ups rewritten; streamed answers with a step timeline; saved conversations per anonymous visitor; share
  links; suggested next messages; staff updates in the chat.
- Staff page: password sign-in, approve / decline (books the places, notifies the guest), analytics (top and
  unanswered questions, viewed vs requested, ignored activities, peak times), room QR codes.
- Neon Postgres via `DATABASE_URL` with a small pool and cold-start retries; SQLite when it isn't set.
- Limits per visit, per minute and per day (questions and cost), counted in the database.
- Eval: 61 dev + 15 held-out cases × 3 runs, 36 retrieval questions, re-score gate in CI; business case calculator.
