# Planning developer experiment suite

`app.planning.developer_suite.run_planning_suite(repeats=3)` runs the fixed
synthetic developer fixtures and returns JSON suitable for a console artifact.
It performs no network calls, database writes or product activation. Callers
must retain the conditions, source fingerprint, dataset digests and limitations
with the results. A diagnostic that finishes is not a claim that every input
has a feasible plan.

From the repository root, with the backend environment installed:

```bash
PYTHONPATH=backend python -m app.planning.developer_suite --repeats 3 \
  --json-report planning-suite.json --markdown-report planning-suite.md
```

On PowerShell, set `$env:PYTHONPATH = (Resolve-Path backend).Path` before the
module command. The report paths must differ. The CLI does not read arbitrary
input paths: its registry names only versioned developer fixtures.

## Experiment contracts

| Experiment | Mechanism | Interpretation |
| --- | --- | --- |
| Single and composed components | Beam, greedy reference, variety off, overlap off, repair off | Component diagnostics under recorded settings |
| Final validation gate | Rank-first draft versus first final-validated draft, using the same retained candidates | Independent final validation's selection effect; compiler and search guards stay on |
| Feedback choice replay | Existing cooked-share experimental rule versus off | Agreement with logged choices, not benefit or learned personalization |
| Feedback plan replay | Rank only compiler-eligible recipe IDs; compute shopping and validate afterwards | Shows candidate-order influence and checks the resulting plans; one dish per slot |

For composed meals the `greedy` preset explicitly uses width-one MealBeamPlanner,
not the formal B1 baseline. Single-dish packets keep FinalScopeReferencePlanner.
No compared system receives another system's answer. The feedback plan adapter
is an offline reference consumer, not a production Beam ranking integration.

The final-gate comparison is the independent-validator ablation at its output
boundary. Removing the constraint compiler as well would test a different
mechanism. Its reporting audit stays active in both arms but cannot change the
unchecked choice. No product request can select an unchecked draft from here.

The component report uses `planning-component-ablation-dev-v2`; final-gate
reports use their separate protocol. Old reports are never relabelled. Explicit
composed diversity weights use the bounded meal average described in
[diversity](planning-diversity.md). The soft-term consumer has a distinct
algorithm version; CP-SAT still refuses explicit diversity-policy packets and
must not be used to claim an optimality gap for this objective.

The generated Markdown lists category case counts and failed-check mechanisms,
including failures of the reference conditions. It does not calculate category
rates or declare category winners. Repeated component runs remain in the JSON;
the Markdown lists failures from the first repeat once. Gate and feedback
conditions are executed once each, as recorded in the suite conditions.

## Feedback adapter

`feedback_plan_experiments.plan_with_feedback` accepts an immutable problem,
typed `FeedbackEvent` values, a caller-supplied scope and an aware decision time.
It defaults off. The constraint compiler fixes each slot's eligible IDs; locked
recipes and the diversity extension guard remain in force. Feedback may only
permute that list. Shopping and final validation reuse the deterministic
implementations. An over-budget result is rejected; missing evidence yields
`needs_data`. All outputs are nonpersistable experiment artifacts.

Future product consumers must authorize the supplied household scope themselves.
They must export feedback using the time it became available, not the planned
meal time, and preserve the event ID. The adapter ignores future and other-scope
feedback. It does not export real check-ins or claim that a short synthetic
history trains a useful personalization model.

## Handoff boundaries

- Console: invoke the suite in a bounded job, persist its returned conditions and
  artifacts, and apply the existing administrator permissions. No new HTTP route
  or database model is defined by this module.
- Product planning: keep the final validator as the save gate. The experiment
  preset names are not runtime feature switches.
- Data: provide explicit versioned core/protein classifications for a real
  catalog. Synthetic fixture classifications are not production annotations.
- Agent themes: use the existing controlled proposal gate. Cuisine affinity,
  energy preference and effort shaping still need agreed parameter semantics
  and consumers; they must not be silently mapped to hard constraints.
- Retrieval and persistence: use the existing mixed-purchase handoff and
  fixed-menu-refresh contracts for package allocations and snapshot updates;
  this suite does not change those structures.

The source checkout and environment lockfile are needed for replay; a digest
alone cannot reconstruct an environment. This suite establishes developer
regression evidence only, not the final independent evaluation or a product
integration sign-off.
