"""ADR-0091: an omitted halal declaration must not become a non-halal HTTP request."""

import pytest

from app.schemas.meal_plan import WeeklyMealPlanRequest
from tests.test_recipes import recipe_client as recipe_client


@pytest.mark.parametrize("url", ["/api/plans/generate", "/api/recommendations/recipes"])
@pytest.mark.parametrize("declaration", [{}, {"requires_halal": None}])
def test_http_requires_an_explicit_halal_boolean(recipe_client, url, declaration):
    response = recipe_client.post(url, json={"household_size": 2, **declaration})
    assert response.status_code == 422, response.text
    assert any(item["loc"] == ["body", "requires_halal"] for item in response.json()["detail"])


@pytest.mark.parametrize("url", ["/api/plans/generate", "/api/recommendations/recipes"])
def test_http_explicit_non_halal_request_still_works(recipe_client, url):
    response = recipe_client.post(url, json={"household_size": 2, "requires_halal": False})
    assert response.status_code in {200, 201}, response.text


def test_legacy_stored_domain_request_is_not_a_new_http_declaration():
    old = WeeklyMealPlanRequest.model_validate({"household_size": 2})
    assert old.requires_halal is False
