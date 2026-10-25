from datetime import timedelta

import pytest

from app.planning.algorithm_lns import LargeNeighborhoodPlanner
from app.planning.algorithm_reference import EnumeratedReference, evaluate
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from tests.test_algorithm_member_diversity import family, shared_family
from tests.test_algorithm_price_priority import packet, price_objective


@pytest.mark.parametrize("factory", [lambda: family(2), lambda: family(6), shared_family])
def test_whole_neighborhood_matches_enumeration_for_families(factory):
    problem, objective = factory()
    planner = LargeNeighborhoodPlanner(objective, destroy_size=2)
    result = planner.solve(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert result.validation.status == "passed"
    assert objective.score_validated(problem, result.assignments, result.validation) == exact["score"]
    assert objective.diversity(problem, result.assignments) == exact["diversity"]
    assert len(planner.repairs) == 1
    assert result.trace.deterministic is False
    assert planner.repairs[0]["workers"] == 4
    assert planner.repairs[0]["solver_seed"] == 0


def test_joint_repair_escapes_package_cost_local_minimum():
    problem, objective = packet()
    problem.products[1].price_sgd = 3
    objective = price_objective(objective)
    planner = LargeNeighborhoodPlanner(objective)
    seed = DiversityAwareGreedyPlanner(objective).solve(problem)
    score, assignments, shopping, report = evaluate(planner, problem, (("s0", ((None, "c"),)), ("s1", ((None, "c"),))))
    seed.assignments, seed.shopping, seed.validation = assignments, shopping, report
    # Switching either meal alone adds a second package; switching both saves money.
    one_score, *_ = evaluate(planner, problem, (("s0", ((None, "a"),)), ("s1", ((None, "c"),))))
    assert one_score > score
    result = planner.solve(problem, initial=seed)
    assert result.validation.purchase_total_sgd == 2
    assert planner.repairs[0]["accepted"]
    assert seed.validation.purchase_total_sgd == 3  # supplied seed is not mutated


def test_native_fixed_meal_and_optional_empty_remain_fixed():
    problem, objective = packet()
    problem.slots[0].required = False
    result = NativeSharedScoreCpSat(objective).solve_exact(problem, time_limit=None, fixed_choices={"s0": ()})
    assert result["status"] == "optimal_for_native_model"
    assert all(a["slot_id"] != "s0" for a in result["assignments"])
    with pytest.raises(ValueError, match="unknown slot"):
        NativeSharedScoreCpSat(objective).solve_exact(problem, fixed_choices={"missing": ()})
    with pytest.raises(ValueError, match="outside"):
        NativeSharedScoreCpSat(objective).solve_exact(problem, fixed_choices={"s1": ((None, "absent"),)})


def test_two_trip_budget_is_not_collapsed_to_one_total():
    problem, objective = packet()
    problem.purchase_budget_sgd = 2
    problem.slots[1].planned_date += timedelta(days=7)
    problem.slots[0].trip, problem.slots[1].trip = 1, 2
    result = LargeNeighborhoodPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert result.validation.status == "passed"
    assert result.validation.purchase_total_sgd == 4


@pytest.mark.parametrize("status", ["unknown", "infeasible", "validation_rejected"])
def test_failed_repair_keeps_valid_seed(monkeypatch, status):
    problem, objective = packet()
    initial = DiversityAwareGreedyPlanner(objective).solve(problem)
    monkeypatch.setattr(NativeSharedScoreCpSat, "solve_exact", lambda *a, **kw: {"status": status})
    planner = LargeNeighborhoodPlanner(objective, iterations=2)
    result = planner.solve(problem, initial=initial)
    assert result.assignments == initial.assignments
    assert result.validation.status == "passed"
    assert not any(row["accepted"] for row in planner.repairs)
    assert len(planner.repairs) == 1  # A failed whole-horizon repair is not retried identically.


def test_partial_repair_has_reproducible_schedule_not_assignment_guarantee():
    problem, objective = packet()
    problem.slots.append(problem.slots[-1].model_copy(update={"slot_id": "s2"}))
    planners = [LargeNeighborhoodPlanner(objective, seed=9, iterations=3, destroy_size=2) for _ in range(2)]
    results = [planner.solve(problem) for planner in planners]
    assert all(result.trace.deterministic is False for result in results)
    assert [objective.score_validated(problem, result.assignments, result.validation) for result in results] == [
        objective.score_validated(problem, results[0].assignments, results[0].validation)
    ] * 2
    assert [row["released"] for row in planners[0].repairs] == [row["released"] for row in planners[1].repairs]
    assert all(len(row["released"]) == 2 for row in planners[0].repairs)
    assert results[0].validation.status == "passed"


def test_locked_meal_is_preserved():
    problem, objective = packet()
    problem.slots[0].locked_recipe_id = "b"
    result = LargeNeighborhoodPlanner(objective).solve(problem)
    assert next(a.recipe_id for a in result.assignments if a.slot_id == "s0") == "b"


def test_no_feasible_seed_does_not_call_repair(monkeypatch):
    problem, objective = packet()
    problem.purchase_budget_sgd = 0.01
    monkeypatch.setattr(NativeSharedScoreCpSat, "solve_exact", lambda *a, **kw: pytest.fail("unexpected repair"))
    planner = LargeNeighborhoodPlanner(objective)
    assert planner.solve(problem).status != "feasible"
    assert planner.repairs == []


def test_unsupported_native_input_is_reported_without_losing_seed(monkeypatch):
    problem, objective = packet()

    def unsupported(*args, **kwargs):
        raise ValueError("Unsupported precision")

    monkeypatch.setattr(NativeSharedScoreCpSat, "solve_exact", unsupported)
    planner = LargeNeighborhoodPlanner(objective)
    result = planner.solve(problem)
    assert result.status == "feasible"
    assert planner.repairs[0]["reason"] == "Unsupported precision"
    assert not planner.repairs[0]["accepted"]


def test_supplied_seed_is_revalidated():
    problem, objective = packet()
    initial = DiversityAwareGreedyPlanner(objective).solve(problem)
    initial.assignments = []
    with pytest.raises(ValueError, match="independent validation"):
        LargeNeighborhoodPlanner(objective).solve(problem, initial=initial)


@pytest.mark.parametrize("kwargs", [{"iterations": 0}, {"destroy_size": -1}, {"destroy_size": True}])
def test_invalid_parameters(kwargs):
    _, objective = packet()
    with pytest.raises(ValueError, match="positive integers"):
        LargeNeighborhoodPlanner(objective, **kwargs)
