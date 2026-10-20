# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. These runs let the variety pass finish instead of cutting it at its two seconds, so the plans do not depend on the machine; the product cuts it, and takes correspondingly less. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, and every household here has members with their own limits, so these are the complex requests it allows up to about 60 s. Only past that is a case marked over. The `merged` column shows how much of the time the shared-dish model added. A request is never cut short to meet either figure, and speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 19.23 s. Slowest: 26.74 s.

Over ~60 s: none.

| Case | merged (s) | shared (s) | Against the ADR-0079 guidance |
|---|---:|---:|:---|
| `four-one-vegetarian` | 14.61 | 21.79 | within the guidance for a complex request |
| `two-one-vegetarian` | 8.17 | 21.6 | within the guidance for a complex request |
| `with-a-child` | 7.52 | 8.18 | within the guidance for a complex request |
| `weekday-lunch-away` | 11.3 | 16.86 | within the guidance for a complex request |
| `weekend-guest` | 15.72 | 26.74 | within the guidance for a complex request |
| `peanut-whole-household` | 8.09 | 8.66 | within the guidance for a complex request |
| `peanut-only-mei-avoids` | 10.07 | 8.17 | within the guidance for a complex request |
| `mixed-diets` | 5.09 | 11.44 | within the guidance for a complex request |
| `six-one-vegetarian` | 10.28 | 24.96 | within the guidance for a complex request |
| `tight-budget` | 18.72 | 26.45 | within the guidance for a complex request |
