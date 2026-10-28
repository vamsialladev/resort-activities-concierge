# Concierge agent eval: protocols (2026-10-26)

- Model claude-haiku-5-5, effort low, retrieval hybrid · 6 cases × 3 runs · prices $0.1 / $0.5 per million tokens (in / out) · pinned date 2026-11-02 08:15

| Metric | Result |
|---|---|
| All checks pass | **100% (18/18)** (runs: 100% (6/6), 100% (6/6), 100% (6/6)) |
| Safety cases (injection, booking flow, wrong property, stay lookup) | **n/a** |
| Same verdict in every run | 6/6 cases |
| Latency per message (all model turns + tools) | p50 5.92 s, p95 11.71 s |
| Tool calls / model calls per message | 1.8 / 2.8 |
| Cost per 1,000 messages | $1.14 |

| Check | Pass |
|---|---|
| cite | 100% (6/6) |
| claim_not | 100% (6/6) |
| must | 100% (24/24) |
| must_not | 100% (3/3) |
| no_promise | 100% (15/15) |
| request | 100% (9/9) |
| request_args | 100% (3/3) |
| tools | 100% (12/12) |

| Category | Pass |
|---|---|
| a2a_handoff | 100% (3/3) |
| ap2_payment | 100% (9/9) |
| mcp_policy | 100% (6/6) |

Failing (failed checks): none

Re-scored without the model after a grader fix: 3 verdict(s) changed (n04 run 1, n04 run 2, n04 run 3).
