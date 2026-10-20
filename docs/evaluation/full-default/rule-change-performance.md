# Rule-change timing replay

> Scope: Developer six-tight-budget only; same-machine sequential replay, not capability evaluation or speed acceptance.

Replay the four changed app modules and matching tag file from ce4fbef, 45133a7 and corrected sources. Hold other app code, fixtures and six-person request fixed. One unbounded-variety report run warms caches; three warm product runs restore the two-second variety limit. No concurrent task-owned heavy test was run during replay. Wall and process CPU are measured separately. Exact source hashes identify uncommitted corrected code.

| Version | First/report wall (s) | Three warm wall times (s) | Warm median (s) | Three warm CPU times (s) |
|---|---:|---|---:|---|
| ce4fbef | 39.581 | 24.539, 22.426, 24.088 | 24.088 | 23.469, 22.141, 23.312 |
| 45133a7 | 36.384 | 21.923, 21.41, 21.438 | 21.438 | 21.438, 21.188, 21.0 |
| current | 41.388 | 28.32, 27.905, 29.437 | 28.32 | 27.906, 27.609, 28.812 |

- The earlier roughly 38-second single warm run is not reproduced by the submitted-version three-run median. Historical machine load and CPU data were not recorded, so its exact cause cannot be established.
- Corrected sources are slower than the submitted version in this replay; process CPU also increases, so it is not justified to attribute the complete increase to waiting or machine noise. Rules, admissible roles and resulting search/plan choices changed together; this replay does not isolate their individual contributions.
- Every replayed plan passes. The six-person request remains over the four-second target. This correctness repair does not claim or implement the separate speed task.

Source and tag hashes, machine description, catalog-role counts and raw measurements are in `rule-change-performance.json`. The separate `timing.md` runs all five developer households; its samples are a different run and need not equal this controlled six-person replay.
