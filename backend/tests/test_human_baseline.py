import json

import pytest
from pydantic import ValidationError

from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.human_baseline import (
    SYSTEM_ID,
    HumanBaselineSubmission,
    load_submissions,
    run_submission,
)
from app.evaluation.pure_llm_baseline import BaselineResources
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

EPISODE = {"episode_id": "human-1", "scenario": {"user_request": "Plan dinner."}}


def submission_payload():
    return {
        "metadata": {
            "annotator_id": "participant-03",
            "run_id": "manual-first",
            "completion_time_seconds": 742.5,
            "tools_used": ["paper", "ChatGPT"],
        },
        "response": {
            "episode_id": "human-1",
            "system_id": SYSTEM_ID,
            "status": "plan",
            "plan": {
                "meals": [
                    {
                        "slot_id": "mon-dinner",
                        "role_id": "main",
                        "dishes": [
                            {
                                "name": "Tofu rice",
                                "cooking_time_minutes": 25,
                                "ingredients": [
                                    {"name": "tofu", "quantity_g": 200},
                                    {"name": "rice", "quantity_g": 300},
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    }


def resources():
    nutrients = PlanningNutrients(
        calories_kcal=100,
        protein_g=10,
        carbohydrate_g=20,
        fat_g=5,
        sodium_mg=50,
        sugar_g=2,
    )
    names = {"tofu": "Tofu", "rice": "Rice"}
    return BaselineResources(
        names=names,
        aliases={},
        matcher=IngredientMatcher(names, mode="spelling"),
        ingredient_facts={
            "tofu": IngredientEvaluationFacts(("soy",), nutrients),
            "rice": IngredientEvaluationFacts((), nutrients),
        },
        frozen_products=[
            PlanningProductOption(
                ingredient_id="tofu",
                product_id="tofu-200",
                package_quantity=200,
                package_unit="g",
                price_sgd=2,
                available=True,
            ),
            PlanningProductOption(
                ingredient_id="rice",
                product_id="rice-500",
                package_quantity=500,
                package_unit="g",
                price_sgd=3,
                available=True,
            ),
        ],
        not_purchased=frozenset(),
    )


def test_human_submission_reuses_common_response_and_records_comparison_metadata():
    submission = HumanBaselineSubmission.model_validate(submission_payload())

    assert submission.response.episode_id == "human-1"
    assert submission.metadata.completion_time_seconds == 742.5
    assert submission.metadata.tools_used == ["paper", "ChatGPT"]


@pytest.mark.parametrize(
    "change",
    [
        lambda row: row["metadata"].update(completion_time_seconds=0),
        lambda row: row["metadata"].update(annotator_id="  "),
        lambda row: row["metadata"].update(tools_used=["ChatGPT", "ChatGPT"]),
        lambda row: row["response"].update(system_id="pure-llm-single-turn"),
        lambda row: row["response"].update(plan=None),
        lambda row: row.update(unexpected=True),
    ],
)
def test_rejects_malformed_human_submission(change):
    payload = submission_payload()
    change(payload)

    with pytest.raises(ValidationError):
        HumanBaselineSubmission.model_validate(payload)


def test_load_submissions_rejects_malformed_collection(tmp_path):
    path = tmp_path / "submissions.json"
    path.write_text(json.dumps({"submissions": "not-a-list"}), encoding="utf-8")

    with pytest.raises(ValueError, match="submissions must be a list"):
        load_submissions(path)


def test_human_plan_uses_same_mapping_verification_and_recomputation_pipeline():
    submission = HumanBaselineSubmission.model_validate(submission_payload())

    result = run_submission(EPISODE, submission, resources=resources())

    assert result.valid_output is True
    assert result.generation.elapsed_seconds == 742.5
    assert result.generation.usage.total_tokens == 0
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.allergens == ("soy",)
    assert result.recomputation.purchase_total_sgd == 5


def test_rejects_submission_for_a_different_episode():
    submission = HumanBaselineSubmission.model_validate(submission_payload())

    with pytest.raises(ValueError, match="does not match"):
        run_submission({"episode_id": "human-2"}, submission, resources=resources())
