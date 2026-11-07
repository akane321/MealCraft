"""Cross-week completion recency is persisted product input and a bounded soft rank only."""

from datetime import date, timedelta

import pytest

from app.core.clock import today as local_today
from app.planning.recommendation_engine import (
    RECENCY_FADE_DAYS,
    RECENCY_PENALTY_POINTS,
    RecipeRecommendationEngine,
    cross_week_recency_penalty,
)
from app.schemas.meal_plan import PriorMealCompletion, WeeklyMealPlanRequest
from tests.test_recipe_feedback import WEEK, _ids, dishes  # noqa: F401
from tests.test_recipe_feedback import client as client


def request(age_days: int | None = None) -> WeeklyMealPlanRequest:
    start = date(2026, 11, 7)
    history = (
        [] if age_days is None else [PriorMealCompletion(recipe_id=1, completed_on=start - timedelta(days=age_days))]
    )
    return WeeklyMealPlanRequest(start_date=start, prior_completions=history)


def test_no_history_is_neutral_and_omitted_from_the_compatibility_contract():
    constraints = request()
    assert cross_week_recency_penalty(1, constraints) == 0
    assert "prior_completions" not in constraints.model_dump()


def test_recent_completion_has_the_bounded_maximum_penalty():
    assert cross_week_recency_penalty(1, request(0)) == RECENCY_PENALTY_POINTS
    assert cross_week_recency_penalty(2, request(0)) == 0


def test_recency_penalty_fades_linearly_and_is_neutral_after_three_weeks():
    assert cross_week_recency_penalty(1, request(7)) == pytest.approx(RECENCY_PENALTY_POINTS * 2 / 3)
    assert cross_week_recency_penalty(1, request(14)) == pytest.approx(RECENCY_PENALTY_POINTS / 3)
    assert cross_week_recency_penalty(1, request(RECENCY_FADE_DAYS)) == 0
    assert cross_week_recency_penalty(1, request(90)) == 0


def test_history_cannot_override_a_hard_time_constraint():
    recipes = dishes()
    for recipe_id, recipe in enumerate(recipes, start=1):
        recipe.id = recipe_id
        for line in recipe.recipe_ingredients:
            line.ingredient.allergens = []
    constraints = WeeklyMealPlanRequest(
        start_date=local_today(),
        max_cooking_time_minutes=5,
        prior_completions=[PriorMealCompletion(recipe_id=1, completed_on=local_today())],
    )
    ranked, excluded = RecipeRecommendationEngine().recommend(recipes, constraints)
    assert ranked == []
    assert {item.id for item in excluded} == {1, 2, 3, 4}


def test_completed_entry_is_loaded_into_the_next_real_product_planning_request(client, monkeypatch):
    first = client.post(
        "/api/plans/generate",
        json={"requires_halal": False, **WEEK, "start_date": local_today().isoformat(), "day_count": 1},
    ).json()
    completed = first["days"][0]
    assert (
        client.patch(
            f"/api/plans/{first['id']}/entries/{completed['entry_id']}", json={"status": "completed"}
        ).status_code
        == 200
    )

    seen = []
    original = RecipeRecommendationEngine.recommend

    def recorded(engine, recipes, constraints):
        seen.append(tuple(getattr(constraints, "prior_completions", ())))
        return original(engine, recipes, constraints)

    monkeypatch.setattr(RecipeRecommendationEngine, "recommend", recorded)
    payload = {
        "requires_halal": False,
        **WEEK,
        "start_date": (local_today() + timedelta(days=1)).isoformat(),
        "day_count": 1,
    }
    left = client.post("/api/plans/generate", json=payload)
    right = client.post("/api/plans/generate", json=payload)
    assert left.status_code == right.status_code == 201
    recipe_id = _ids()[completed["recipe"]["slug"]]
    assert any(any(item.recipe_id == recipe_id for item in history) for history in seen)
    assert [day["recipe"]["slug"] for day in left.json()["days"]] == [
        day["recipe"]["slug"] for day in right.json()["days"]
    ]
