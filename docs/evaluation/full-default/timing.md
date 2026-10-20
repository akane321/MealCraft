# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run lets the variety pass finish (and warms the candidate cache); the warm runs plan as the product does, the variety pass cut at its two seconds. Median and slowest of the warm runs. ADR-0075 targets about 4 s for a common request: a case whose warm median is over it is marked, and no feature is cut to meet it.

Machine: x86_64 (Linux). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against ~4 s |
|---|---:|---:|---:|---|
| one-adult | 13.98 | 7.73 | 7.89 | over target |
| four-with-vegetarian | 21.44 | 21.79 | 23.12 | over target |
| six-tight-budget | 217.51 | 115.44 | 120.39 | over target |
| two-no-oven-ten-days | 15.68 | 9.3 | 10.21 | over target |
| seven-with-young-children | 13.95 | 12.78 | 13.46 | over target |

Over target: one-adult, four-with-vegetarian, six-tight-budget, two-no-oven-ten-days, seven-with-young-children.

- `one-adult`: not profiled yet.

- `four-with-vegetarian`: not profiled yet.

- `six-tight-budget`: four whole-week beam searches instead of one: the ranked search keeps no week filled with no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`) run as well. Each builds every six-dish dinner of its candidates again (about 90,000 combinations a search, 360,000 real-meal checks in all, half the run) and expands 32 partial weeks by 256 meals a slot (the other half). Upgrade path: share the meal checks between the four searches (they do not depend on the ranking) and price beam states incrementally.

- `two-no-oven-ten-days`: not profiled yet.

- `seven-with-young-children`: not profiled yet.
