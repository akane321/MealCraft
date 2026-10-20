# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. These runs let the variety pass finish instead of cutting it at its two seconds, so the plans do not depend on the machine; the product cuts it, and takes correspondingly less. The target is about 4 seconds for a common request (ADR-0075); a case over it is marked, and the `merged` column shows how much of that the shared-dish model added. Speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 15.84 s. Slowest: 24.25 s.

| Case | merged (s) | shared (s) | Against the 4 s target |
|---|---:|---:|:---:|
| `four-one-vegetarian` | 13.56 | 15.76 | over |
| `two-one-vegetarian` | 6.99 | 19.37 | over |
| `with-a-child` | 6.49 | 7.67 | over |
| `weekday-lunch-away` | 9.0 | 15.91 | over |
| `weekend-guest` | 12.09 | 22.15 | over |
| `peanut-whole-household` | 8.67 | 7.89 | over |
| `peanut-only-mei-avoids` | 7.82 | 7.61 | over |
| `mixed-diets` | 3.61 | 9.77 | over |
| `six-one-vegetarian` | 9.41 | 21.51 | over |
| `tight-budget` | 16.13 | 24.25 | over |
