# Reusing product meal candidates

Fixed developer households and fixture prices; no LLM or held-out inputs.
Both conditions use the same committed source, seed, 50 proposals and search settings.
The full household reports, including meals, checks and prices, are identical.
One sequential measurement per condition; timings are diagnostic, not a statistical speed claim.
Profiling adds overhead. Stage durations include nested calls and must not be summed.

| Household | Reuse | Total s | Candidate-generation calls | SA domains s | SA proposals s |
| --- | --- | --- | --- | --- | --- |
| one-adult | False | 10.460 | 42 | 2.166 | 0.279 |
| four-with-vegetarian | False | 54.830 | 42 | 15.600 | 1.217 |
| one-adult | True | 8.380 | 21 | 0.041 | 0.796 |
| four-with-vegetarian | True | 24.990 | 21 | 0.307 | 1.261 |

This removes duplicate computation; it does not establish improved menu quality or an optimal-price gap.
Provenance and detailed results: [uncached](uncached/steps-50.json), [cached](cached/steps-50.json).
