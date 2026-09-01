# MealCraft MVP Evaluation

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
| `fixture_mapping_count` | 34 | - |
| `used_ingredient_count` | 34 | - |
| `fixture_mapping_coverage` | 1.0 | PASS |
| `complete_grocery_rate` | 1.0 | PASS |

## Scenario results

| Scenario | Expected | Actual | Violations |
|---|---|---|---:|
| baseline | feasible | feasible | 0 |
| vegetarian | feasible | feasible | 0 |
| vegan | feasible | feasible | 0 |
| gluten-free | feasible | feasible | 0 |
| dairy-free | feasible | feasible | 0 |
| soy-allergy | feasible | feasible | 0 |
| fish-allergy | feasible | feasible | 0 |
| egg-allergy | feasible | feasible | 0 |
| sesame-allergy | feasible | feasible | 0 |
| exclude-chicken | feasible | feasible | 0 |
| sodium-hard-limit | feasible | feasible | 0 |
| quick-meals | feasible | feasible | 0 |
| lower-calorie-soft-preference | feasible | feasible | 0 |
| low-sugar-soft-preference | feasible | feasible | 0 |
| nutrition-targets | feasible | feasible | 0 |
| known-pantry-quantity | feasible | feasible | 0 |
| unknown-pantry-quantity | feasible | feasible | 0 |
| per-meal-budget | feasible | feasible | 0 |
| impossible-five-minute-limit | rejected | rejected | 0 |
| impossible-vegan-ten-minute-limit | rejected | rejected | 0 |
