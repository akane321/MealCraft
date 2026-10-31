"""ADR-0091 item 2, kept by ADR-0104: an omitted halal declaration must not become a non-halal HTTP request."""

import pytest

from app.schemas.meal_plan import WeeklyMealPlanRequest
from tests.test_recipes import recipe_client as recipe_client


@pytest.mark.parametrize(
    "url",
    [
        "/api/plans/generate",
        "/api/recommendations/recipes",
        "/api/ingredient-substitutions/review",
        "/api/ingredient-substitutions/suggest",
        "/api/external-recipes/intake",
        "/api/external-recipes/search-and-intake",
    ],
)
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


PROFILE = {"name": "Tan household", "members": [{"name": "Ann", "servings_per_meal": 1}]}


@pytest.mark.parametrize("declaration", [{}, {"requires_halal": None}])
@pytest.mark.parametrize("method", ["post", "put"])
def test_a_household_profile_write_requires_an_explicit_halal_boolean(recipe_client, method, declaration):
    created = recipe_client.post("/api/household-profiles", json={**PROFILE, "requires_halal": False}).json()
    url = "/api/household-profiles" if method == "post" else f"/api/household-profiles/{created['id']}"
    body = {**PROFILE, **declaration, **({"expected_version": 1} if method == "put" else {})}
    response = getattr(recipe_client, method)(url, json=body)
    assert response.status_code == 422, response.text
    assert any(item["loc"] == ["body", "requires_halal"] for item in response.json()["detail"])
    assert recipe_client.get("/api/household-profiles/current").json()["current_version"] == 1


@pytest.mark.parametrize("flag", [False, True])
def test_a_household_profile_write_with_the_flag_saves_it(recipe_client, flag):
    saved = recipe_client.post("/api/household-profiles", json={**PROFILE, "requires_halal": flag})
    assert saved.status_code == 201, saved.text
    assert saved.json()["current"]["requires_halal"] is flag
