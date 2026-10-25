from datetime import timedelta

import pytest

from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.algorithm_reference import EnumeratedReference
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.planning.near_duplicate_groups import DishGroups
from tests.test_algorithm_price_priority import packet, price_objective


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
@pytest.mark.parametrize("minimum,price", [(0, 2), (1, 2), (2, 4)])
def test_minimum_kinds_price_matches_exhaustive(planner_type, minimum, price):
    problem, objective = packet()
    objective = price_objective(objective)
    actual = planner_type(objective).solve_exact(problem, min_dish_kinds=minimum)
    expected = EnumeratedReference(objective).solve_reference(problem, min_dish_kinds=minimum)
    assert actual["status"].startswith("optimal_for_")
    assert actual["score"] == expected["score"]
    assert actual["minimum_checkout_sgd"] == price
    assert actual["min_dish_kinds"] == minimum


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
@pytest.mark.parametrize("budget,minimum", [(10, 3), (2, 2)])
def test_impossible_kind_count_or_budget_has_no_minimum(planner_type, budget, minimum):
    problem, objective = packet()
    problem.purchase_budget_sgd = budget
    objective = price_objective(objective)
    actual = planner_type(objective).solve_exact(problem, min_dish_kinds=minimum)
    expected = EnumeratedReference(objective).solve_reference(problem, min_dish_kinds=minimum)
    assert not actual["status"].startswith("optimal_for_")
    assert expected["score"] is None
    assert actual.get("minimum_checkout_sgd") is None


@pytest.mark.parametrize("minimum", [-1, 1.5, True, "2"])
def test_invalid_minimum_is_rejected(minimum):
    problem, objective = packet()
    for planner_type in (SharedScoreCpSat, NativeSharedScoreCpSat, EnumeratedReference):
        planner = planner_type(objective)
        solve = planner.solve_reference if planner_type is EnumeratedReference else planner.solve_exact
        with pytest.raises(ValueError, match="min_dish_kinds"):
            solve(problem, min_dish_kinds=minimum)


@pytest.mark.parametrize("planner_type", [SharedScoreCpSat, NativeSharedScoreCpSat])
def test_at_least_four_kinds_uses_distinct_groups_not_recipe_ids(planner_type):
    problem, original = packet()
    for key in ("d", "e"):
        problem.recipes.append(problem.recipes[0].model_copy(deep=True, update={"recipe_id": key, "title": key}))
    first = problem.slots[0]
    problem.slots = [
        first.model_copy(update={"slot_id": f"s{i}", "planned_date": first.planned_date + timedelta(days=i)})
        for i in range(4)
    ]
    groups = DishGroups(
        original.groups.policy, original.groups.groups + (("d",), ("e",)), (), original.groups.near_pairs
    )
    objective = AlgorithmObjective(groups, {k: k for k in "abcde"}, dict.fromkeys("abcde", 0), priority="price")
    result = planner_type(objective).solve_exact(problem, min_dish_kinds=4)
    exact = EnumeratedReference(objective).solve_reference(problem, min_dish_kinds=4)
    assert result["status"].startswith("optimal_for_")
    assert result["score"] == exact["score"]
    assert result["score"][2] == -4
    assert result["minimum_checkout_sgd"] == 6
