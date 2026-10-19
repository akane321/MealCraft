# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run lets the variety pass finish (and warms the candidate cache); the warm runs plan as the product does, the variety pass cut at its two seconds. Median and slowest of the warm runs. ADR-0075 targets about 4 s for a common request: a case whose warm median is over it is marked, and no feature is cut to meet it.

Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (Windows). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against ~4 s |
|---|---:|---:|---:|---|
| one-adult | 5.11 | 2.76 | 3.33 | within |
| four-with-vegetarian | 2.71 | 2.69 | 3.09 | within |
| six-tight-budget | 31.74 | 20.95 | 20.95 | over target |
| two-no-oven-ten-days | 3.29 | 3.73 | 3.74 | within |
| seven-with-young-children | 3.48 | 3.04 | 3.48 | within |

Over target: six-tight-budget.

- `six-tight-budget`: four whole-week beam searches instead of one: the ranked search keeps no week filled with no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`) run as well. Each builds every six-dish dinner of its candidates again (about 90,000 combinations a search, 360,000 real-meal checks in all, half the run) and expands 32 partial weeks by 256 meals a slot (the other half). Upgrade path: share the meal checks between the four searches (they do not depend on the ranking) and price beam states incrementally.
