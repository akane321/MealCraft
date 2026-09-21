from sqlalchemy import select

from app.models.meal_plan import MealPlan
from tests.test_planning_product_path import REQUEST, database, latest_trace
from tests.test_recipes import recipe_client as recipe_client


def test_time_proposal_requires_a_new_request_before_a_plan_is_saved(recipe_client):
    request = {**REQUEST, "allergens": ["soy"], "max_cooking_time_minutes": 20}
    response = recipe_client.post("/api/plans/generate", json=request)
    assert response.status_code == 422
    assert "30-minute" in response.json()["detail"]
    with database() as session:
        assert session.scalars(select(MealPlan)).all() == []
    _, trace = latest_trace()
    assert trace["status"] == "infeasible"
    assert trace["explanation"]["conflict"] == ["time_limit"]
    accepted = recipe_client.post("/api/plans/generate", json={**request, "max_cooking_time_minutes": 30})
    assert accepted.status_code == 201
    _, trace = latest_trace()
    assert trace["validation"]["status"] == "passed"


def test_budget_proposal_can_be_explicitly_resubmitted(recipe_client):
    request = {**REQUEST, "allergens": ["soy"], "weekly_budget_sgd": 0.01}
    response = recipe_client.post("/api/plans/generate", json=request)
    assert response.status_code == 422
    _, trace = latest_trace()
    proposal = trace["explanation"]["suggestions"][0]
    amount = next(c["value"] for c in proposal["changes"] if c["field"] == "purchase_budget")
    assert f"S${amount:.2f}" in response.json()["detail"]
    accepted = recipe_client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": amount})
    assert accepted.status_code == 201
    assert accepted.json()["grocery_estimate"]["purchase_total_sgd"] <= amount


def test_unknown_allergen_has_no_suggestion(recipe_client):
    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "allergens": ["unknown-allergen"]})
    assert response.status_code == 422
    _, trace = latest_trace()
    assert "explanation" not in trace


def test_diagnosis_restores_time_filtered_candidates_and_reestablishes_evidence(recipe_client):
    response = recipe_client.post(
        "/api/plans/generate", json={**REQUEST, "max_cooking_time_minutes": 30, "weekly_budget_sgd": 0.01}
    )
    assert response.status_code == 422
    _, trace = latest_trace()
    assert "prior_candidate_attempt" in trace
    assert any(
        d["recipe_id"] == "tofu-soba" and "time_limit" in d["rejection_codes"] for d in trace["compiled"]["decisions"]
    )
    assert trace["explanation"]["suggestions"]
