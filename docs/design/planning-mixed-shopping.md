# Offline mixed shopping and solver comparison

The `mixed-plan` command runs Beam Search, derives consolidated ingredient demand,
deducts known pantry quantities, optimizes mixed packages and independently checks
the result. This is a separate offline contract, `offline-mixed-shopping-v1`.
The existing V2 single-product output and production API remain unchanged.

## Reproduce the developer example

Run from `backend` in the project Python environment:

```text
python -m app.planning.workbench mixed-plan ../data/fixtures/planning-v2/mixed-package-developer.json
python -m app.planning.workbench mixed-oracle ../data/fixtures/planning-v2/mixed-package-developer.json
python -m pip install -r requirements-planning-oracle.txt
python -m app.planning.workbench mixed-oracle ../data/fixtures/planning-v2/mixed-package-developer.json --cp-sat
```

The synthetic fixture has two meals for three people. Each recipe requires 100g
for two people, giving 300g total. Deducting 50g of pantry rice leaves 250g.
One 150g package at SGD2 and one 100g package at SGD1.50 cost SGD3.50 with no
surplus. Repeating either product costs more and exceeds the SGD3.50 budget.
Both mixed solvers and the mixed beam path return the budget-valid purchase.

## Search and validation

`BeamPlanner.search_candidates` exposes retained complete assignments. The
existing `solve` method retains its original shopping policy. `solve_mixed_beam`
evaluates every retained completion with mixed shopping and selects a valid plan
before comparing preference loss. An expansion cap never returns a partial plan.
Beam pruning still means that a better assignment may have been discarded.

The mixed validator recomputes serving-scaled ingredient demand, inventory
deduction, row identity, package coverage and total cost. It uses canonical
slot and nutrition checks and separate package arithmetic validation. Unknown
pantry quantity is never deducted; repeated pantry IDs require clarification of
the data policy. Forged quantities, totals and duplicate/missing rows fail checks.

The package enumerator uses rational arithmetic from decimal input strings.
Products must match both canonical ingredient and unit, have an unambiguous ID,
and use finite nonnegative whole-cent prices. It minimizes cost, then surplus,
then the selected product/count tuple. It does not infer substitutions or units.

The optional OR-Tools CP-SAT solver independently models integer package counts,
coverage and cost. It minimizes cost, fixes that optimum, minimizes coverage,
then fixes tied counts in sorted product order. Its tied allocation may differ
from enumeration; cost and surplus are the comparison targets. CP-SAT is an
optional offline dependency, pinned in `requirements-planning-oracle.txt`.
Integer modeling and solver status handling follow the
[official CP-SAT documentation](https://developers.google.com/optimization/cp/cp_solver).

`exhaustive_mixed_plan` enumerates raw recipe assignments and solves each shopping
subproblem. With `--cp-sat` this is a hybrid exhaustive/CP-SAT oracle, not a single
joint CP-SAT model. Complete supported packets can establish the best recipe loss
under the mixed shopping policy. Unknown data or an unfinished package solve
produces `incomplete_evidence`, even when a feasible incumbent exists. A recipe
search cap returns `limit_exceeded` before enumeration. No live-catalog or
unbounded global optimality claim follows from these results.

## Explicit limits and semantics

- Default beam width: 32; recipe expansions: 10000.
- Default oracle assignment cap: 10000; enumerated package combinations per
  ingredient: 100000. Runtime can grow with both assignment and ingredient counts.
- CP-SAT supports up to 32 compatible products per ingredient, exact quantity
  scaling up to 10^6 and integer activity up to 10^12. All lexicographic solves
  share one deterministic-work budget per ingredient. An unfinished solve is
  reported as a limit, never as infeasibility.
- Mixed demand fields currently serialize decimal floats. A serving calculation
  that cannot round-trip exactly, such as a third of a gram, returns `needs_data`
  with `quantity_not_representable`; it is not silently rounded. A rational or
  explicitly rounded quantity contract needs agreement before runtime adoption.
- Mixed hard budgets use an exact comparison to the submitted amount. This
  differs from the existing V2 validator's rounding allowance. It is confined to
  this offline contract and must be aligned before replacing V2 behavior.
- `--whole-plan` opts into the existing experimental scoring policy for
  `mixed-plan` or `mixed-oracle`. Scoring rules are not frozen evaluation policy.

## Remaining integration

The relaxation command accepts `--mixed-packages` to check declared changes
against mixed shopping. It evaluates the unchanged problem too, so a budget-valid
mixed purchase returns an empty change set. Missing products or package limits
prevent a minimality claim. Output identifies the shopping policy used. For example:

```text
python -m app.planning.workbench relax problem.json --options permitted-changes.json --mixed-packages
```

The repair command also accepts `--mixed-packages`. `solve_mixed_with_repair`
retains a separate failed candidate solely for deriving retrieval demand, requests
a complete replacement snapshot, and reruns mixed beam planning each round.
It refreshes product-evidence and budget failures only. Missing recipe quantities,
safety conflicts and package-search caps do not trigger retrieval. Attempts retain
the requested quantities, product records, version and retrieval trace. A degraded
response is recorded without using its prices; repeated versions, provider errors
and round limits stop explicitly. A feasible frozen plan returns immediately.

```text
python -m app.planning.workbench repair problem.json --options ordered-fixture-snapshots.json --mixed-packages --rounds 2
```

The default repair command retains the V2 policy. Both modes enforce the same
source-label, observation-time and candidate-count checks. Runtime adoption requires agreement
on mixed allocation fields, provenance, quantity precision and budget tolerance,
followed by owner-coordinated API, persistence and UI integration.

Tests cover a hand-calculated purchase, mutations of every reported quantity,
ambiguous IDs, invalid prices, unknown pantry, limits, deterministic ordering,
CP-SAT/enumerator agreement, and preservation of the original beam behavior.
These synthetic developer checks do not measure held-out or live-service quality.
