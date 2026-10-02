# Final validation gate diagnostic

The offline module `app.planning.validation_gate_experiments` compares selection
from the same retained BeamPlanner candidates with and without a final validation
gate. Both conditions use the same fixed packet, search limits, scoring and
shopping construction. It does not create or persist a product plan.

From the repository root with the backend environment installed:

```bash
PYTHONPATH=backend python -m app.planning.validation_gate_experiments \
  data/fixtures/planning-v2/final-gate-developer-v1.json > gate-report.json
```

On PowerShell, set `$env:PYTHONPATH = (Resolve-Path backend).Path` before running
the module. The input uses the developer dataset envelope from
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
ranking are off in both arms. One dish per explicit slot is supported; composed
meals, mixed-package procurement and the product's full planning flow are not.

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
[P8](planning-validation-v2.md#p8--evidence); full validation-off experiments,
learned ranking comparisons, composed-meal conditions and console integration
still require separate work. Existing developer experiment protocol v1 remains
unchanged; this report uses `planning-final-gate-dev-v1`.
