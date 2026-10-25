"""The product's checked-price route, including its minimum-dish requirement."""

from datetime import date

from app.api.routes.meal_plans import build_meal_plan_service
from app.planning import product_path
from app.schemas.meal_plan import WeeklyMealPlanRequest
from tests.test_planning_capability import COMPOSITION, _catalog_session, composed_client  # noqa: F401


def test_checked_price_route_uses_price_priority_and_keeps_requested_variety(composed_client, monkeypatch):  # noqa: F811
    seen = []
    original = product_path.improve_product_plan

    def observe(problem, initial, losses, **kwargs):
        result, trace = original(problem, initial, losses, **kwargs)
        seen.append((result, trace))
        return result, trace

    monkeypatch.setattr(product_path, "improve_product_plan", observe)
    request = WeeklyMealPlanRequest(
        start_date=date(2026, 10, 26),
        household_size=4,
        pricing_mode="fixture",
        max_cooking_time_minutes=90,
        meal_composition=COMPOSITION[:2],
    )
    with _catalog_session() as session:
        service = build_meal_plan_service(session, 1)
        price = service.cheapest_week(request, minimum_distinct_dishes=4)
    assert price is not None and price > 0
    assert seen
    result, trace = seen[-1]
    assert trace["objective_priority"] == "price"
    assert trace["after"] <= trace["before"]
    assert len({a.recipe_id for a in result[0]}) >= 4
    assert result[2].status == "passed"
    assert result[2].purchase_total_sgd == price
