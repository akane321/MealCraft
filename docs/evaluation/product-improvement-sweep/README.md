# Product beam and annealing: developer parameter sweep

Fixture-priced v1 developer cases only. This is not held-out or user-study evidence.
The set covers single-dish dinners; it does not establish composed-household acceptance.
ADR-0095 retains the beam seed whenever a local proposal increases adjacent repeats.
Each evaluation independently plans each feasible case twice to check determinism.
Times cover the product planning engine, excluding HTTP, LLM parsing and live prices.
No exact reference is run here, so no optimality gap is claimed.
Runs are sequential, with no other local test or benchmark job started during this sweep.
Background machine load is uncontrolled; timings do not establish statistically significant speedups.

| Beam width | SA steps | Runs | Hard violations | Legacy failures (range) | Median plan s | Max plan s | Median improvement s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | 0 | 3 | 0 | 0–0 | 0.0454 | 0.1144 | 0.0000 |
| 8 | 50 | 3 | 0 | 0–0 | 0.0950 | 0.1812 | 0.0473 |
| 8 | 200 | 3 | 0 | 0–0 | 0.2389 | 0.6916 | 0.1896 |
| 16 | 0 | 3 | 0 | 0–0 | 0.0699 | 0.2016 | 0.0000 |
| 16 | 50 | 3 | 0 | 0–0 | 0.1436 | 0.4577 | 0.0553 |
| 16 | 200 | 3 | 0 | 0–0 | 0.2687 | 0.6576 | 0.1913 |
| 32 | 0 | 3 | 0 | 0–0 | 0.1241 | 0.2659 | 0.0000 |
| 32 | 50 | 3 | 0 | 0–0 | 0.1728 | 0.3236 | 0.0471 |
| 32 | 200 | 3 | 0 | 0–0 | 0.3126 | 0.5398 | 0.1854 |
| 64 | 0 | 3 | 0 | 0–0 | 0.1368 | 0.3387 | 0.0000 |
| 64 | 50 | 3 | 0 | 0–0 | 0.1795 | 0.4003 | 0.0423 |
| 64 | 200 | 3 | 0 | 0–0 | 0.4367 | 1.1762 | 0.2215 |

| Beam width | SA steps | Mean table kinds | Mean checkout S$ | Worsened weekly scores |
| --- | --- | --- | --- | --- |
| 8 | 0 | 6.611 | 91.292 | 0 |
| 8 | 50 | 6.778 | 92.206 | 0 |
| 8 | 200 | 6.778 | 93.300 | 0 |
| 16 | 0 | 6.611 | 91.292 | 0 |
| 16 | 50 | 6.778 | 92.139 | 0 |
| 16 | 200 | 6.778 | 93.764 | 0 |
| 32 | 0 | 6.611 | 91.292 | 0 |
| 32 | 50 | 6.778 | 92.139 | 0 |
| 32 | 200 | 6.778 | 93.764 | 0 |
| 64 | 0 | 6.611 | 91.292 | 0 |
| 64 | 50 | 6.778 | 94.294 | 0 |
| 64 | 200 | 6.778 | 91.614 | 0 |

No product default is changed by this diagnostic. Raw records include packet hashes,
table-kind counts, checkout totals, per-case outcomes and before/after scores.

Recorded evaluation rounds: 36. Source commits: `ec0bcdde39fa8de11da59d5e478f62dea14fb0bd`.

At width 32, mean table kinds are 6.611 without improvement, 6.778 at 50 proposals and 6.778 at 200 proposals.
More proposals are not automatically a better default. The weekly objective prioritizes variety
over cost, so a valid improved plan may cost more. Household breadth and exact-reference evidence
remain necessary before claiming final algorithm acceptance.
