import pytest

from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.schemas.planning_v2 import PlanningNutritionBand
from tests.test_diversity_greedy import setup_problem


@pytest.mark.parametrize("planner", [GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner, AnnealingPlanner])
def test_search_reproducible_valid_and_never_worse_than_seed(planner):
    problem, objective = setup_problem()
    baseline = DiversityAwareGreedyPlanner(objective).solve(problem)
    result = planner(objective).solve(problem)
    assert result == planner(objective).solve(problem)
    assert result.status == "feasible"
    assert objective.score_validated(problem, result.assignments, result.validation) <= objective.score_validated(
        problem, baseline.assignments, baseline.validation
    )


@pytest.mark.parametrize("planner", [GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner, AnnealingPlanner])
def test_search_never_accepts_over_budget_or_claims_infeasibility(planner):
    problem, objective = setup_problem(1.99)
    result = planner(objective).solve(problem)
    assert result.status == "candidate_rejected"
    assert result.validation.status != "passed"


def test_beam_recovers_from_greedy_horizon_rejection():
    problem, objective = setup_problem()
    for recipe, calories in zip(problem.recipes, (600, 600, 200), strict=True):
        recipe.nutrients_per_serving.calories_kcal = calories
    problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope="horizon_average", lower=550)]
    assert DiversityAwareGreedyPlanner(objective).solve(problem).status == "candidate_rejected"
    result = SharedObjectiveBeamPlanner(objective).solve(problem)
    assert result.status == "feasible"
    assert result.validation.status == "passed"


def test_beam_budget_keeps_validated_incumbent():
    problem, objective = setup_problem()
    result = SharedObjectiveBeamPlanner(objective, max_expansions=1).solve(problem)
    assert result.status == "feasible"
    assert any("expansions=1;" in warning for warning in result.trace.warnings)


def test_exact_reference_counts_every_combination_and_refuses_truncation():
    problem, objective = setup_problem()
    reference = EnumeratedReference(objective)
    result = reference.solve_reference(problem)
    assert result["status"] == "optimal_for_generated_options"
    assert result["checked"] == result["total"] == 9
    assert result["score"] == (0, -2, 0, 0, 0.5, 200)
    limited = reference.solve_reference(problem, max_combinations=8)
    assert limited["status"] == "limit_exceeded"
    assert limited["checked"] == 0


def test_exact_reference_distinguishes_rejection_from_optimality():
    problem, objective = setup_problem(1.99)
    result = EnumeratedReference(objective).solve_reference(problem)
    assert result["status"] == "no_valid_generated_assignment"
    assert result["score"] is None
