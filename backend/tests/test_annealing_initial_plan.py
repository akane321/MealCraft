import pytest

from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from tests.test_diversity_greedy import setup_problem


def test_supplied_beam_seed_is_retained_without_running_greedy(monkeypatch):
    problem, objective = setup_problem()
    initial = DiversityAwareGreedyPlanner(objective).solve(problem)
    before = initial.model_dump()

    def forbidden(*args, **kwargs):
        raise AssertionError("Supplied seed must not be replaced by a fresh greedy search")

    monkeypatch.setattr(DiversityAwareGreedyPlanner, "solve", forbidden)
    result = AnnealingPlanner(objective, steps=20).solve(problem, initial=initial)
    assert result.validation.status == "passed"
    assert objective.score_validated(problem, result.assignments, result.validation) <= objective.score_validated(
        problem, initial.assignments, initial.validation
    )
    assert initial.model_dump() == before


def test_seed_report_from_a_different_budget_is_not_trusted():
    problem, objective = setup_problem()
    initial = DiversityAwareGreedyPlanner(objective).solve(problem)
    problem.purchase_budget_sgd = 1
    with pytest.raises(ValueError, match="current problem"):
        AnnealingPlanner(objective).solve(problem, initial=initial)


def test_rejected_seed_is_returned_without_exploration():
    problem, objective = setup_problem(1)
    initial = DiversityAwareGreedyPlanner(objective).solve(problem)
    before = initial.model_dump()
    result = AnnealingPlanner(objective).solve(problem, initial=initial)
    assert result.status == initial.status != "feasible"
    assert initial.model_dump() == before
