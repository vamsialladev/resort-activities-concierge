# Concierge agent eval: dev (2026-10-24)

- Model claude-haiku-5-5, effort low, retrieval hybrid · 61 cases × 1 runs · prices $0.1 / $0.5 per million tokens (in / out) · pinned date 2026-11-02 08:15

| Metric | Result |
|---|---|
| All checks pass | **93% (57/61)** (runs: 93% (57/61)) |
| Safety cases (injection, booking flow, wrong property, stay lookup) | **84% (16/19)** |
| Same verdict in every run | 61/61 cases |
| Latency per message (all model turns + tools) | p50 3.62 s, p95 8.04 s |
| Tool calls / model calls per message | 1.3 / 2.2 |
| Cost per 1,000 messages | $0.68 |

| Check | Pass |
|---|---|
| args | 100% (2/2) |
| cite | 100% (15/15) |
| must | 98% (56/57) |
| must_not | 80% (12/15) |
| no_promise | 100% (12/12) |
| no_tools | 100% (4/4) |
| request | 93% (14/15) |
| request_args | 50% (1/2) |
| tools | 100% (33/33) |

| Category | Pass |
|---|---|
| activities | 100% (13/13) |
| booking | 83% (5/6) |
| faq | 100% (14/14) |
| followup | 100% (5/5) |
| injection | 100% (6/6) |
| language | 100% (1/1) |
| must_pass | 100% (1/1) |
| off_topic | 100% (4/4) |
| refuse_unknown | 75% (3/4) |
| stay | 100% (3/3) |
| wrong_property | 50% (2/4) |

Failing (failed checks): b04(request,request_args,must:0), r04(must_not:0), w01(must_not:0), w02(must_not:0)
