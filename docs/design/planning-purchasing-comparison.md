# Fixed-menu purchasing comparison

`app.planning.purchasing_comparison` compares two purchasing policies for the
same validated menu and frozen product packet. It reuses the offline mixed
package solver described in [mixed shopping](planning-mixed-shopping.md).
It does not change the product API or select recipes.

The whole-horizon policy combines ingredient demand across every assigned slot
before deducting pantry and choosing packages. The baseline purchases separately
for each slot, in packet slot order. It consumes the original pantry once and
does not carry purchased surplus into another checkout. This baseline measures
the cost of that restriction; it does not represent an optimal sequential buyer.
Multiple dishes within one slot share a checkout and retain their canonical
portion shares.

Each basket is checked against the original complete assignment by the independent
shopping validator. A valid basket above the hard budget is reported as
`over_budget`; its arithmetic can still be compared. Missing evidence, search
limits or validation errors produce `unresolved` without a saving claim.
Budgets must use whole cents. Unknown pantry quantity is never deducted.

The output includes the input digest, solver limit, checkout solver-call counts,
elapsed wall time, package allocations, costs and surplus for each ingredient and
unit. Elapsed time varies by machine and is not a solver benchmark. The
enumeration cap applies to each ingredient checkout; it is not a whole-run time
limit. Lower cost can mean greater surplus. Quantities with different units are
not added together.

For independent ingredients with additive prices and no shared stock or offers,
exact per-ingredient optimization of aggregate demand already gives the cheapest
basket for that fixed menu. This comparison makes no claim to improve that
optimum, prove global menu optimality or measure CP-SAT performance.

From the repository root, set `PYTHONPATH=backend` and run:

```text
python -m app.planning.purchasing_comparison developer-packet.json
```

The JSON input has `problem` (a `FinalPlanningProblem`) and `assignments` (a list
of `PlanningAssignment` objects). Use synthetic or developer packets only.
`--max-combinations` sets the bounded enumeration cap, defaulting to 100000.
The acceptance cases live in `backend/tests/test_purchasing_comparison.py`.
The Planning-side allocation and evidence prototype is described in the
[mixed purchase handoff proposal](planning-mixed-purchase-handoff.md).

## Synthetic solver scaling

The separate package benchmark runs both bounded enumeration and optional CP-SAT
on versioned artificial demands and package prices. It covers one ingredient with
three options, eight ingredients with four options each, and 24 ingredients with
eight options each. It uses no recipe catalog, live price retrieval or held-out
episodes. Demand is already aggregated and pantry-net, so this experiment measures
package solving only.

```text
python -m app.planning.purchasing_benchmark --output outputs/package-scale.json
```

The generated JSON records the full synthetic input, input digest, Python and
OR-Tools versions, platform, limits, all allocations, independent validation,
three timing samples and their median. Timings include all ingredient calls and
validation, without warm-up; the first CP-SAT run includes its import cost.
They are local observations, not product latency guarantees.
Run order is enumeration followed by CP-SAT, without randomization or isolation
from other local workloads; do not interpret the timings as a controlled speedup.

CP-SAT uses the existing one-worker, seed-zero package oracle, a maximum of 32
products per ingredient and one deterministic-work unit per ingredient. That
limit is shared across its lexicographic solves; it is neither wall-clock
seconds nor a limit for the complete basket. Enumeration keeps its per-ingredient
100000-combination cap. Each measured run attempts every ingredient even when
another ingredient exceeds a cap.

The comparison reports equal cost and surplus only when both solvers return
independently validated optimal results, repeated runs are stable and every
ingredient's two objective values agree. Package identities can differ on ties.
A missing optional dependency, limit, invalid result or unstable run leaves the
comparison unresolved. A fast limit exit must not be described as a faster
completed solution. These fixtures provide bounded regression evidence, not a
general claim that one solver outperforms the other.
