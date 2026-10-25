from datetime import timedelta

import pytest

from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.algorithm_reference import EnumeratedReference
from app.planning.near_duplicate_groups import DishGroups, NearDuplicatePolicy
from app.schemas.planning_v2 import PlanningNutritionBand, PlanningPantryItem
from tests.test_diversity_greedy import setup_problem
from tests.test_planning_meal_composition import problem as composed_problem


def test_cp_sat_table_matches_independent_full_enumeration():
    problem, objective = setup_problem()
    actual = SharedScoreCpSat(objective).solve_exact(problem)
    expected = EnumeratedReference(objective).solve_reference(problem)
    assert actual["status"] == "optimal_for_count_table"
    assert actual["score"] == expected["score"]
    assert actual["count_states"] == 6


def test_cp_sat_table_refuses_truncation_and_preserves_nonexchangeable_slots():
    problem, objective = setup_problem()
    planner = SharedScoreCpSat(objective)
    assert planner.solve_exact(problem, max_states=5)["status"] == "limit_exceeded"
    problem.slots[1].servings = 2
    result = planner.solve_exact(problem)
    assert result["scope"] == "ordered generated meal options"
    assert result["count_states"] == 9


def test_cp_sat_table_does_not_call_over_budget_optimal():
    problem, objective = setup_problem(1.99)
    assert SharedScoreCpSat(objective).solve_exact(problem)["status"] == "no_valid_count_state"


def household_week():
    problem = composed_problem()
    first = problem.slots[0]
    problem.slots = [
        first.model_copy(
            update={
                "slot_id": f"d{i}",
                "planned_date": first.planned_date + timedelta(days=i),
                "trip": 1 if i < 4 else 2,
            }
        )
        for i in range(7)
    ]
    problem.pantry = [PlanningPantryItem(ingredient_id="chicken-base", quantity=300, unit="g")]
    problem.nutrition_bands = [
        PlanningNutritionBand(metric="calories_kcal", scope=scope, lower=100, upper=1000)
        for scope in ("per_slot", "per_day", "horizon_average")
    ]
    keys = {r.recipe_id: r.recipe_id for r in problem.recipes}
    groups = DishGroups(NearDuplicatePolicy("household-dev", 0.2, 0.05, 0.7), tuple((k,) for k in keys), (), ())
    return problem, AlgorithmObjective(groups, keys, dict.fromkeys(keys, 0))


def test_composed_week_nutrition_and_two_trips_match_full_enumeration():
    problem, objective = household_week()
    actual = SharedScoreCpSat(objective).solve_exact(problem)
    expected = EnumeratedReference(objective).solve_reference(problem)
    assert actual["status"] == "optimal_for_generated_options"
    assert actual["score"] == expected["score"]
    assert {row["trip"] for row in actual["shopping"]} == {1, 2}
    assert sum(row["pantry_deduction"] for row in actual["shopping"] if row["ingredient_id"] == "chicken-base") == 300
    assert {a["role_id"] for a in actual["assignments"]} >= {"main", "vegetable"}


@pytest.mark.parametrize("bounds", [{"upper": 1}, {"lower": 10000}])
def test_impossible_nutrition_bound_is_not_softened(bounds):
    problem, objective = household_week()
    problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope="per_slot", **bounds)]
    result = SharedScoreCpSat(objective).solve_exact(problem)
    assert result["score"] is None
    assert result["status"] == "no_valid_count_state"
