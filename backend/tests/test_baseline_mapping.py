from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_mapping import (
    map_ingredient,
    map_response_ingredients,
)
from app.evaluation.baseline_output import BaselineResponse

NAMES = {
    "chicken_breast": "Chicken breast",
    "brown_rice": "Brown rice",
    "coriander": "Coriander",
}

ALIASES = {
    "coriander": ["cilantro"],
}


def matcher() -> IngredientMatcher:
    return IngredientMatcher(
        NAMES,
        aliases=ALIASES,
        mode="spelling",
    )


def test_exact_display_name_is_matched():
    result = map_ingredient(
        "Chicken breast",
        300,
        names=NAMES,
        aliases=ALIASES,
        matcher=matcher(),
    )

    assert result.status == "matched"
    assert result.ingredient_id == "chicken_breast"


def test_alias_is_matched():
    result = map_ingredient(
        "cilantro",
        20,
        names=NAMES,
        aliases=ALIASES,
        matcher=matcher(),
    )

    assert result.status == "matched"
    assert result.ingredient_id == "coriander"


def test_non_exact_match_requires_review():
    result = map_ingredient(
        "chicken fillet",
        300,
        names=NAMES,
        aliases=ALIASES,
        matcher=matcher(),
    )

    assert result.status == "needs_review"
    assert result.ingredient_id is None
    assert result.suggestions


def test_coverage_is_weighted_by_grams():
    response = BaselineResponse.model_validate(
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
                                "name": "Chicken Rice",
                                "cooking_time_minutes": 30,
                                "ingredients": [
                                    {
                                        "name": "chicken breast",
                                        "quantity_g": 300,
                                    },
                                    {
                                        "name": "brown rice",
                                        "quantity_g": 200,
                                    },
                                    {
                                        "name": "unknown leaf",
                                        "quantity_g": 50,
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        }
    )

    result = map_response_ingredients(
        response,
        names=NAMES,
        aliases=ALIASES,
        matcher=matcher(),
    )

    assert result.total_grams == 550
    assert result.matched_grams == 500
    assert result.coverage == 500 / 550
