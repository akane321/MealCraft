# Final validation gate diagnostic

The offline module `app.planning.validation_gate_experiments` compares selection
from the same retained component beam candidates with and without a final validation
gate. Both conditions use the same fixed packet, search limits, scoring and
shopping construction. It does not create or persist a product plan.

From the repository root with the backend environment installed:

```bash
PYTHONPATH=backend python -m app.planning.validation_gate_experiments \
  data/fixtures/planning-v2/final-gate-developer-v1.json > gate-report.json
```

On PowerShell, set `$env:PYTHONPATH = (Resolve-Path backend).Path` before running
the module. The input uses the `GateDataset` envelope (version, source and cases), compatible with one-dish developer packets from
[component experiments](planning-developer-experiments.md). Repair snapshots and
provider failures are rejected here: both conditions use one fixed snapshot.

`final_gate_off` chooses the lowest-loss retained candidate, with stable choice
IDs breaking ties, before validation runs. Its output is an unchecked draft.
`final_gate_on` chooses the lowest-loss retained candidate that passes final
validation, or selects nothing. A fresh independent audit observes each selected
draft; it cannot replace the off condition's choice. A missing candidate has a
null audit, which is not a passed check. An indeterminate candidate never passes
the on condition's gate.

Compiler filters, allergen exclusions, search-side diversity guards, nutrition
pruning and dominance stay active in both conditions. The experiment isolates
the final selection gate, not all constraint checking. Repair and feedback
ranking are off in both arms. Packets with a composed slot use MealBeamPlanner; other packets use BeamPlanner.
Role identifiers and portion shares are preserved. The report records the selected
engine and every engine limit. Mixed-package procurement and the product's full
planning flow are not measured. Search-side package-budget and daily-nutrition
pruning remain active in the meal engine, so those failures can be removed before
either final-gate condition receives a candidate.

The synthetic fixture includes a higher-ranked candidate over budget with a
lower-ranked affordable alternative, a basket one cent over budget with no
alternative, an allergen-saturated packet, pantry covering demand and an explicit
diversity packet. These cases are authored for development and regression, not
independent held-out evidence.

The report carries input and source digests, configuration, search counters,
selected assignments and shopping, and failed or indeterminate checks for each
candidate. It never labels bounded search exhaustion as infeasibility. Candidate
generation is shared and timed once. `gate_seconds` covers candidate validation;
per-condition `audit_seconds` measures the reporting audit. These are diagnostic
phase timings, not independent end-to-end latency measurements or a speedup claim.
Keep the code checkout and environment lockfile with the generated report.

This module has no product route or console setting. It covers a narrow part of
[P8](planning-validation-v2.md#p8--evidence); the other component conditions and feedback replay are gathered by
[the suite](planning-experiment-suite.md), while console integration remains a
consumer task. The final-gate experiment removes the independent final selection
gate; it deliberately retains constraint compilation and search guards. Existing developer experiment protocol v1 remains
unchanged; this report uses `planning-final-gate-dev-v2`. Previously generated v1 reports
remain v1; the engine configuration fields and composed support start in v2.


## Composed fixture

Use `data/fixtures/planning-v2/final-gate-composed-developer-v1.json` with the
same command for the composed component condition. It contains four synthetic
cases: a main, vegetable and optional soup; a tighter budget; missing products;
and unavailable optional dishes. The fixture is derived from the existing
meal-composition engineering tests, not independently authored evaluation data.

This uses the component MealBeamLimits defaults, including repeat_cost 0.10,
with the requested width and expansion limit. Product-level fallback searches,
optional-dish-first ordering and recommendation losses are not invoked. No
product-quality or CP-SAT optimality claim follows from this diagnostic. The
existing multi-dish evaluation runner remains the separate Beam/CP-SAT comparison.
