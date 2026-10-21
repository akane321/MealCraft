# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. These runs let the variety pass finish instead of cutting it at its two seconds, so the plans do not depend on the machine; the product cuts it, and takes correspondingly less. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, and every household here has members with their own limits, so these are the complex requests it allows up to about 60 s. Only past that is a case marked over. The `merged` column shows how much of the time the shared-dish model added. A request is never cut short to meet either figure, and speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 18.23 s. Slowest: 26.79 s.

Over ~60 s: none.

| Case | merged (s) | shared (s) | Against the ADR-0079 guidance |
|---|---:|---:|:---|
| `four-one-vegetarian` | 14.8 | 18.66 | within the guidance for a complex request |
| `two-one-vegetarian` | 7.47 | 22.57 | within the guidance for a complex request |
| `with-a-child` | 7.2 | 12.72 | within the guidance for a complex request |
| `weekday-lunch-away` | 10.88 | 17.81 | within the guidance for a complex request |
| `weekend-guest` | 13.53 | 26.79 | within the guidance for a complex request |
| `peanut-whole-household` | 9.54 | 9.36 | within the guidance for a complex request |
| `peanut-only-mei-avoids` | 10.34 | 8.28 | within the guidance for a complex request |
| `mixed-diets` | 5.39 | 11.89 | within the guidance for a complex request |
| `six-one-vegetarian` | 10.63 | 24.87 | within the guidance for a complex request |
| `tight-budget` | 17.91 | 26.6 | within the guidance for a complex request |
