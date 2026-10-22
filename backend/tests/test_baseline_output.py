import pytest
from pydantic import ValidationError

from app.evaluation.baseline_output import BaselineResponse


def test_valid_plan_response():
    response = BaselineResponse.model_validate(
        {
            "episode_id": "ep-1",
            "system_id": "pure-llm",
            "status": "plan",
            "plan": {
                "meals": [
                    {
                        "slot_id": "mon-dinner",
                        "role_id": "main",
                        "dishes": [
                            {
                                "name": "Lemon Chicken",
                                "cooking_time_minutes": 30,
                                "ingredients": [
                                    {"name": "chicken breast", "quantity_g": 300},
                                    {"name": "lemon", "quantity_g": 50},
                                ],
                            }
                        ],
                    }
                ]
            },
        }
    )

    assert response.episode_id == "ep-1"
    assert response.status == "plan"
    assert response.plan is not None
    assert response.plan.meals[0].dishes[0].name == "Lemon Chicken"


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        BaselineResponse.model_validate(
            {
                "episode_id": "ep-1",
                "system_id": "pure-llm",
                "status": "plan",
                "unexpected": "not allowed",
            }
        )


def test_rejects_invalid_status():
    with pytest.raises(ValidationError):
        BaselineResponse.model_validate(
            {
                "episode_id": "ep-1",
                "system_id": "pure-llm",
                "status": "maybe",
            }
        )


def test_rejects_nonpositive_ingredient_quantity():
    with pytest.raises(ValidationError):
        BaselineResponse.model_validate(
            {
                "episode_id": "ep-1",
                "system_id": "pure-llm",
                "status": "plan",
                "plan": {
                    "meals": [
                        {
                            "slot_id": "mon-dinner",
                            "dishes": [
                                {
                                    "name": "Rice Bowl",
                                    "cooking_time_minutes": 20,
                                    "ingredients": [{"name": "rice", "quantity_g": 0}],
                                }
                            ],
                        }
                    ]
                },
            }
        )
