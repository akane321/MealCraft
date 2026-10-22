# Meal-combination cap sweep

> Developer data, diagnostic: not held-out evidence. Fixture prices, no model call, no held-out data.

`product_path.MEAL_COMBINATIONS` caps the dish combinations a meal's first widening step builds, which sets how many dishes each of a meal's roles keeps (`meal_beam.integer_root` of the cap per role, never fewer than three). It is a search-breadth parameter: removing it in task 15 planned no better and took up to hours. The owner asked (2026-10-22) for the smallest cap that does not materially reduce plan quality against the earlier 16,384 (ADR-0083).

## Method

`python scripts/combination_cap_sweep.py run --cap N` for each cap, one process at a time, then `python scripts/combination_cap_sweep.py report`. Scenarios: every full-default case (report run, then one warm run timed), every shared-dish case in the shared arrangement (planned twice, the second timed) and every v3 meal-day-week developer episode (`mdw-dev-*`, once; each loads its own pool, so its time includes that). Every cap uses the exact integer root, so a seven-role meal keeps four dishes a role at 16,384 (`int(16384 ** (1 / 7))` gave three).

A cap is materially worse than 16,384 when any of these fails:

- no scenario changes from planning to refusing;
- 0 safety violations;
- no scenario loses more than 1 distinct dish, and the mean distinct is within 1%;
- the worst repeat is never higher;
- no scenario's total price is more than 1% higher;

**Chosen cap: 16,384**, the smallest that passes every one.

A cap matters only through the dishes each role keeps: at most `candidates_per_role` (8), else the integer root. Up to 8,192 every smaller cap loses on some scenario. Between 8,192 and 16,384 only six-role meals (4 dishes a role, 5 from 15,625) and seven-role meals change, and a seven-role meal keeps 3 dishes a role at any cap below 16,384 = 4^7, as at 8,192, where `seven-with-young-children` repeats a dish three times and costs 7% more. So no value between them was swept.

## Summary

| Cap | Planned | Safety violations | Failed checks | Mean distinct | Worst repeat | Total price (S$) | Largest price rise | Total time (s) | Slowest (s) | Materially worse |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1,024 | 35/36 | 0 | 0 | 28.63 | 14 | 13800.26 | +32.52% | 261.4 | 84.82 | full-default/four-with-vegetarian: price S$655.79 > 1% over S$567.89; full-default/six-tight-budget: price S$282.33 > 1% over S$240.27; full-default/two-no-oven-ten-days: price S$709.88 > 1% over S$642.77; full-default/seven-with-young-children: worst repeat 3 > 2; full-default/seven-with-young-children: price S$739.20 > 1% over S$687.91; shared-dish/four-one-vegetarian: price S$650.11 > 1% over S$535.59; shared-dish/two-one-vegetarian: 2 fewer distinct dishes; shared-dish/two-one-vegetarian: worst repeat 2 > 1; shared-dish/two-one-vegetarian: price S$719.71 > 1% over S$644.50; shared-dish/with-a-child: price S$300.17 > 1% over S$276.49; shared-dish/weekday-lunch-away: price S$633.54 > 1% over S$527.27; shared-dish/weekend-guest: price S$647.79 > 1% over S$567.20; shared-dish/peanut-whole-household: price S$310.40 > 1% over S$296.25; shared-dish/six-one-vegetarian: worst repeat 2 > 1; shared-dish/tight-budget: price S$111.75 > 1% over S$84.33; mdw/mdw-dev-004: 2 fewer distinct dishes; mdw/mdw-dev-004: worst repeat 2 > 1 |
| 2,048 | 35/36 | 0 | 0 | 28.6 | 14 | 13733.34 | +32.52% | 248.0 | 91.25 | full-default/four-with-vegetarian: price S$655.79 > 1% over S$567.89; full-default/six-tight-budget: price S$282.33 > 1% over S$240.27; full-default/two-no-oven-ten-days: price S$694.81 > 1% over S$642.77; full-default/seven-with-young-children: worst repeat 3 > 2; full-default/seven-with-young-children: price S$739.20 > 1% over S$687.91; shared-dish/four-one-vegetarian: price S$650.11 > 1% over S$535.59; shared-dish/two-one-vegetarian: worst repeat 2 > 1; shared-dish/with-a-child: price S$300.17 > 1% over S$276.49; shared-dish/weekday-lunch-away: price S$633.54 > 1% over S$527.27; shared-dish/weekend-guest: price S$647.79 > 1% over S$567.20; shared-dish/peanut-whole-household: price S$310.40 > 1% over S$296.25; shared-dish/six-one-vegetarian: worst repeat 2 > 1; shared-dish/tight-budget: price S$111.75 > 1% over S$84.33; mdw/mdw-dev-004: 3 fewer distinct dishes; mdw/mdw-dev-004: worst repeat 3 > 1 |
| 4,096 | 35/36 | 0 | 0 | 28.69 | 14 | 13363.28 | +23.40% | 286.7 | 103.36 | full-default/seven-with-young-children: worst repeat 3 > 2; full-default/seven-with-young-children: price S$739.20 > 1% over S$687.91; shared-dish/with-a-child: price S$311.76 > 1% over S$276.49; shared-dish/peanut-whole-household: price S$321.08 > 1% over S$296.25; shared-dish/peanut-only-mei-avoids: price S$323.02 > 1% over S$316.58; shared-dish/mixed-diets: price S$254.41 > 1% over S$246.51; shared-dish/tight-budget: price S$104.06 > 1% over S$84.33 |
| 8,192 | 35/36 | 0 | 0 | 28.51 | 14 | 13284.35 | +7.46% | 299.2 | 95.36 | full-default/four-with-vegetarian: 2 fewer distinct dishes; full-default/seven-with-young-children: worst repeat 3 > 2; full-default/seven-with-young-children: price S$739.20 > 1% over S$687.91; shared-dish/weekend-guest: 2 fewer distinct dishes |
| 16,384 | 35/36 | 0 | 0 | 28.66 | 14 | 13296.18 | +0.00% | 370.5 | 129.45 | no |

## Per scenario

Distinct dishes / worst repeat / price (S$) / seconds; `refused` when no week was planned.

| Scenario | 1,024 | 2,048 | 4,096 | 8,192 | 16,384 |
| --- | --- | --- | --- | --- | --- |
| full-default/one-adult | 42 / 1 / 390.11 / 3.18 | 42 / 1 / 397.72 / 3.77 | 42 / 1 / 405.82 / 4.6 | 42 / 1 / 405.82 / 4.69 | 42 / 1 / 405.82 / 4.4 |
| full-default/four-with-vegetarian | 50 / 2 / 655.79 / 9.01 | 50 / 2 / 655.79 / 9.58 | 50 / 2 / 547.72 / 12.28 | 48 / 2 / 545.01 / 14.54 | 50 / 2 / 567.89 / 18.43 |
| full-default/six-tight-budget | 56 / 1 / 282.33 / 84.82 | 56 / 1 / 282.33 / 91.25 | 56 / 1 / 238.08 / 103.36 | 56 / 1 / 238.08 / 95.36 | 56 / 1 / 240.27 / 129.45 |
| full-default/two-no-oven-ten-days | 59 / 2 / 709.88 / 3.36 | 58 / 2 / 694.81 / 3.82 | 59 / 2 / 642.77 / 5.47 | 59 / 2 / 642.77 / 4.98 | 59 / 2 / 642.77 / 4.9 |
| full-default/seven-with-young-children | 57 / 3 / 739.20 / 8.32 | 57 / 3 / 739.20 / 9.05 | 57 / 3 / 739.20 / 8.88 | 57 / 3 / 739.20 / 8.13 | 58 / 2 / 687.91 / 35.95 |
| shared-dish/four-one-vegetarian | 49 / 1 / 650.11 / 7.72 | 49 / 1 / 650.11 / 8.51 | 48 / 2 / 526.41 / 9.29 | 47 / 2 / 535.59 / 13.16 | 47 / 2 / 535.59 / 13.47 |
| shared-dish/two-one-vegetarian | 58 / 2 / 719.71 / 6.72 | 59 / 2 / 639.93 / 5.93 | 60 / 1 / 644.50 / 6.57 | 60 / 1 / 644.50 / 6.94 | 60 / 1 / 644.50 / 6.49 |
| shared-dish/with-a-child | 21 / 1 / 300.17 / 6.65 | 21 / 1 / 300.17 / 4.86 | 21 / 1 / 311.76 / 6.06 | 21 / 1 / 276.49 / 7.53 | 21 / 1 / 276.49 / 7.29 |
| shared-dish/weekday-lunch-away | 49 / 1 / 633.54 / 9.76 | 49 / 1 / 633.54 / 8.74 | 48 / 2 / 508.10 / 10.35 | 47 / 2 / 527.27 / 14.46 | 47 / 2 / 527.27 / 13.45 |
| shared-dish/weekend-guest | 50 / 2 / 647.79 / 11.79 | 50 / 2 / 647.79 / 10.03 | 50 / 2 / 545.75 / 11.94 | 48 / 2 / 535.35 / 15.12 | 50 / 2 / 567.20 / 18.54 |
| shared-dish/peanut-whole-household | 21 / 1 / 310.40 / 5.68 | 21 / 1 / 310.40 / 5.6 | 21 / 1 / 321.08 / 6.07 | 21 / 1 / 296.25 / 7.91 | 21 / 1 / 296.25 / 7.56 |
| shared-dish/peanut-only-mei-avoids | 21 / 1 / 304.69 / 6.59 | 21 / 1 / 304.69 / 5.51 | 21 / 1 / 323.02 / 6.09 | 21 / 1 / 316.58 / 7.94 | 21 / 1 / 316.58 / 7.65 |
| shared-dish/mixed-diets | 21 / 1 / 209.01 / 7.17 | 21 / 1 / 209.01 / 5.87 | 20 / 2 / 254.41 / 6.73 | 20 / 2 / 246.51 / 8.36 | 20 / 2 / 246.51 / 8.15 |
| shared-dish/six-one-vegetarian | 23 / 2 / 280.30 / 9.95 | 23 / 2 / 280.30 / 8.58 | 24 / 1 / 324.72 / 11.68 | 24 / 1 / 324.72 / 12.49 | 24 / 1 / 330.92 / 17.87 |
| shared-dish/tight-budget | 21 / 1 / 111.75 / 45.2 | 21 / 1 / 111.75 / 35.74 | 21 / 1 / 104.06 / 45.68 | 21 / 1 / 84.33 / 47.67 | 21 / 1 / 84.33 / 46.5 |
| mdw/mdw-dev-001 | 21 / 1 / 293.70 / 1.24 | 21 / 1 / 293.70 / 1.19 | 21 / 1 / 293.70 / 1.24 | 21 / 1 / 293.70 / 1.01 | 21 / 1 / 293.70 / 1.16 |
| mdw/mdw-dev-002 | 28 / 1 / 470.13 / 1.32 | 28 / 1 / 470.13 / 1.08 | 28 / 1 / 470.13 / 1.04 | 28 / 1 / 470.13 / 0.79 | 28 / 1 / 470.13 / 0.98 |
| mdw/mdw-dev-003 | 20 / 2 / 404.42 / 0.85 | 20 / 2 / 404.42 / 0.72 | 20 / 2 / 404.42 / 0.71 | 20 / 2 / 404.42 / 0.7 | 20 / 2 / 404.42 / 0.69 |
| mdw/mdw-dev-004 | 26 / 2 / 416.00 / 1.29 | 25 / 3 / 436.32 / 1.11 | 28 / 1 / 486.40 / 1.38 | 28 / 1 / 486.40 / 1.33 | 28 / 1 / 486.40 / 1.28 |
| mdw/mdw-dev-005 | 28 / 1 / 461.34 / 1.54 | 28 / 1 / 461.34 / 1.31 | 28 / 1 / 461.34 / 1.32 | 28 / 1 / 461.34 / 1.27 | 28 / 1 / 461.34 / 1.24 |
| mdw/mdw-dev-006 | 20 / 2 / 380.90 / 1.14 | 20 / 2 / 380.90 / 0.94 | 20 / 2 / 380.90 / 1.08 | 20 / 2 / 380.90 / 1.03 | 20 / 2 / 380.90 / 1.0 |
| mdw/mdw-dev-007 | 21 / 5 / 415.16 / 2.87 | 21 / 5 / 415.16 / 2.38 | 21 / 5 / 415.16 / 2.36 | 21 / 5 / 415.16 / 2.28 | 21 / 5 / 415.16 / 2.23 |
| mdw/mdw-dev-008 | 13 / 7 / 100.97 / 3.49 | 13 / 7 / 100.97 / 3.09 | 13 / 7 / 100.97 / 2.99 | 13 / 7 / 100.97 / 3.08 | 13 / 7 / 100.97 / 3.1 |
| mdw/mdw-dev-009 | refused / 6.02 | refused / 5.39 | refused / 5.37 | refused / 5.17 | refused / 5.39 |
| mdw/mdw-dev-010 | 28 / 1 / 387.35 / 1.16 | 28 / 1 / 387.35 / 1.03 | 28 / 1 / 387.35 / 1.21 | 28 / 1 / 387.35 / 0.98 | 28 / 1 / 387.35 / 0.98 |
| mdw/mdw-dev-011 | 14 / 1 / 301.27 / 0.8 | 14 / 1 / 301.27 / 0.72 | 14 / 1 / 301.27 / 0.74 | 14 / 1 / 301.27 / 0.69 | 14 / 1 / 301.27 / 0.79 |
| mdw/mdw-dev-012 | 28 / 1 / 467.59 / 1.55 | 28 / 1 / 467.59 / 1.46 | 28 / 1 / 467.59 / 1.45 | 28 / 1 / 467.59 / 1.39 | 28 / 1 / 467.59 / 1.4 |
| mdw/mdw-dev-013 | 21 / 1 / 301.22 / 1.09 | 21 / 1 / 301.22 / 1.06 | 21 / 1 / 301.22 / 1.05 | 21 / 1 / 301.22 / 1.05 | 21 / 1 / 301.22 / 1.03 |
| mdw/mdw-dev-014 | 14 / 1 / 266.69 / 0.97 | 14 / 1 / 266.69 / 0.85 | 14 / 1 / 266.69 / 0.87 | 14 / 1 / 266.69 / 0.84 | 14 / 1 / 266.69 / 0.81 |
| mdw/mdw-dev-015 | 15 / 1 / 393.27 / 1.26 | 15 / 1 / 393.27 / 1.07 | 15 / 1 / 393.27 / 1.1 | 15 / 1 / 393.27 / 1.02 | 15 / 1 / 393.27 / 0.98 |
| mdw/mdw-dev-016 | 20 / 1 / 333.48 / 1.43 | 20 / 1 / 333.48 / 1.22 | 20 / 1 / 333.48 / 1.23 | 20 / 1 / 333.48 / 1.19 | 20 / 1 / 333.48 / 1.13 |
| mdw/mdw-dev-017 | 16 / 1 / 319.95 / 1.26 | 16 / 1 / 319.95 / 1.11 | 16 / 1 / 319.95 / 1.12 | 16 / 1 / 319.95 / 0.89 | 16 / 1 / 319.95 / 1.06 |
| mdw/mdw-dev-018 | 16 / 1 / 242.96 / 0.85 | 16 / 1 / 242.96 / 0.82 | 16 / 1 / 242.96 / 0.81 | 16 / 1 / 242.96 / 0.86 | 16 / 1 / 242.96 / 0.79 |
| mdw/mdw-dev-019 | 16 / 1 / 303.93 / 1.14 | 16 / 1 / 303.93 / 1.03 | 16 / 1 / 303.93 / 1.01 | 16 / 1 / 303.93 / 0.84 | 16 / 1 / 303.93 / 0.96 |
| mdw/mdw-dev-020 | 4 / 14 / 50.90 / 2.5 | 4 / 14 / 50.90 / 2.16 | 4 / 14 / 50.90 / 2.14 | 4 / 14 / 50.90 / 2.02 | 4 / 14 / 50.90 / 2.07 |
| mdw/mdw-dev-021 | 35 / 1 / 544.25 / 1.72 | 35 / 1 / 544.25 / 1.44 | 35 / 1 / 544.25 / 1.44 | 35 / 1 / 544.25 / 1.53 | 35 / 1 / 544.25 / 1.3 |

## Caveats

- Developer data only; the chosen cap has not been checked on held-out episodes.
- Times are one machine (Intel64 Family 6 Model 198 Stepping 2, GenuineIntel), one run per cap; they are recorded, not used to choose.
- Distinct dishes count recipes (full-default and shared-dish leave out staples); the product's own search loss is not exposed by the reports and is not compared.
- Commits per cap are in `latest.json` (`code_commits`).
