"""Product planning and previews never price candidate ingredients against the network."""

from datetime import date

import pytest

from app.api.routes.meal_plans import build_meal_plan_service
from app.db.session import get_db_session
from app.main import app
from app.models.meal_plan import MealPlan
from app.products.provider import FairPriceProductProvider
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.services.product import ProductSearchService
from tests.test_planning_capability import _dish, dish_client


@pytest.fixture
def offline_searches(monkeypatch):
    searched = []
    original = ProductSearchService.search

    def search(self, query, *, live, **kwargs):
        assert not live, "a candidate/preview attempted live pricing"
        searched.append(query)
        return original(self, query, live=live, **kwargs)

    monkeypatch.setattr(ProductSearchService, "search", search)
    # Confirmation may refresh the chosen basket; never access the real site in a unit test.
    monkeypatch.setattr(FairPriceProductProvider, "search", lambda *args, **kwargs: [])
    return searched


def dishes():
    return [
        _dish("tofu-bowl", "main", "firm_tofu", 100, calories=400),
        _dish("chickpea-stew", "main", "chickpea", 100, calories=400),
        _dish("broccoli-side", "side", "broccoli", 100, calories=100),
        _dish("tomato-soup", "soup", "tomato", 100, calories=100),
    ]


@pytest.mark.parametrize("method", ["check", "week_floor", "cheapest_week", "plan_dishes"])
def test_every_live_planning_entry_uses_offline_candidate_prices(monkeypatch, offline_searches, method):
    with dish_client(monkeypatch, dishes()):
        database = app.dependency_overrides[get_db_session]()
        session = next(database)
        try:
            service = build_meal_plan_service(session, household_id=0)
            request = WeeklyMealPlanRequest(
                household_size=2,
                weekly_budget_sgd=100,
                pricing_mode="live",
                meal_composition=[{"role_id": "main", "courses": ["main"]}],
            )
            if method == "plan_dishes":
                result = service.plan_dishes(request, first_day=1, day_count=1, rest=[])
                assert result
            else:
                result = getattr(service, method)(request)
                if method == "check":
                    assert result is None
                else:
                    assert result is not None
            assert request.pricing_mode == "live"  # never mutate the request or its found-week key
            assert offline_searches
        finally:
            database.close()


@pytest.mark.parametrize("preview", ["replace", "shape", "variety"])
def test_live_plan_preview_keeps_network_out_of_selection(monkeypatch, offline_searches, preview):
    with dish_client(monkeypatch, dishes()) as client:
        generated = client.post(
            "/api/plans/generate",
            json={
                "household_size": 2,
                "weekly_budget_sgd": 100,
                "pricing_mode": "live",
                "start_date": date.today().isoformat(),
            },
        )
        assert generated.status_code == 201, generated.text
        plan = generated.json()
        assert plan["grocery_estimate"]["pricing_mode"] == "live"
        before = len(offline_searches)
        if preview == "replace":
            response = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={
                    "entry_id": plan["days"][0]["entry_id"],
                    "event_type": "REPLACE_MEAL",
                },
            )
        elif preview == "shape":
            response = client.post(
                f"/api/plans/{plan['id']}/shape/preview",
                json={
                    "meal_type": "lunch",
                    "roles": [{"role_id": "main", "courses": ["main"]}],
                },
            )
        else:
            from app.api.routes.meal_plans import build_replanning_service

            database = app.dependency_overrides[get_db_session]()
            session = next(database)
            try:
                household_id = session.get(MealPlan, plan["id"]).household_id
                build_replanning_service(session, household_id=household_id).preview_variety(plan_id=plan["id"])
                assert len(offline_searches) > before
            finally:
                database.close()
            return
        assert response.status_code == 201, response.text
        assert len(offline_searches) > before
