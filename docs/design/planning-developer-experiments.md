# Planning developer component experiments

`python -m app.planning.developer_experiments` runs paired offline conditions on
versioned synthetic or developer packets. It writes JSON to stdout and never
saves a household plan or calls a live provider. These are component diagnostics,
not held-out results or end-to-end task-success measurements.

From the repository root, with the backend environment installed:

```bash
PYTHONPATH=backend python -m app.planning.developer_experiments \
  data/fixtures/planning-v2/ablation-developer-v1.json --repeats 3 > report.json
```

On PowerShell, set `$env:PYTHONPATH = (Resolve-Path backend).Path` before running
the same module command. The input contains `version`, `source` and uniquely
identified `cases`. Each case embeds a `FinalPlanningProblem` and optional ordered
fixture snapshots, or a simulated unavailable provider. A source label does not
prove dataset provenance: never relabel held-out data to use this runner.

## Conditions

| Preset | Change from the beam condition |
| --- | --- |
| `beam` | Bounded BeamPlanner with independent validation and bounded fixture repair |
| `greedy` | FinalScopeReferencePlanner replaces BeamPlanner; this is the existing component reference, not evaluation B1 |
| `variety_off` | Only the explicit diversity policy's `diversity_penalty` becomes zero |
| `overlap_off` | Only the explicit diversity policy's `overlap_reward_weight` becomes zero |
| `repair_off` | Repair rounds become zero; no snapshot is requested |

Hard constraints, classification evidence and diversity caps remain in force.
A weight absent from a packet, or already zero, yields `not_applicable` rather
than an apparent comparison. Every repeat starts from a detached packet and a
fresh fixture provider. Seed is null because neither solver uses randomness.
The defaults are existing component limits, not tuned or frozen parameters.

The runner records the dataset and effective-packet digests, app-source digest,
Python version, active configuration, algorithm trace, snapshot attempts, selected
assignments, shopping and a fresh independent audit against the snapshot actually
used. CLI output also carries the exact input-file digest. Keep the source
checkout and environment lockfile with the report; a digest alone cannot restore
code. `solve_seconds` includes repair and its built-in validation;
`audit_seconds` measures the additional report audit. Timing is not deterministic.

A failed hard check and an indeterminate check both remain visible. Search
exhaustion is not relabelled infeasible. Reports give category input counts and
individual failed-check mechanisms, with no per-category rates or winners. There
is no success-rate aggregate: accepting a valid plan and correctly refusing an
impossible request are different tasks and require declared labels before scoring.

## Fixture coverage

The embedded synthetic cases exercise a checkout one cent over budget, candidates
all containing an excluded allergen, pantry covering the full requirement, a new
fixture price that makes the same request affordable, and an unavailable provider.
A separate synthetic diversity packet exercises both nonzero soft weights. The
price case exercises repair, not repricing a persisted confirmed plan; that
separate flow is documented in [fixed-menu refresh](planning-fixed-menu-refresh.md).

## Limits and handoff

This runner accepts one dish per explicit slot, including multiple dates and
meal types. It rejects composed-meal packets; it does not measure the product's
MealBeamPlanner. It uses the component's one-product-per-ingredient shopping
policy, not mixed-package purchasing. See the [purchasing comparison](planning-purchasing-comparison.md).

Independent-validation-off, learned-ranking-off and composed meals remain
deferred and are named in each report. Ranking is off in all implemented
conditions. No product route exposes a validation bypass.

The internal Operations Console now exposes this fixed developer fixture as
`planning-components`. Operators and administrators must explicitly confirm a
bounded parameter set; they cannot supply a path, held-out packet or provider.
The durable worker calls `run_experiments`, preserves the full report and adds
the code revision, dataset file digest, product snapshot digest, normalized
parameter digest, duration and paid-usage declaration to the append-only run.
Retries reuse the same idempotent job and cannot replace a result from another
worker attempt. This integration does not turn component diagnostics into an
evaluation winner or a citable held-out result.

The complete P8 target remains in [Planning and Validation](planning-validation-v2.md#p8--evidence).
The reporting and split rules remain in [comparative evaluation](comparative-evaluation-v2.md).
