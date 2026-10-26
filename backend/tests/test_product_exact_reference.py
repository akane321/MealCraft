from datetime import date

import pytest

from app.api.routes.meal_plans import build_meal_plan_service
from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.meal_beam import MealBeamPlanner
from app.planning.product_path import product_validation
from app.schemas.meal_plan import WeeklyMealPlanRequest
from tests.test_diversity_greedy import setup_problem
from tests.test_planning_capability import COMPOSITION, _catalog_session, composed_client  # noqa: F401


def test_exact_reference_preserves_date_sensitive_product_callback():
    problem, objective = setup_problem(100)
    candidates = MealBeamPlanner()

    def validate(problem, assignments, shopping):
        report = product_validation(candidates.validator, problem, assignments, shopping, minimum_distinct_dishes=2)
        if assignments[0].recipe_id != "c":
            return report.model_copy(update={"status": "failed", "hard_failure_count": 1})
        return report

    brute = EnumeratedReference(objective, candidates).solve_reference(problem, validate=validate)
    exact = SharedScoreCpSat(objective, candidates).solve_exact(problem, validate=validate)
    assert exact["status"] == "optimal_for_generated_options"
    assert exact["scope"] == "ordered generated meal options"
    assert exact["score"] == brute["score"]
    assert exact["assignments"][0]["recipe_id"] == "c"
    assert len({a["recipe_id"] for a in exact["assignments"]}) == 2


@pytest.mark.parametrize("days", [2, 3])
def test_product_checked_price_matches_small_exact_reference(composed_client, monkeypatch, days):  # noqa: F811
    captured = []
    original = AnnealingPlanner.solve

    def observe(self, problem, *, initial=None, validate=None):
        result = original(self, problem, initial=initial, validate=validate)
        captured.append((problem, self.objective, self.candidates, validate))
        return result

    monkeypatch.setattr(AnnealingPlanner, "solve", observe)
    request = WeeklyMealPlanRequest(
        start_date=date(2026, 10, 26),
        day_count=days,
        household_size=4,
        pricing_mode="fixture",
        max_cooking_time_minutes=90,
        meal_composition=COMPOSITION[:2],
    )
    with _catalog_session() as session:
        price = build_meal_plan_service(session, 1).cheapest_week(request, minimum_distinct_dishes=4)
    assert price is not None
    problem, objective, candidates, validate = captured[-1]
    assert objective.priority == "price"
    assert validate is not None
    brute = EnumeratedReference(objective, candidates).solve_reference(problem, validate=validate)
    exact = SharedScoreCpSat(objective, candidates).solve_exact(problem, validate=validate)
    assert exact["status"] == brute["status"] == "optimal_for_generated_options"
    assert exact["score"] == brute["score"]
    assert len({a["recipe_id"] for a in exact["assignments"]}) >= 4
    assert price == pytest.approx(exact["minimum_checkout_sgd"], abs=0.005)
