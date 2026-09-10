# Exhaustive assignment oracle

> **Scope of this document.** It is a component contract: what the component
> promises, what it refuses, and what it must never be read as proving. Run
> counts, local timings and per-PR verification logs are not contracts - they go
> stale on the next commit - and live in the pull request and in the private
> task history instead. Current test status comes from CI.

`exhaustive_assignments(problem, max_combinations=10000)` checks every recipe assignment in a small frozen packet. Optional unlocked slots include a skip choice. The oracle uses raw recipe candidates and the independent validator rather than the compiler, beam pruning or dominance logic.

The returned counts show total, checked, feasible and indeterminate combinations. `best_choices` and `best_loss` describe the best validated assignment under the current reference local-loss and repetition policy.

Statuses:

- `optimal_for_fixed_shopping_policy`: every combination was checked, no indeterminate combinations remain, and a valid assignment was found.
- `no_valid_assignment`: every combination was checked and none passed under the fixed shopping policy and supplied packet.
- `needs_data`: at least one combination was indeterminate; a best known valid assignment may still be returned, without an optimality claim.
- `limit_exceeded`: the Cartesian product exceeds the configured cap; no enumeration starts and no infeasibility claim is made.

Shopping selection deliberately uses the reference builder, which chooses one product type per ingredient line. This oracle does not prove global optimality over mixed package products, substitutions or recipes outside the packet. It also shares the final validator and local-loss helper with the planner, so independent hand-calculated tests remain necessary. It is a developer tool, not a production solver or a CP-SAT/MILP replacement.

Regression example: two slots and two recipes create four combinations. Only the slower recipe repeated twice satisfies the frozen package budget. Width-one Beam Search misses it; width four and exhaustive enumeration find it. With only time loss active, the known score is 0.5 + 0.5 + 0.1 + 0.35 = 1.45.

Required test coverage for this component: enumeration counts, the hand-computed score in the worked example above, a narrow-beam miss, missing evidence, resource limits, raw-candidate validation, optional skips and stable ordering.

## Running this component

From the repository root, without starting the stack:

```bash
uv run --project backend pytest backend/tests/test_exhaustive_oracle.py
```

The oracle is a developer tool. It has no product entry point, and it is not
wired into the evaluation workbench.

Current pass/fail status comes from CI, not from this page.
