import json
from types import SimpleNamespace

import pytest

from app.core.paths import repository_root
from app.data.external_ingredient_mapping import ReviewedIngredientMapper
from app.data.release_v2 import map_allergens
from app.planning.vegetable_led import food_groups
from app.schemas.agent import AgentConstraintState
from app.services.ingredient_substitutions import (
    IngredientSubstitutionFoodQuestionAnswerer,
    OpenAISubstituteGenerator,
    filter_safe_substitutes,
    reviewed_ingredient_mapper,
    suits_diet,
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


# Diet checks per candidate, on the release's own facts --------------------------------------------------------

RELEASE_ROWS = {
    json.loads(line)["ingredient_id"].removeprefix("ING_").lower(): json.loads(line)
    for line in (repository_root() / "data-engineering/data/release/v2.2/ingredients.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
}


def release_ingredient(name):
    """A catalog row as the release import writes it (display name, runtime allergens; no halal record)."""
    row = RELEASE_ROWS[name]
    return SimpleNamespace(
        normalized_name=name,
        display_name=row["canonical_name"],
        allergens=map_allergens(row["allergens"]),
        halal_status=None,
    )


# Not in the release nor the ingredient hierarchy: its origin and food group are unknown.
MYSTERY = SimpleNamespace(
    normalized_name="mystery_sauce", display_name="mystery sauce", allergens=[], halal_status=None
)


def diet_answerer(catalog, suggestions, aliases):
    mapper = reviewed_ingredient_mapper()
    for alias, name in aliases.items():
        mapper.aliases[alias] = {name}
    return IngredientSubstitutionFoodQuestionAnswerer(
        SimpleNamespace(scalars=lambda _statement: iter(catalog)),
        generator=SimpleNamespace(suggest=lambda _source: list(suggestions)),
        mapper=mapper,
    )


def household(*members, allergens=()):
    return AgentConstraintState.model_validate(
        {
            "allergens": list(allergens),
            "household": {"members": [{"servings": 1, **member} for member in members]},
        }
    )


# The issue #367 walkthrough household: three people, peanuts kept off the whole table, one vegetarian, one child.
WALKTHROUGH = household(
    {"name": "Ann", "allergens": ["peanut"]},
    {"name": "Mei", "dietary_preferences": ["vegetarian"]},
    {"name": "Leo", "servings": 0.6},
    allergens=["peanut"],
)


def test_the_walkthrough_fish_sauce_question_gets_options_checked_for_every_member():
    """Before the fix, any member's diet refused every substitution question."""
    answerer = diet_answerer(
        [release_ingredient(name) for name in ("soy_sauce", "worcestershire", "anchovy")],
        ["soy sauce", "worcestershire sauce", "anchovy paste", "light soy sauce"],
        {},
    )

    answer = answerer.answer("What can I use instead of fish sauce?", "en", WALKTHROUGH)

    assert answer == (
        "Possible options: soy sauce. These were checked against every member’s allergens, diet, and exclusions "
        "using catalog allergen, dietary-origin, and halal data."
    )


def test_a_vegetarian_member_and_a_peanut_table_get_only_verified_plant_options():
    assert RELEASE_ROWS["lard"]["dietary_origin"] == RELEASE_ROWS["worcestershire"]["dietary_origin"] == "flesh"
    catalog = [
        release_ingredient("soy_sauce"),  # plant
        release_ingredient("worcestershire"),  # flesh (anchovies)
        release_ingredient("lard"),  # flesh, no allergen to catch it
        release_ingredient("peanut_oil"),  # plant, peanut
        MYSTERY,  # unknown origin
    ]
    answerer = diet_answerer(
        catalog,
        ["soy sauce", "worcestershire sauce", "lard", "peanut oil", "mystery sauce"],
        {"mystery sauce": "mystery_sauce"},
    )

    answer = answerer.answer("What can I use instead of fish sauce?", "en", WALKTHROUGH)

    assert answer.startswith("Possible options: soy sauce. ")
    assert answer.endswith(
        " Other suggestions were left out because I couldn’t verify they suit Mei’s vegetarian diet."
    )
    for dropped in ("worcestershire", "lard", "peanut", "mystery"):
        assert dropped not in answer


def test_the_walkthrough_question_in_chinese():
    catalog = [release_ingredient("soy_sauce"), release_ingredient("worcestershire"), MYSTERY]
    answerer = diet_answerer(catalog, ["酱油", "worcestershire sauce", "神秘酱"], {"神秘酱": "mystery_sauce"})

    answer = answerer.answer("没有鱼露可以用什么代替？", "zh", WALKTHROUGH)

    assert answer == (
        "可考虑：soy sauce。这些选项已按食材目录中的过敏原、饮食来源和清真信息，"
        "核对了每位家庭成员的过敏原、饮食和忌口。其他建议未列出，因为我无法核实它们是否符合Mei的素食饮食。"
    )


def test_a_vegan_member_gets_no_dairy_egg_or_honey():
    assert {RELEASE_ROWS[name]["dietary_origin"] for name in ("honey", "butter", "egg")} == {"secretion"}
    catalog = [release_ingredient(name) for name in ("honey", "butter", "egg", "olive_oil")]
    answerer = diet_answerer(catalog, ["honey", "butter", "egg", "olive oil"], {})
    constraints = household({"name": "Ann"}, {"name": "Ben", "dietary_preferences": ["vegan"]})

    answer = answerer.answer("What can I use instead of ghee?", "en", constraints)

    assert answer.startswith("Possible options: olive oil. These were checked against every member’s")
    assert "left out" not in answer


def test_a_dairy_free_member_gets_no_dairy_group_or_dairy_allergen():
    assert RELEASE_ROWS["yogurt"]["food_group"] == "dairy"
    assert RELEASE_ROWS["margarine"]["food_group"] != "dairy" and "milk" in RELEASE_ROWS["margarine"]["allergens"]
    catalog = [release_ingredient(name) for name in ("yogurt", "margarine", "coconut_milk")]
    unknown_allergens = SimpleNamespace(normalized_name="olive_oil", display_name="olive oil", allergens=None)
    answerer = diet_answerer([*catalog, unknown_allergens], ["yogurt", "margarine", "coconut milk", "olive oil"], {})
    constraints = household({"name": "Ann", "dietary_preferences": ["dairy-free"]})

    answer = answerer.answer("What can I use instead of butter?", "en", constraints)

    assert answer.startswith("Possible options: coconut milk. ")
    assert answer.endswith(
        " Other suggestions were left out because I couldn’t verify they suit Ann’s dairy free diet."
    )


def test_a_gluten_free_member_gets_no_gluten_or_possible_gluten():
    # Tamari's release allergens are soy and gluten_candidate, which the import reads as gluten.
    catalog = [release_ingredient(name) for name in ("soy_sauce", "tamari", "rice_vinegar")]
    answerer = diet_answerer(catalog, ["soy sauce", "tamari", "rice vinegar"], {"tamari": "tamari"})
    constraints = household({"name": "Ann"}, {"name": "Ben", "dietary_preferences": ["gluten-free"]})

    answer = answerer.answer("What can I use instead of fish sauce?", "en", constraints)

    assert answer.startswith("Possible options: rice vinegar. ")
    assert "soy sauce" not in answer and "tamari" not in answer


def test_every_diet_at_the_table_applies_and_nothing_verified_is_said_as_such_in_chinese():
    answerer = diet_answerer([release_ingredient("honey"), MYSTERY], ["honey", "神秘酱"], {"神秘酱": "mystery_sauce"})
    constraints = household({"name": "Ann", "dietary_preferences": ["vegan"]}, {"name": "Mei"})
    constraints.dietary_preferences = ["vegetarian"]

    answer = answerer.answer("没有糖可以用什么代替？", "zh", constraints)

    assert answer == (
        "目录中没有找到通过家庭限制核验的替代食材。部分建议未列出，因为我无法核实它们是否符合家庭的素食饮食和Ann的纯素饮食。"
    )


def test_unconfirmed_release_allergens_are_unknown(monkeypatch):
    groups = dict(food_groups())
    groups["soy_sauce"] = (*groups["soy_sauce"][:3], "pending_human")
    monkeypatch.setattr("app.services.ingredient_substitutions.food_groups", lambda: groups)
    soy_sauce = release_ingredient("soy_sauce")

    assert filter_safe_substitutes([soy_sauce], household_allergens=["peanut"]) == []
    assert suits_diet(soy_sauce, "gluten-free") is None
    assert suits_diet(soy_sauce, "vegetarian") is True
    assert suits_diet(soy_sauce, "keto") is None


def test_substitution_client_uses_configured_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.ingredient_substitutions.OpenAI", lambda **kw: captured.update(kw) or object())
    OpenAISubstituteGenerator(api_key="unused", model="test", timeout_seconds=47)
    assert captured["timeout"] == 47
