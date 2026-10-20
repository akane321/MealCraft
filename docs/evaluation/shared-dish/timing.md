# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. These runs let the variety pass finish instead of cutting it at its two seconds, so the plans do not depend on the machine; the product cuts it, and takes correspondingly less. The target is about 4 seconds for a common request (ADR-0075); a case over it is marked, and the `merged` column shows how much of that the shared-dish model added. Speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 12.23 s. Slowest: 16.40 s.

| Case | merged (s) | shared (s) | Against the 4 s target |
|---|---:|---:|:---:|
| `four-one-vegetarian` | 10.55 | 12.36 | over |
| `two-one-vegetarian` | 6.5 | 13.19 | over |
| `with-a-child` | 5.75 | 5.97 | over |
| `weekday-lunch-away` | 6.99 | 12.1 | over |
| `weekend-guest` | 8.79 | 16.23 | over |
| `peanut-whole-household` | 6.29 | 5.81 | over |
| `peanut-only-mei-avoids` | 6.16 | 6.59 | over |
| `mixed-diets` | 3.84 | 7.72 | over |
| `six-one-vegetarian` | 5.99 | 15.08 | over |
| `tight-budget` | 15.2 | 16.4 | over |
