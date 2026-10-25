import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.db.session import get_db_session
from app.main import app
from app.models.agent import AgentSession
from app.orchestration.contracts import ScopeClass
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.orchestration.scope_classifier import OpenAIScopeClassifier, ScopePrediction
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.schemas.agent import AgentConstraintState
from tests.test_recipes import recipe_client as recipe_client


@pytest.mark.parametrize("message", ["Plan halal dinners for two.", "两个人这周吃清真晚餐。"])
def test_halal_request_is_explicitly_declined_before_parser_or_planner(recipe_client, message):
    response = recipe_client.post("/api/agent/sessions", json={"message": message})
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["constraints"]["requires_halal"] is True
    assert not value["can_confirm"] and value["plan_id"] is None
    assert value["last_scope_decision"]["reason_code"] == "HALAL_NOT_SUPPORTED"
    assert "not supported" in value["messages"][-1]["content"] or "暂不支持" in value["messages"][-1]["content"]
    assert recipe_client.post(f"/api/agent/sessions/{value['id']}/confirm").status_code == 409


def test_old_ready_halal_state_cannot_bypass_confirmation_gate(recipe_client):
    value = recipe_client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    database_generator = app.dependency_overrides[get_db_session]()
    database = next(database_generator)
    try:
        saved = database.get(AgentSession, value["id"])
        saved.constraints = {**saved.constraints, "requires_halal": True}
        saved.status = "ready"
        database.commit()
    finally:
        database_generator.close()
    assert not recipe_client.get(f"/api/agent/sessions/{value['id']}").json()["can_confirm"]
    assert recipe_client.post(f"/api/agent/sessions/{value['id']}/confirm").status_code == 409
    assert recipe_client.get("/api/plans").json()["items"] == []


def test_halal_followup_on_an_existing_week_cannot_create_or_confirm_a_replan(recipe_client):
    value = recipe_client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    confirmed = recipe_client.post(f"/api/agent/sessions/{value['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    plan = confirmed.json()["plan"]
    response = recipe_client.post(
        f"/api/agent/sessions/{value['id']}/messages",
        json={"message": "Replan this week with halal dinners"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["constraints"]["requires_halal"]
    assert recipe_client.post(f"/api/agent/sessions/{value['id']}/replan/confirm").status_code == 409
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"]


@pytest.mark.parametrize(
    "message, restriction",
    [
        ("安排一周晚餐；不吃花生；推荐电影", "不吃花生"),
        ("Plan dinners for two. I am allergic to peanuts. Recommend a movie.", "I am allergic to peanuts"),
        ("Plan dinners for 2. No peanuts. Recommend a movie.", "No peanuts"),
    ],
)
def test_mixed_scope_keeps_separate_food_restrictions(message, restriction):
    policy = ReferenceScopePolicy()
    result = policy.classify(message)
    assert result.scope_class is ScopeClass.PARTIALLY_SUPPORTED
    assert restriction in result.supported_segments
    assert not any("movie" in part or "电影" in part for part in result.supported_segments)


def test_social_model_error_cannot_discard_a_new_allergy():
    class WrongModel:
        def invoke(self, prompt):
            return ScopePrediction(scope_class=ScopeClass.SOCIAL, intent="social")

    classifier = OpenAIScopeClassifier(api_key="synthetic-not-real", model="synthetic", structured_model=WrongModel())
    workflow = BoundedAgentOrchestrator(RuleBasedConstraintParser(), scope_classifier=classifier)
    result = workflow.process(
        "Dinners for two; I am allergic to peanuts; recommend a movie",
        current=AgentConstraintState(household_size=2),
        acknowledged_unknowns=[],
        history=[],
        current_status="ready",
        current_missing_fields=[],
        current_questions=[],
        context_version=1,
    )
    assert "peanut" in result.constraints.allergens
    assert result.scope_decision.scope_class is ScopeClass.PARTIALLY_SUPPORTED


def test_non_food_negation_is_not_promoted_to_a_meal_request():
    assert (
        ReferenceScopePolicy().classify("No movie recommendations; suggest a travel itinerary.").scope_class
        is ScopeClass.OUT_OF_SCOPE
    )
