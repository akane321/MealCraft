from sqlalchemy import select

from app.models.meal_plan import MealPlan
from tests.test_planning_product_path import REQUEST, database, latest_trace
from tests.test_recipes import recipe_client as recipe_client


def test_product_scope_is_echoed_and_persisted(recipe_client):
    request = {**REQUEST, "nutrition_constraints": [{"metric": "calories_kcal", "upper": 1000}]}
    response = recipe_client.post("/api/plans/generate", json=request)
    assert response.status_code == 201, response.text
    result = response.json()
    assert any("average across planned meals" in note for note in result["warnings"])
    assert recipe_client.get(f"/api/plans/{result['id']}").json()["warnings"] == result["warnings"]
    _, trace = latest_trace()
    assert trace["nutrition_scope"][0]["average_basis"] == "selected_slots"
    assert all("upper" not in b and "lower" not in b for b in trace["nutrition_scope"])


def test_impossible_per_meal_target_cannot_save_or_suggest_relaxing_it(recipe_client):
    request = {**REQUEST, "nutrition_constraints": [{"metric": "calories_kcal", "upper": 1, "scope": "per_serving"}]}
    response = recipe_client.post("/api/plans/generate", json=request)
    assert response.status_code == 422
    with database() as session:
        assert session.scalars(select(MealPlan)).all() == []
    _, trace = latest_trace()
    assert trace["nutrition_scope"][0]["scope"] == "per_slot"
    assert trace.get("explanation", {}).get("suggestions", []) == []


def test_product_explicit_scope_and_invalid_scope(recipe_client):
    request = {**REQUEST, "nutrition_constraints": [{"metric": "calories_kcal", "upper": 1000, "scope": "per_serving"}]}
    response = recipe_client.post("/api/plans/generate", json=request)
    assert response.status_code == 201
    assert any("each planned meal" in note for note in response.json()["warnings"])
    request["nutrition_constraints"][0]["scope"] = "per_day"
    assert recipe_client.post("/api/plans/generate", json=request).status_code == 422
