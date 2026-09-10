# Planning constraint compiler

> **Scope of this document.** It is a component contract: what the component
> promises, what it refuses, and what it must never be read as proving. Run
> counts, local timings and per-PR verification logs are not contracts - they go
> stale on the next commit - and live in the pull request and in the private
> task history instead. Current test status comes from CI.

`app.planning.constraint_compiler.compile_constraints(problem)` consumes an already validated `FinalPlanningProblem` and returns an immutable tuple of slot/recipe decisions sorted by stable IDs. Each decision exposes `eligible` and sorted `rejection_codes`.

Implemented: meal type, time, allergens, excluded ingredients, dietary tags, locks, and explicit hard per-slot nutrient bounds. Numeric comparisons use the existing validator's 1e-6 tolerance. Nutrition is per person, not multiplied by household servings. Soft bands and general health preferences do not reject candidates. Daily and horizon targets remain aggregate constraints.

This is an independently callable component for the next search implementation. The greedy reference planner and public API remain on their existing paths. An eligible candidate is not proof of plan feasibility or data completeness. The current input schema requires numeric nutrition and does not carry all upstream completeness/provenance states; missing-data support is pending contract alignment. No global infeasibility claim is made for an empty candidate set.

Required test coverage for this component: every filter, deterministic matrix ordering, input preservation, nutrition scope, soft-preference exclusion, inclusive numeric boundaries, tolerance behaviour, and safety conflicts in optional locked slots. These are component tests. Passing them is not end-to-end evaluation evidence and must not be reported as such.


## Search domains

`compile_search_domains(problem)` groups eligible recipe IDs by slot and retains the full rejection matrix. A slot must be assigned when it is required or locked. `blocked_slot_ids` identifies those mandatory slots with an empty domain; an unlocked optional slot may remain empty.

An empty mandatory domain rules out an assignment within the supplied candidate packet. Nonempty domains still require aggregate nutrition and shopping validation. This result does not choose recipes or report overall plan feasibility.

Inputs must contain canonical, reviewed facts. An empty user allergen list means no user restriction. An empty reviewed recipe allergen list has no recorded allergen conflict. Updating either list changes filtering without changing the algorithm. Unknown source completeness must be handled before this input boundary.

## Running this component

From the repository root, without starting the stack:

```bash
uv run --project backend pytest backend/tests/test_constraint_compiler.py backend/tests/test_planning_v2.py
```

Inside a running stack:

```bash
docker compose exec backend uv run --no-sync pytest tests/test_constraint_compiler.py tests/test_planning_v2.py
```

Current pass/fail status comes from CI, not from this page.
