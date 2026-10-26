# Concierge agent eval: dev (2026-10-26)

- Model claude-haiku-5-5, effort low, retrieval hybrid · 61 cases × 3 runs · prices $0.1 / $0.5 per million tokens (in / out) · pinned date 2026-11-02 08:15

| Metric | Result |
|---|---|
| All checks pass | **99% (181/183)** (runs: 98% (60/61), 100% (61/61), 98% (60/61)) |
| Safety cases (injection, booking flow, wrong property, stay lookup) | **100% (57/57)** |
| Same verdict in every run | 60/61 cases |
| Latency per message (all model turns + tools) | p50 3.73 s, p95 7.65 s |
| Tool calls / model calls per message | 1.2 / 2.1 |
| Cost per 1,000 messages | $0.76 |

| Check | Pass |
|---|---|
| args | 100% (6/6) |
| cite | 100% (45/45) |
| claim_not | 100% (6/6) |
| must | 100% (171/171) |
| must_not | 100% (39/39) |
| no_promise | 100% (36/36) |
| no_tools | 100% (12/12) |
| request | 100% (45/45) |
| request_args | 100% (6/6) |
| tools | 98% (94/96) |

| Category | Pass |
|---|---|
| activities | 95% (37/39) |
| booking | 100% (18/18) |
| faq | 100% (42/42) |
| followup | 100% (15/15) |
| injection | 100% (18/18) |
| language | 100% (3/3) |
| must_pass | 100% (3/3) |
| off_topic | 100% (12/12) |
| refuse_unknown | 100% (12/12) |
| stay | 100% (9/9) |
| wrong_property | 100% (12/12) |

Failing (failed checks): a23(tools)
