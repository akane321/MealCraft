# Product improvement: full-default household comparison

Five developer households, fixture prices, one run per condition. No held-out data or model calls.
Each condition uses the same product defaults; the only change is enabling 50 annealing proposals.
Distinct dishes below count recipe IDs excluding staples, not near-duplicate or member-mean groups.
Timing covers plan generation and persistence, not HTTP, language-model parsing or live retailer calls.
These single measurements are diagnostic; there is no optimality or statistically significant speed claim.

| Household | SA steps | Planned | Checks pass | Distinct dishes | Worst repeat | Checkout S$ | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| one-adult | 0 | planned | True | 42 | 1 | 416.35 | 10.35 |
| four-with-vegetarian | 0 | planned | True | 48 | 3 | 606.21 | 35.77 |
| six-tight-budget | 0 | planned | True | 56 | 1 | 266.09 | 249.43 |
| two-no-oven-ten-days | 0 | planned | True | 59 | 2 | 682.0 | 9.68 |
| seven-with-young-children | 0 | planned | True | 58 | 4 | 700.91 | 69.03 |
| one-adult | 50 | planned | True | 42 | 1 | 416.35 | 13.66 |
| four-with-vegetarian | 50 | planned | True | 48 | 3 | 606.21 | 48.85 |
| six-tight-budget | 50 | planned | True | 56 | 1 | 266.09 | 299.47 |
| two-no-oven-ten-days | 50 | planned | True | 59 | 2 | 682.0 | 20.55 |
| seven-with-young-children | 50 | planned | True | 58 | 4 | 700.91 | 118.63 |

In 5 of 5 households, distinct dishes, worst repeat and checkout are unchanged.
The table must not be presented as evidence that annealing improves these households.
Investigate proposal acceptance and stage costs before expanding the iteration count or claiming acceptance.

Raw JSON retains every check and the planned dishes. A passing check is not proof of user preference.
The ten-day household exercises two shopping trips; this does not replace the separate 14-day regression suite.

Source commit: `ec0bcdde39fa8de11da59d5e478f62dea14fb0bd`.
Reproduce with `python scripts/product_household_comparison.py --output <fresh-directory>`
and `python scripts/summarize_product_households.py <fresh-directory>`.
