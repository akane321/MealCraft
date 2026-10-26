import importlib.util

import pytest

from app.core.paths import repository_root
from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.meal_beam import MealBeamPlanner
from tests.test_diversity_greedy import setup_problem


def profiler_class():
    spec = importlib.util.spec_from_file_location(
        "planning_stage_profile", repository_root() / "scripts/planning_stage_profile.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PlanningStageProfile


def test_profile_preserves_plan_and_restores_methods():
    problem, objective = setup_problem()
    planner = AnnealingPlanner(objective, steps=20)
    expected = planner.solve(problem)
    original = MealBeamPlanner.meal_options
    with profiler_class()() as profile:
        actual = planner.solve(problem)
    assert actual == expected
    assert MealBeamPlanner.meal_options is original
    rows = profile.snapshot()
    assert rows["annealing_domains"]["calls"] == 1
    assert rows["annealing_proposal"]["calls"] > 0
    assert rows["independent_validation"]["calls"] > 0
    assert rows["shopping"]["calls"] > 0
    assert rows["objective"]["calls"] > 0
    assert all(row["seconds"] >= 0 and row["errors"] == 0 for row in rows.values())


def test_profile_preserves_exceptions_and_records_elapsed_time():
    ticks = iter([10.0, 12.5])
    profile = profiler_class()(clock=lambda: next(ticks))
    error = ValueError("invalid input")

    def fail():
        raise error

    with pytest.raises(ValueError) as raised:
        profile.measure("failing", fail)()
    assert raised.value is error
    assert profile.snapshot() == {"failing": {"calls": 1, "seconds": 2.5, "errors": 1}}


def test_profile_restores_methods_when_case_raises():
    original = MealBeamPlanner.meal_options
    with pytest.raises(RuntimeError), profiler_class()():
        raise RuntimeError("case failed")
    assert MealBeamPlanner.meal_options is original
