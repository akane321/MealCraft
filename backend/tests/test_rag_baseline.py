from types import SimpleNamespace

import pytest

from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.pure_llm_baseline import BaselineResources
from app.evaluation.rag_baseline import SYSTEM_ID, generate, render_prompt, retrieval_context, run_episode
from app.evaluation.release_catalog import ReleaseCatalog
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

EPISODE = {
    "episode_id": "dev-rag-1",
    "scenario": {
        "user_request": "Plan Monday dinner for two people.",
        "household_profile": {"household_size": 2, "allergens": []},
        "planning_horizon": {"slots": ["mon-dinner"]},
        "recipe_candidate_slugs": ["recipe-tofu-rice"],
        "fairprice_product_ids": ["tofu-200", "rice-500"],
    },
    "gold": {"class": "feasible", "secret": "must not leak"},
}


def catalog() -> ReleaseCatalog:
    return ReleaseCatalog(
        recipes=[
            {
                "slug": "recipe-tofu-rice",
                "title": "Tofu rice",
                "course": "main",
                "meal_types": ["dinner"],
                "cuisine": "Asian",
                "servings": 2,
                "prep_time_minutes": 10,
                "cook_time_minutes": 15,
                "dietary_tags": ["vegetarian"],
                "ingredients": [
                    {"ingredient": "tofu", "quantity": 200.0},
                    {"ingredient": "rice", "quantity": 300.0},
                ],
                "nutrients": {"calories_kcal": 400.0},
            }
        ],
        products=[
            {
                "external_id": "tofu-200",
                "ingredient_id": "tofu",
                "name": "Tofu 200g",
                "package_size": 200.0,
                "package_unit": "g",
                "price_sgd": 2.0,
                "in_stock": True,
            },
            {
                "external_id": "rice-500",
                "ingredient_id": "rice",
                "name": "Rice 500g",
                "package_size": 500.0,
                "package_unit": "g",
                "price_sgd": 3.0,
                "in_stock": True,
            },
            {
                "external_id": "secret-product",
                "ingredient_id": "secret",
                "name": "Must not appear",
                "package_size": 1.0,
                "package_unit": "g",
                "price_sgd": 99.0,
                "in_stock": True,
            },
        ],
        ingredients=[],
    )


def response() -> dict:
    return {
        "episode_id": "dev-rag-1",
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
        return next(self.answers)


def resources() -> BaselineResources:
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


def test_prompt_contains_only_frozen_mealcraft_candidate_context():
    context = retrieval_context(EPISODE, catalog())
    prompt = render_prompt(EPISODE, catalog())

    assert context["recipes"][0]["recipe_id"] == "recipe-tofu-rice"
    assert "tofu-200" in prompt
    assert "secret-product" not in prompt
    assert "must not leak" not in prompt
    assert "no tools, web search" in prompt
    assert "perform the planning yourself" in prompt


def test_unknown_frozen_candidate_fails_instead_of_silently_changing_context():
    episode = {**EPISODE, "scenario": {**EPISODE["scenario"], "recipe_candidate_slugs": ["missing"]}}

    with pytest.raises(ValueError, match="unknown recipe candidates: missing"):
        retrieval_context(episode, catalog())


def test_malformed_output_retries_with_identical_rag_prompt_and_sums_usage():
    first = SimpleNamespace(
        usage_metadata={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
        response_metadata={},
    )
    second = SimpleNamespace(
        usage_metadata={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70, "cost_usd": 0.02},
        response_metadata={},
    )
    model = MockModel(
        [
            {"parsed": None, "raw": first, "parsing_error": "invalid JSON"},
            {"parsed": response(), "raw": second},
        ]
    )

    result = generate(EPISODE, model, catalog=catalog())

    assert result.response is not None
    assert result.attempts == 2
    assert result.usage.total_tokens == 70
    assert result.usage.cost_usd == 0.02
    assert model.prompts[0] == model.prompts[1]


def test_valid_rag_output_uses_shared_mapping_verification_and_recomputation():
    model = MockModel([{"parsed": response(), "raw": SimpleNamespace()}])

    result = run_episode(EPISODE, model=model, resources=resources(), catalog=catalog())

    assert result.system_id == SYSTEM_ID
    assert result.valid_output is True
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.allergens == ("soy",)
    assert result.recomputation.purchase_total_sgd == 5
