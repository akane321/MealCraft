from types import SimpleNamespace

from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.pure_llm_baseline import (
    SYSTEM_ID,
    BaselineResources,
    generate,
    household_task_input,
    render_prompt,
    run_episode,
)
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

EPISODE = {
    "episode_id": "dev-1",
    "category": "ordinary",
    "language": "en",
    "scenario": {
        "user_request": "Plan Monday dinner for two people.",
        "conversation_history": [],
        "household_profile": {"household_size": 2, "allergens": []},
        "pantry": [],
        "planning_horizon": {"slots": ["mon-dinner"]},
        "recipe_candidate_slugs": ["secret-recipe"],
        "fairprice_product_ids": ["secret-product"],
    },
    "gold": {"class": "feasible"},
}


def response():
    return {
        "episode_id": "dev-1",
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
    }


class MockModel:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


def resources():
    names = {"tofu": "Tofu", "rice": "Rice"}
    nutrients = PlanningNutrients(
        calories_kcal=100,
        protein_g=10,
        carbohydrate_g=20,
        fat_g=5,
        sodium_mg=50,
        sugar_g=2,
    )
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


def test_prompt_exposes_only_household_and_task_input():
    selected = household_task_input(EPISODE)
    prompt = render_prompt(EPISODE)

    assert selected["user_request"] == "Plan Monday dinner for two people."
    assert "secret-recipe" not in prompt
    assert "secret-product" not in prompt
    assert '"gold"' not in prompt
    assert "recipe database" in prompt


def test_valid_structured_response_records_usage_without_retry():
    raw = SimpleNamespace(
        usage_metadata={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
        response_metadata={},
    )
    model = MockModel([{"parsed": response(), "raw": raw}])

    result = generate(EPISODE, model)

    assert result.response is not None
    assert result.attempts == 1
    assert result.usage.total_tokens == 140
    assert result.usage.cost_usd is None
    assert result.parse_errors == ()


def test_malformed_output_gets_one_identical_retry_then_succeeds():
    model = MockModel(
        [
            {"parsed": None, "raw": SimpleNamespace(), "parsing_error": "invalid JSON"},
            {"parsed": response(), "raw": SimpleNamespace()},
        ]
    )

    result = generate(EPISODE, model)

    assert result.response is not None
    assert result.attempts == 2
    assert len(result.parse_errors) == 1
    assert model.prompts[0] == model.prompts[1]


def test_second_malformed_output_is_explicit_invalid_failure():
    model = MockModel(
        [
            {"parsed": None, "raw": SimpleNamespace(), "parsing_error": "bad one"},
            {"parsed": None, "raw": SimpleNamespace(), "parsing_error": "bad two"},
        ]
    )

    result = run_episode(EPISODE, model=model, resources=resources())

    assert result.valid_output is False
    assert result.generation.attempts == 2
    assert len(result.generation.parse_errors) == 2
    assert result.coverage is None
    assert result.recomputation is None


def test_valid_output_flows_through_mapping_verification_and_recomputation():
    model = MockModel([{"parsed": response(), "raw": SimpleNamespace()}])

    result = run_episode(EPISODE, model=model, resources=resources())

    assert result.valid_output is True
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.allergens == ("soy",)
    assert result.recomputation.purchase_total_sgd == 5
