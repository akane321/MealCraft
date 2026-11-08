# Full product parameter calibration — 2026-11-06

This is developer calibration evidence only. It uses the five documented
`full-default-v1` synthetic households and fixture prices. It does not use or
inspect held-out or sealed evaluation content, and it does not establish global
optimality, a real-price gap, independent near-duplicate acceptance, or sealed
evaluation success.

## Reproduction

Run from the repository root. The [JSON artifacts](.) are the canonical carrier
for the issue #310 run commit and reproducibility metadata:

```powershell
uv run --no-sync --project backend python scripts/product_household_comparison.py `
  --output docs/evaluation/product-improvement-sweep/full-parameter-calibration-2026-11-06 `
  --widths 8 16 32 64 --steps 0 50 200 --repeats 3 --profile
```

The working tree was dirty because the issue #310 WIP was present. Every JSON
artifact records the runner and profiler SHA-256, commit, dirty-tree flag,
machine metadata, parameters, cases, repetitions, condition order, full case
reports, plan timings, improvement traces, and stage profiles. The command ran
sequentially with no competing benchmark job. It completed with exit code 0.

The runner formed conditions in width-major order:

```text
8/0, 8/50, 8/200, 16/0, 16/50, 16/200,
32/0, 32/50, 32/200, 64/0, 64/50, 64/200
```

Repeat 0 used that order. Repeat 1 rotated left by one condition; repeat 2
rotated left by two. Within every condition, the matched case order was:

```text
one-adult, four-with-vegetarian, six-tight-budget,
two-no-oven-ten-days, seven-with-young-children
```

This gives 36 condition-runs and 180 household plans. All 36 condition-runs
passed all five household checks.

## Matched results

Plan time is the median and maximum across the 15 matched case-runs for each
condition. Mean checkout and distinct dishes are also across those 15 runs.
`Improved` counts improvement traces whose returned plan improved the
lexicographic product objective; `retained` counts traces where the adjacency
guard retained the beam seed. Beam-only conditions have no improvement trace.

| Width | Steps | Passing repeats | Median plan s | Max plan s | Mean checkout S$ | Mean distinct dishes | Improved | Retained |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 0 | 3/3 | 60.74 | 263.83 | 490.51 | 54.0 | 0 | 0 |
| 8 | 50 | 3/3 | 37.27 | 309.31 | 489.54 | 54.0 | 6 | 3 |
| 8 | 200 | 3/3 | 73.80 | 432.03 | 489.54 | 54.0 | 6 | 0 |
| 16 | 0 | 3/3 | 62.83 | 729.04 | 488.33 | 54.2 | 0 | 0 |
| 16 | 50 | 3/3 | 59.49 | 474.39 | 487.36 | 54.2 | 6 | 3 |
| 16 | 200 | 3/3 | 51.09 | 275.99 | 487.36 | 54.2 | 6 | 0 |
| 32 | 0 | 3/3 | 36.98 | 356.50 | 479.42 | 54.2 | 0 | 0 |
| 32 | 50 | 3/3 | 45.30 | 364.16 | 478.45 | 54.2 | 6 | 3 |
| 32 | 200 | 3/3 | 54.34 | 308.70 | 478.45 | 54.2 | 6 | 3 |
| 64 | 0 | 3/3 | 37.48 | 201.57 | 510.15 | 54.2 | 0 | 0 |
| 64 | 50 | 3/3 | 43.00 | 202.26 | 509.75 | 54.2 | 3 | 0 |
| 64 | 200 | 3/3 | 56.99 | 205.58 | 509.75 | 54.2 | 3 | 0 |

The large timing changes between repeat 0 and later warm repetitions show that
machine/cache/order effects are material. These measurements do not establish a
statistically significant speed ranking.

## Stage profiles

The values below are medians across the 15 case profiles per condition. Stage
durations are inclusive and overlap: candidate generation contains nested
fixture grocery estimates, and stages must not be summed. Profiling adds
overhead and excludes HTTP, LLM parsing, and live lookup.

| Width | Steps | Candidate s | Meal options s | Validation s | Shopping s | Objective s | Proposal s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 0 | 5.203 | 21.323 | 0.032 | 0.000 | 0.000 | 0.000 |
| 8 | 50 | 4.891 | 18.112 | 1.043 | 0.136 | 0.051 | 1.361 |
| 8 | 200 | 5.470 | 29.238 | 4.837 | 0.748 | 0.211 | 6.806 |
| 16 | 0 | 7.478 | 28.776 | 0.046 | 0.000 | 0.000 | 0.000 |
| 16 | 50 | 6.651 | 28.897 | 1.173 | 0.150 | 0.050 | 1.448 |
| 16 | 200 | 4.364 | 16.785 | 2.756 | 0.430 | 0.140 | 3.411 |
| 32 | 0 | 4.931 | 19.164 | 0.036 | 0.000 | 0.000 | 0.000 |
| 32 | 50 | 5.711 | 22.076 | 0.833 | 0.118 | 0.042 | 1.087 |
| 32 | 200 | 4.988 | 19.989 | 3.583 | 0.511 | 0.157 | 4.444 |
| 64 | 0 | 5.327 | 18.816 | 0.031 | 0.000 | 0.000 | 0.000 |
| 64 | 50 | 5.325 | 18.929 | 0.839 | 0.128 | 0.038 | 0.944 |
| 64 | 200 | 5.574 | 20.762 | 4.474 | 0.500 | 0.143 | 5.555 |

## Conclusion

No production default changes are justified by this matrix, and none were
made. Width 32 matched the highest mean distinct-dish count and had lower mean
fixture checkout than widths 8, 16, and 64 in these five households. Width 64
did not add aggregate distinct-dish value and cost more. Fifty improvement
steps reduced mean fixture checkout relative to beam-only at every width;
200 steps produced no further aggregate checkout or distinct-dish gain over 50.
The matched timings are too order-sensitive to support a speed-based default
change, which would be disallowed in any case without a quality justification.

This completes the issue #310 full-parameter-calibration evidence item for the
documented developer cases. It does not close the other issue #310 acceptance
blockers listed in [the remaining-work inventory](../remaining-work.md).
