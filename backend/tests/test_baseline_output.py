import pytest
from pydantic import ValidationError

from app.evaluation import common_output
from app.evaluation.baseline_output import BaselineAnswer, BaselineResponse

DISH = {
    "name": "Lemon Chicken",
    "servings": 2,
    "cooking_time_minutes": 30,
    "steps": ["Season the chicken.", "Roast it."],
    "ingredients": [{"name": "chicken breast", "quantity_g": 300}, {"name": "lemon", "quantity_g": 50}],
}


def answer(**changes) -> dict:
    return {"status": "plan", "plan": {"meals": [{"slot_id": "mon-dinner", "dishes": [DISH]}]}} | changes


def test_valid_plan_and_harness_ids():
    response = BaselineResponse.model_validate(answer(episode_id="ep-1", system_id="pure-llm"))
    assert response.plan.meals[0].dishes[0].steps[1] == "Roast it."
    assert "episode_id" not in BaselineAnswer.model_fields  # the model never copies ids


def test_reuses_the_common_schema_types():
    assert issubclass(BaselineAnswer, common_output.StrictModel)
    assert BaselineAnswer.model_fields["status"].annotation is common_output.ResponseStatus


@pytest.mark.parametrize(
    "payload",
    [
        answer(unexpected=1),
        answer(status="maybe"),
        answer(plan=None),  # a plan status with no plan
        answer(status="clarification", clarification=[{"field": "budget_sgd", "question": "Budget?"}]),
        {"status": "infeasible"},
        answer(plan={"meals": [{"slot_id": "s", "dishes": [DISH | {"steps": []}]}]}),
        answer(
            plan={"meals": [{"slot_id": "s", "dishes": [DISH | {"ingredients": [{"name": "x", "quantity_g": 0}]}]}]}
        ),
    ],
)
def test_rejects_malformed_answers(payload):
    with pytest.raises(ValidationError):
        BaselineAnswer.model_validate(payload)


def test_rejects_infinite_quantities_from_json():
    bad = (
        '{"status":"plan","plan":{"meals":[{"slot_id":"s","dishes":[{"name":"d","servings":1,'
        '"cooking_time_minutes":5,"steps":["x"],"ingredients":[{"name":"x","quantity_g":Infinity}]}]}]}}'
    )
    with pytest.raises(ValidationError):
        BaselineAnswer.model_validate_json(bad)
    with pytest.raises(ValidationError):
        BaselineAnswer.model_validate(
            answer(plan={"meals": [{"slot_id": "s", "dishes": [DISH | {"servings": float("inf")}]}]})
        )


def test_clarification_and_infeasible_payloads():
    asked = BaselineAnswer.model_validate(
        {"status": "clarification", "clarification": [{"field": "budget_sgd", "question": "What budget?"}]}
    )
    assert asked.plan is None
    refused = BaselineAnswer.model_validate(
        {"status": "infeasible", "infeasible": {"conflict": "no dish meets the allergens", "allowed_relaxations": []}}
    )
    assert refused.infeasible.conflict
