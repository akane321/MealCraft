# MealCraft Planning Evaluation

**System:** `mealcraft-planner`

**Dataset:** `data/evaluation/dev/planning-v1.json`

**Overall result: PASS**

## Metrics

| Metric | Result | Gate |
|---|---:|:---:|
| `catalog_recipe_count` | 30 | PASS |
| `catalog_ingredient_count` | 34 | - |
| `scenario_count` | 20 | - |
| `scenario_expectation_rate` | 1.0 | PASS |
| `feasible_scenario_success_rate` | 1.0 | PASS |
| `hard_constraint_violation_count` | 0 | PASS |
| `determinism_rate` | 1.0 | PASS |
| `consecutive_repetition_count` | 0 | PASS |
| `mean_distinct_recipes` | 6.2222 | - |
| `fixture_mapping_count` | 34 | - |
| `used_ingredient_count` | 34 | - |
| `fixture_mapping_coverage` | 1.0 | PASS |
| `complete_grocery_rate` | 1.0 | PASS |
| `failure_case_count` | 0 | - |

## Category results

| Category | N | Expectation rate | Violations | Failures |
|---|---:|---:|---:|---:|
| allergen | 4 | 1.0 | 0 | 0 |
| basic | 1 | 1.0 | 0 | 0 |
| budget | 1 | 1.0 | 0 | 0 |
| dietary | 4 | 1.0 | 0 | 0 |
| exclusion | 1 | 1.0 | 0 | 0 |
| infeasible | 2 | 1.0 | 0 | 0 |
| nutrition | 2 | 1.0 | 0 | 0 |
| pantry | 2 | 1.0 | 0 | 0 |
| preference | 2 | 1.0 | 0 | 0 |
| time | 1 | 1.0 | 0 | 0 |

## Failure cases

| ID | Scenario | Category | Reasons |
|---|---|---|---|
| - | No failures recorded | - | - |
