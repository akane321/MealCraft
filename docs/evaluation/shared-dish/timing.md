# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. The target is about 4 seconds for a common request (ADR-0075); a case over it is marked. Speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 7.46 s. Slowest: 16.37 s.

| Case | merged (s) | shared (s) | Against the 4 s target |
|---|---:|---:|:---:|
| `four-one-vegetarian` | 8.79 | 7.92 | over |
| `two-one-vegetarian` | 3.06 | 6.72 | over |
| `with-a-child` | 6.6 | 6.88 | over |
| `weekday-lunch-away` | 3.81 | 9.25 | over |
| `weekend-guest` | 3.39 | 11.73 | over |
| `peanut-whole-household` | 6.21 | 6.94 | over |
| `peanut-only-mei-avoids` | 6.45 | 6.98 | over |
| `mixed-diets` | 3.79 | 7.0 | over |
| `six-one-vegetarian` | 6.87 | 16.37 | over |
| `tight-budget` | 16.64 | 15.62 | over |
