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
- Mixed hard budgets compare exactly against the submitted amount. `ADR-0021`
  section 2 aligned the V2 validator to the same rule, at cent granularity with
  no tolerance, so the two paths no longer differ.

## Not in this tranche

The workbench CLI, bounded snapshot repair, declared relaxation search and the
whole-plan scoring policy live on the source branch and arrive separately. The
commands quoted above run from that branch; the modules here are called
directly.

Runtime adoption additionally requires agreement on mixed allocation fields,
provenance and quantity precision, followed by owner-coordinated API,
persistence and UI integration. `ADR-0021` section 3 keeps the V2 shopping shape
unchanged until then, because Shopping List rendering, replanning deltas and
evaluation all read it.

## When the snapshot has one size per ingredient

A FairPrice snapshot may carry a single package size for an ingredient. That is
a limit of what has been captured, not evidence that mixed purchasing is
unnecessary: real supermarkets sell one ingredient in several sizes, and the
capability applies the moment a second size appears.

`data/fixtures/fairprice-products.json` had exactly one size per ingredient,
which meant this planner could not be exercised at all outside its own developer
fixture. `fairprice-products-v2.json` adds further sizes for the ingredients
recipes lean on most, so the held-out set can test it. No code changes when a
snapshot gains sizes.

