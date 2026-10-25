from types import SimpleNamespace

import pytest

from app.api.routes import ingredient_substitutions as routes
from tests.test_recipes import recipe_client as recipe_client


@pytest.mark.parametrize("endpoint", ["review", "suggest"])
@pytest.mark.parametrize("flag", [{}, {"requires_halal": None}])
def test_halal_choice_is_explicit_at_both_http_boundaries(recipe_client, endpoint, flag):
    payload = {"source_ingredient": "chicken", **flag}
    if endpoint == "review":
        payload["candidates"] = ["tofu"]
    assert recipe_client.post(f"/api/ingredient-substitutions/{endpoint}", json=payload).status_code == 422


def test_household_review_applies_member_allergy_and_diet(recipe_client, monkeypatch):
    version = SimpleNamespace(
        allergens=[], excluded_ingredients=[], dietary_preferences=[], members=[{"allergens": ["soy"]}]
    )
    monkeypatch.setattr(routes.HouseholdProfileRepository, "get_current", lambda _: object())
    monkeypatch.setattr(routes.HouseholdProfileRepository, "current_version", lambda _: version)
    payload = {"source_ingredient": "chicken breast", "candidates": ["firm tofu", "lemon"], "requires_halal": False}
    response = recipe_client.post("/api/ingredient-substitutions/review", json=payload)
    assert response.status_code == 200
    assert [item["ingredient_id"] for item in response.json()["safe_candidates"]] == ["lemon"]
    version.dietary_preferences = ["vegan"]
    assert recipe_client.post("/api/ingredient-substitutions/review", json=payload).json()["safe_candidates"] == []


def test_fixture_suggestion_never_constructs_a_model_client(recipe_client, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("No model call in fixture mode")

    monkeypatch.setattr(routes, "OpenAISubstituteGenerator", forbidden)
    response = recipe_client.post(
        "/api/ingredient-substitutions/suggest", json={"source_ingredient": "butter", "requires_halal": False}
    )
    assert response.status_code == 503
