# Concierge agent eval: heldout (2026-10-26)

- Model claude-haiku-5-5, effort low, retrieval hybrid · 15 cases × 3 runs · prices $0.1 / $0.5 per million tokens (in / out) · pinned date 2026-11-02 08:15

| Metric | Result |
|---|---|
| All checks pass | **93% (42/45)** (runs: 93% (14/15), 93% (14/15), 93% (14/15)) |
| Safety cases (injection, booking flow, wrong property, stay lookup) | **100% (15/15)** |
| Same verdict in every run | 15/15 cases |
| Latency per message (all model turns + tools) | p50 3.35 s, p95 8.36 s |
| Tool calls / model calls per message | 1.1 / 2.2 |
| Cost per 1,000 messages | $0.78 |

| Check | Pass |
|---|---|
| cite | 100% (12/12) |
| claim_not | 100% (3/3) |
| must | 90% (27/30) |
| must_not | 100% (6/6) |
| no_promise | 100% (9/9) |
| no_tools | 100% (3/3) |
| request | 100% (12/12) |
| request_args | 100% (3/3) |
| tools | 100% (21/21) |

| Category | Pass |
|---|---|
| activities | 100% (6/6) |
| booking | 100% (6/6) |
| faq | 80% (12/15) |
| followup | 100% (3/3) |
| injection | 100% (3/3) |
| language | 100% (3/3) |
| off_topic | 100% (3/3) |
| stay | 100% (3/3) |
| wrong_property | 100% (3/3) |

Failing (failed checks): h11(must:0)
