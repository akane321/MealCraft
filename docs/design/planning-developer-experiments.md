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

The v2 CLI accepts single-dish and composed packets using MealExperimentDataset.
ExperimentDataset retains the original one-dish schema for existing callers.
Composed packets use component MealBeamPlanner settings, not product orchestration.
For these packets the greedy preset is width-one meal beam, explicitly recorded
in engine_limits; it is not the formal evaluation B1 baseline. It uses the component's one-product-per-ingredient shopping
policy, not mixed-package purchasing. See the [purchasing comparison](planning-purchasing-comparison.md).

Final-gate and feedback on/off comparisons are separate experiments gathered by
[the suite](planning-experiment-suite.md). Ranking remains off in the five
component conditions. The Operations worker calls the v2 runner for the fixed
single-dish component fixture, retaining its conditions and complete report.
The composed component fixture and feedback replay remain available through the
CLI suite, not this Console registry. No product route exposes a validation bypass.

The complete P8 target remains in [Planning and Validation](planning-validation-v2.md#p8--evidence).
The reporting and split rules remain in [comparative evaluation](comparative-evaluation-v2.md).

The composed weight and repair fixture is `data/fixtures/planning-v2/composed-ablation-developer-v1.json`.
The extended runner reports `planning-component-ablation-dev-v2`; existing v1 reports remain unchanged.
