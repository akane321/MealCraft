import json
from types import SimpleNamespace

import pytest

from app.data.external_ingredient_mapping import ReviewedIngredientMapper
from app.schemas.agent import AgentConstraintState
from app.services.ingredient_substitutions import (
    IngredientSubstitutionFoodQuestionAnswerer,
    OpenAISubstituteGenerator,
    filter_safe_substitutes,
    reviewed_ingredient_mapper,
)


def ingredient(name, *, allergens=None, halal="halal"):
    return SimpleNamespace(
        normalized_name=name,
        display_name=name.replace("_", " "),
        allergens=allergens,
        halal_status=halal,
    )


def test_substitution_candidates_are_filtered_for_declared_allergens_and_exclusions():
    candidates = [
        ingredient("sunflower_oil", allergens=[]),
        ingredient("peanut_oil", allergens=["peanut"]),
        ingredient("olive_oil", allergens=[], halal="halal"),
    ]

    safe = filter_safe_substitutes(
        candidates,
        household_allergens=["peanut"],
        excluded_ingredients=["olive_oil"],
    )

    assert [(item.ingredient_id, item.display_name) for item in safe] == [("sunflower_oil", "sunflower oil")]


def test_chat_substitution_answer_uses_current_constraints_and_catalog_candidates():
    catalog = [
        ingredient("peanut_oil", allergens=["peanut"]),
        ingredient("olive_oil", allergens=[]),
        ingredient("sunflower_oil", allergens=[]),
    ]

    class FakeGenerator:
        def suggest(self, source):
            assert source == "butter in this sauce"
            return ["peanut oil", "olive oil", "sunflower oil"]

    mapper = ReviewedIngredientMapper(
        {
            "butter": {"butter"},
            "peanut oil": {"peanut_oil"},
            "olive oil": {"olive_oil"},
            "sunflower oil": {"sunflower_oil"},
        }
    )
    answerer = IngredientSubstitutionFoodQuestionAnswerer(
        SimpleNamespace(scalars=lambda _statement: iter(catalog)),
        generator=FakeGenerator(),
        mapper=mapper,
    )

    answer = answerer.answer(
        "What can I use instead of butter in this sauce?",
        "en",
        AgentConstraintState(allergens=["peanut"], excluded_ingredients=["olive_oil"]),
    )

    assert answer == (
        "Possible options: sunflower oil. These were filtered using catalog allergen, exclusion, and halal data."
    )


def test_chinese_chat_substitution_uses_reviewed_chinese_catalog_aliases():
    class FakeGenerator:
        def suggest(self, source):
            assert source == "黄油"
            return ["葵花籽油"]

    answerer = IngredientSubstitutionFoodQuestionAnswerer(
        SimpleNamespace(scalars=lambda _statement: iter([ingredient("sunflower_oil", allergens=[])])),
        generator=FakeGenerator(),
        mapper=reviewed_ingredient_mapper(),
    )

    answer = answerer.answer("没有黄油可以用什么代替？", "zh", AgentConstraintState())

    assert answer == "可考虑：sunflower oil。这些选项已按食材目录中的过敏原、忌口和清真信息筛选。"


def test_unknown_allergen_data_and_unverified_halal_fail_closed_when_requested():
    candidates = [
        ingredient("unknown_allergen_oil", allergens=None, halal="halal"),
        ingredient("uncertain_oil", allergens=[], halal="uncertain"),
        ingredient("verified_oil", allergens=[], halal="halal"),
    ]

    safe = filter_safe_substitutes(
        candidates,
        household_allergens=["peanut"],
        requires_halal=True,
    )

    assert [item.ingredient_id for item in safe] == ["verified_oil"]


def test_unknown_allergen_data_does_not_block_when_household_has_no_allergy_limit():
    safe = filter_safe_substitutes([ingredient("unknown_allergen_oil", allergens=None)])

    assert [item.ingredient_id for item in safe] == ["unknown_allergen_oil"]


def test_model_suggestion_generator_returns_names_without_safety_claims():
    class FakeResponses:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_text=json.dumps({"candidates": ["olive oil", "sunflower oil"]}))

    responses = FakeResponses()
    generator = OpenAISubstituteGenerator(
        api_key="unused", model="test-model", client=SimpleNamespace(responses=responses)
    )

    assert generator.suggest("butter", use_context="for pan-frying") == ["olive oil", "sunflower oil"]
    assert "the application will check catalog facts" in responses.kwargs["input"]


def test_model_suggestion_generator_rejects_invalid_output():
    generator = OpenAISubstituteGenerator(
        api_key="unused",
        model="test-model",
        client=SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(output_text="bad"))),
    )

    with pytest.raises(ValueError, match="invalid candidate list"):
        generator.suggest("butter")


@pytest.mark.parametrize("error", [ValueError("invalid"), TimeoutError("timeout"), ConnectionError("offline")])
def test_substitution_failure_is_bounded_not_a_web_fallback(error):
    class Generator:
        def suggest(self, source):
            raise error

    answerer = IngredientSubstitutionFoodQuestionAnswerer(
        None, generator=Generator(), mapper=ReviewedIngredientMapper({"butter": {"butter"}})
    )
    assert "won't suggest unverified" in answerer.answer(
        "What can I use instead of butter?", "en", AgentConstraintState()
    )
    assert "won't suggest unverified" in answerer.answer(
        "What can I use instead of unknown?", "en", AgentConstraintState()
    )
    assert answerer.answer("What is miso?", "en", AgentConstraintState()) is None


def test_member_only_limits_are_not_lost_in_substitution():
    mapper = ReviewedIngredientMapper({"butter": {"butter"}, "peanut oil": {"peanut_oil"}, "olive oil": {"olive_oil"}})
    catalog = [ingredient("peanut_oil", allergens=["peanut"]), ingredient("olive_oil", allergens=[])]
    answerer = IngredientSubstitutionFoodQuestionAnswerer(
        SimpleNamespace(scalars=lambda _: iter(catalog)),
        generator=SimpleNamespace(suggest=lambda _: ["peanut oil", "olive oil"]),
        mapper=mapper,
    )
    constraints = AgentConstraintState.model_validate(
        {
            "household": {
                "members": [
                    {"name": "Ann", "servings": 1, "allergens": ["peanut"], "excluded_ingredients": ["olive_oil"]}
                ]
            }
        }
    )
    answer = answerer.answer("What can I use instead of butter?", "en", constraints)
    assert "couldn’t find" in answer
    constraints.household.members[0].dietary_preferences = ["vegan"]
    assert "dietary preferences" in answerer.answer("What can I use instead of butter?", "en", constraints)


def test_substitution_client_uses_configured_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.ingredient_substitutions.OpenAI", lambda **kw: captured.update(kw) or object())
    OpenAISubstituteGenerator(api_key="unused", model="test", timeout_seconds=47)
    assert captured["timeout"] == 47
