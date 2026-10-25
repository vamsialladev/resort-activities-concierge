# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
