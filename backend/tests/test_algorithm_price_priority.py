from datetime import timedelta

import pytest

from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.algorithm_reference import EnumeratedReference
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from tests.test_diversity_greedy import setup_problem


def packet():
    problem, objective = setup_problem(10)
    # A second dish kind needs a second whole package, despite equal serving cost.
    problem.recipes[2].ingredients[0].ingredient_id = "beans"
    problem.products.append(
        problem.products[0].model_copy(update={"ingredient_id": "beans", "product_id": "beans-bag"})
    )
    return problem, objective


def price_objective(objective):
    return AlgorithmObjective(objective.groups, objective.keys, objective.ranking, objective.scales, priority="price")


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_price_first_finds_cheaper_week_than_variety_first(planner_type):
    problem, objective = packet()
    varied = planner_type(objective).solve_exact(problem)
    priced = planner_type(price_objective(objective)).solve_exact(problem)
    exact = EnumeratedReference(price_objective(objective)).solve_reference(problem)
    assert varied["score"][-1] == 400
    assert priced["status"].startswith("optimal_for_")
    assert priced["score"] == exact["score"]
    assert priced["score"][0] == 200
    assert priced["objective_priority"] == "price"
    assert priced["minimum_checkout_sgd"] == 2


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_price_first_preserves_separate_trip_budgets(planner_type):
    problem, objective = packet()
    problem.purchase_budget_sgd = 2
    problem.slots[1].planned_date += timedelta(days=7)
    problem.slots[0].trip, problem.slots[1].trip = 1, 2
    priced = planner_type(price_objective(objective)).solve_exact(problem)
    exact = EnumeratedReference(price_objective(objective)).solve_reference(problem)
    assert priced["status"].startswith("optimal_for_")
    assert priced["score"] == exact["score"]
    assert priced["minimum_checkout_sgd"] == 4


def test_unproven_reference_never_reports_minimum():
    problem, objective = packet()
    result = SharedScoreCpSat(price_objective(objective)).solve_exact(problem, max_states=1)
    assert result["status"] == "limit_exceeded"
    assert result.get("minimum_checkout_sgd") is None


def test_invalid_priority_is_rejected():
    _, objective = packet()
    with pytest.raises(ValueError, match="priority"):
        AlgorithmObjective(objective.groups, objective.keys, objective.ranking, priority="cheapish")


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_equal_price_keeps_variety_tiebreaker(planner_type):
    problem, objective = setup_problem()
    result = planner_type(price_objective(objective)).solve_exact(problem)
    assert result["score"][:3] == (200, 0, -2)


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_infeasible_budget_never_reports_minimum(planner_type):
    problem, objective = setup_problem(1.99)
    result = planner_type(price_objective(objective)).solve_exact(problem)
    assert not result["status"].startswith("optimal_for_")
    assert result.get("minimum_checkout_sgd") is None


def test_native_timeout_never_reports_minimum():
    problem, objective = packet()
    result = NativeSharedScoreCpSat(price_objective(objective)).solve_exact(problem, time_limit=1e-12)
    assert result["status"] == "unknown"
    assert result.get("minimum_checkout_sgd") is None


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_price_first_composed_week_preserves_nutrition_and_pantry(planner_type):
    from tests.test_algorithm_cp_sat import household_week

    problem, objective = household_week()
    result = planner_type(price_objective(objective)).solve_exact(problem)
    exact = EnumeratedReference(price_objective(objective)).solve_reference(problem)
    assert result["status"].startswith("optimal_for_")
    assert result["score"] == exact["score"]
    assert sum(row["pantry_deduction"] for row in result["shopping"]) == 300
