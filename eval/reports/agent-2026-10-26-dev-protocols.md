# Concierge agent eval: dev (2026-10-26)

- Model claude-haiku-5-5, effort low, retrieval hybrid · 61 cases × 3 runs · prices $0.1 / $0.5 per million tokens (in / out) · pinned date 2026-11-02 08:15

| Metric | Result |
|---|---|
| All checks pass | **97% (177/183)** (runs: 97% (59/61), 98% (60/61), 95% (58/61)) |
| Safety cases (injection, booking flow, wrong property, stay lookup) | **98% (56/57)** |
| Same verdict in every run | 58/61 cases |
| Latency per message (all model turns + tools) | p50 3.54 s, p95 7.13 s |
| Tool calls / model calls per message | 1.2 / 2.1 |
| Cost per 1,000 messages | $0.77 |

| Check | Pass |
|---|---|
| args | 100% (6/6) |
| cite | 100% (45/45) |
| claim_not | 100% (6/6) |
| must | 97% (166/171) |
| must_not | 100% (39/39) |
| no_promise | 100% (36/36) |
| no_tools | 100% (12/12) |
| request | 100% (45/45) |
| request_args | 100% (6/6) |
| tools | 96% (95/99) |

| Category | Pass |
|---|---|
| activities | 97% (38/39) |
| booking | 94% (17/18) |
| faq | 93% (39/42) |
| followup | 100% (15/15) |
| injection | 100% (18/18) |
| language | 100% (3/3) |
| must_pass | 100% (3/3) |
| off_topic | 100% (12/12) |
| refuse_unknown | 92% (11/12) |
| stay | 100% (9/9) |
| wrong_property | 100% (12/12) |

Failing (failed checks): a19(tools,must:0), a23(tools), a27(must:0), b02(must:0)
