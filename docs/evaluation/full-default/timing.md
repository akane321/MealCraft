# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run lets the variety pass finish (and warms the candidate cache); the warm runs plan as the product does, the variety pass cut at its two seconds. Median and slowest of the warm runs. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, a complex one may take up to about 60 s, and only past that is a case marked over. A case is never cut short to meet either figure, and no feature is dropped to make one faster.

Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (Windows). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against the ADR-0079 guidance |
|---|---:|---:|---:|---|
| one-adult | 8.63 | 5.47 | 5.96 | within the guidance for a complex request |
| four-with-vegetarian | 19.5 | 19.55 | 20.25 | within the guidance for a complex request |
| six-tight-budget | 177.27 | 78.71 | 82.57 | over ~60 s |
| two-no-oven-ten-days | 7.3 | 6.94 | 7.13 | within the guidance for a complex request |
| seven-with-young-children | 10.55 | 10.41 | 11.05 | within the guidance for a complex request |

Over ~60 s: six-tight-budget.

- `one-adult` (within the guidance for a complex request): not profiled yet.

- `four-with-vegetarian` (within the guidance for a complex request): not profiled yet.

- `six-tight-budget` (over ~60 s): four whole-week beam searches instead of one: the ranked search keeps no week filled with no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`) run as well. Each builds every six-dish dinner of its candidates again (about 90,000 combinations a search, 360,000 real-meal checks in all, half the run) and expands 32 partial weeks by 256 meals a slot (the other half). Upgrade path: share the meal checks between the four searches (they do not depend on the ranking) and price beam states incrementally. The owner accepted this case's current time on 2026-10-20 and made the speed-up optional (ADR-0079 section 5), so being over the line here is a known exception, not a regression to fix before merging.

- `two-no-oven-ten-days` (within the guidance for a complex request): not profiled yet.

- `seven-with-young-children` (within the guidance for a complex request): not profiled yet.
