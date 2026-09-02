# MealCraft Evaluation Workbench

> Generated evidence. Method, split rules and metric definitions are fixed in [`protocol-v1.md`](../protocol-v1.md).

## Run status

- Developer gate: **PASS**
- Agent provider: **fixture**
- Live API used: **no**
- Recorded failure cases: **44**

## Held-out comparison

| Metric | Greedy baseline | MealCraft planner | Delta |
|---|---:|---:|---:|
| Scenario expectation rate | 1.0 | 1.0 | 0.0 |
| Mean distinct recipes | 1.0 | 6.1389 | 5.1389 |
| Consecutive repetitions | 216 | 0 | -216 |
| Failure cases | 36 | 0 | -36 |

## Offline Agent benchmark

| Metric | Result |
|---|---:|
| `case_count` | 24 |
| `exact_case_rate` | 0.6667 |
| `field_precision` | 1.0 |
| `field_recall` | 0.8298 |
| `field_f1` | 0.907 |
| `hallucinated_field_count` | 0 |
| `clarification_accuracy` | 0.875 |
| `medical_boundary_accuracy` | 1.0 |
| `failure_case_count` | 8 |

## Failure registry

| # | Source | Case | Reasons |
|---:|---|---|---|
| 1 | heldout-greedy-baseline | hold-001 | consecutive_recipe_repetition |
| 2 | heldout-greedy-baseline | hold-002 | consecutive_recipe_repetition |
| 3 | heldout-greedy-baseline | hold-003 | consecutive_recipe_repetition |
| 4 | heldout-greedy-baseline | hold-004 | consecutive_recipe_repetition |
| 5 | heldout-greedy-baseline | hold-005 | consecutive_recipe_repetition |
| 6 | heldout-greedy-baseline | hold-006 | consecutive_recipe_repetition |
| 7 | heldout-greedy-baseline | hold-007 | consecutive_recipe_repetition |
| 8 | heldout-greedy-baseline | hold-008 | consecutive_recipe_repetition |
| 9 | heldout-greedy-baseline | hold-009 | consecutive_recipe_repetition |
| 10 | heldout-greedy-baseline | hold-010 | consecutive_recipe_repetition |
| 11 | heldout-greedy-baseline | hold-011 | consecutive_recipe_repetition |
| 12 | heldout-greedy-baseline | hold-012 | consecutive_recipe_repetition |
| 13 | heldout-greedy-baseline | hold-013 | consecutive_recipe_repetition |
| 14 | heldout-greedy-baseline | hold-014 | consecutive_recipe_repetition |
| 15 | heldout-greedy-baseline | hold-015 | consecutive_recipe_repetition |
| 16 | heldout-greedy-baseline | hold-016 | consecutive_recipe_repetition |
| 17 | heldout-greedy-baseline | hold-017 | consecutive_recipe_repetition |
| 18 | heldout-greedy-baseline | hold-018 | consecutive_recipe_repetition |
| 19 | heldout-greedy-baseline | hold-019 | consecutive_recipe_repetition |
| 20 | heldout-greedy-baseline | hold-020 | consecutive_recipe_repetition |
| 21 | heldout-greedy-baseline | hold-021 | consecutive_recipe_repetition |
| 22 | heldout-greedy-baseline | hold-022 | consecutive_recipe_repetition |
| 23 | heldout-greedy-baseline | hold-023 | consecutive_recipe_repetition |
| 24 | heldout-greedy-baseline | hold-024 | consecutive_recipe_repetition |
| 25 | heldout-greedy-baseline | hold-025 | consecutive_recipe_repetition |
| 26 | heldout-greedy-baseline | hold-026 | consecutive_recipe_repetition, weekly_budget_exceeded |
| 27 | heldout-greedy-baseline | hold-027 | consecutive_recipe_repetition |
| 28 | heldout-greedy-baseline | hold-028 | consecutive_recipe_repetition |
| 29 | heldout-greedy-baseline | hold-029 | consecutive_recipe_repetition |
| 30 | heldout-greedy-baseline | hold-030 | consecutive_recipe_repetition |
| 31 | heldout-greedy-baseline | hold-031 | consecutive_recipe_repetition |
| 32 | heldout-greedy-baseline | hold-032 | consecutive_recipe_repetition |
| 33 | heldout-greedy-baseline | hold-033 | consecutive_recipe_repetition |
| 34 | heldout-greedy-baseline | hold-034 | consecutive_recipe_repetition |
| 35 | heldout-greedy-baseline | hold-035 | consecutive_recipe_repetition |
| 36 | heldout-greedy-baseline | hold-036 | consecutive_recipe_repetition |
| 37 | agent-benchmark | agent-005 | extraction_mismatch, clarification_mismatch |
| 38 | agent-benchmark | agent-014 | extraction_mismatch |
| 39 | agent-benchmark | agent-015 | extraction_mismatch |
| 40 | agent-benchmark | agent-016 | extraction_mismatch, clarification_mismatch |
| 41 | agent-benchmark | agent-017 | extraction_mismatch |
| 42 | agent-benchmark | agent-018 | extraction_mismatch |
| 43 | agent-benchmark | agent-019 | extraction_mismatch |
| 44 | agent-benchmark | agent-024 | extraction_mismatch, clarification_mismatch |
