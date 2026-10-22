from datetime import date

import pytest

from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat, integer
from app.schemas.planning_v2 import PlanningNutritionBand, PlanningPantryItem, PlanningRepetitionRules
from tests.test_diversity_greedy import setup_problem

HEURISTICS = [
    DiversityAwareGreedyPlanner,
    SharedObjectiveBeamPlanner,
    GraspPlanner,
    LocalSearchPlanner,
    AnnealingPlanner,
]


def two_trips():
    problem, objective = setup_problem(3)
    problem.slots[0].trip = 1
    problem.slots[1].trip = 2
    problem.slots[1].planned_date = date(2026, 10, 27)
    problem.products[0].package_quantity = 100
    return problem, objective


@pytest.mark.parametrize("planner", HEURISTICS)
def test_each_shopping_trip_has_the_full_weekly_budget(planner):
    problem, objective = two_trips()
    result = planner(objective).solve(problem)
    assert result.status == "feasible"
    assert result.validation.purchase_total_sgd == 4
    assert result.validation.status == "passed"


@pytest.mark.parametrize("planner", HEURISTICS)
def test_budget_reserves_a_required_meal_beyond_one_step(planner):
    problem, objective = setup_problem(5)
    problem.slots.append(
        problem.slots[1].model_copy(
            update={"slot_id": "s2", "planned_date": date(2026, 10, 21), "locked_recipe_id": "c"}
        )
    )
    problem.recipes[0].ingredients[0].ingredient_id = "expensive"
    problem.products.append(
        problem.products[0].model_copy(
            update={"product_id": "expensive", "ingredient_id": "expensive", "package_quantity": 100, "price_sgd": 3}
        )
    )
    problem.products[0].package_quantity = 100
    problem.products[0].price_sgd = 1.5
    # b/c can share a larger, cheaper bag; buying a first consumes too much budget.
    problem.products.append(
        problem.products[0].model_copy(update={"product_id": "rice-big", "package_quantity": 300, "price_sgd": 4})
    )
    result = planner(objective).solve(problem)
    assert result.status == "feasible"
    assert all(a.recipe_id != "a" for a in result.assignments)


@pytest.mark.parametrize("planner", HEURISTICS)
def test_ingredient_minimum_is_reachable_before_last_slot(planner):
    problem, objective = setup_problem(20)
    problem.slots += [
        problem.slots[0].model_copy(update={"slot_id": f"s{i}", "planned_date": date(2026, 10, 19 + i)}) for i in (2, 3)
    ]
    problem.recipes[1].ingredients[0].ingredient_id = "mushroom"
    problem.products.append(
        problem.products[0].model_copy(update={"ingredient_id": "mushroom", "product_id": "mushroom-bag"})
    )
    problem.repetition_rules = PlanningRepetitionRules(ingredient_meals=[{"ingredient_id": "mushroom", "min_meals": 3}])
    result = planner(objective).solve(problem)
    assert result.status == "feasible"
    assert sum(a.recipe_id == "b" for a in result.assignments) >= 3


def test_completion_bound_does_not_buy_shared_package_twice():
    problem, objective = setup_problem(2)
    result = DiversityAwareGreedyPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert sum(r.packages for r in result.shopping) == 1


def test_unknown_pantry_is_not_deducted_by_native_model():
    problem, objective = setup_problem()
    problem.pantry = [PlanningPantryItem(ingredient_id="rice", quantity=None, unit="g")]
    result = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert result["status"] == "optimal_for_native_model"
    assert result["score"] == exact["score"]


def test_native_two_trip_budget_matches_enumeration():
    problem, objective = two_trips()
    result = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert result["status"] == "optimal_for_native_model"
    assert result["score"] == exact["score"]


def test_scaled_float_roundoff_does_not_reject_grid_coefficient():
    assert integer(10.000000000000002, 100000000) == 1000000000
    with pytest.raises(ValueError, match="precision"):
        integer(10.000000005, 100000000)


@pytest.mark.parametrize("planner", HEURISTICS)
def test_empty_optional_prefix_with_soft_selected_average(planner):
    problem, objective = setup_problem()
    problem.slots[0].required = False
    problem.nutrition_bands = [
        PlanningNutritionBand(
            metric="calories_kcal", scope="horizon_average", average_basis="selected_slots", lower=500, hard=False
        )
    ]
    objective.scales["nutrition_calories_kcal_horizon_average"] = 500
    result = planner(objective).solve(problem)
    assert result.status == "feasible"
    assert result.validation.status == "passed"
