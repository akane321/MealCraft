# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run lets the variety pass finish (and warms the candidate cache); the warm runs plan as the product does, the variety pass cut at its two seconds. Median and slowest of the warm runs. ADR-0075 targets about 4 s for a common request: a case whose warm median is over it is marked, and no feature is cut to meet it.

Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (Windows). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against ~4 s |
|---|---:|---:|---:|---|
| one-adult | 5.51 | 3.32 | 3.59 | within |
| four-with-vegetarian | 2.9 | 2.88 | 2.93 | within |
| six-tight-budget | 33.18 | 21.99 | 22.99 | over target |
| two-no-oven-ten-days | 4.08 | 4.06 | 4.5 | over target |
| seven-with-young-children | 3.79 | 3.36 | 3.67 | within |

Over target: six-tight-budget, two-no-oven-ten-days.

- `six-tight-budget`: four whole-week beam searches instead of one: the ranked search keeps no week filled with no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`) run as well. Each builds every six-dish dinner of its candidates again (about 90,000 combinations a search, 360,000 real-meal checks in all, half the run) and expands 32 partial weeks by 256 meals a slot (the other half). Upgrade path: share the meal checks between the four searches (they do not depend on the ranking) and price beam states incrementally.

- `two-no-oven-ten-days`: not profiled yet.
