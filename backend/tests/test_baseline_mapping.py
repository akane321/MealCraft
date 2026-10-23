from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_mapping import map_ingredient, map_response_ingredients
from app.evaluation.baseline_output import BaselineResponse

NAMES = {
    "chicken": "Chicken",
    "chicken_breast": "Chicken breast",
    "brown_rice": "Brown rice",
    "coriander": "Coriander",
    "tomato": "Tomato",
    "spinach": "Spinach",
}
ALIASES = {"coriander": ["cilantro"]}
PARENTS = {"baby_spinach": "spinach"}


def map_one(name: str, grams: float = 100, **kwargs):
    matcher = IngredientMatcher(NAMES, aliases=ALIASES, mode="spelling")
    return map_ingredient(name, grams, names=NAMES, aliases=ALIASES, matcher=matcher, parents=PARENTS, **kwargs)


def test_display_name_and_id_map_without_review():
    named = map_one("Chicken breast")
    assert (named.status, named.ingredient_id, named.needs_review) == ("matched", "chicken_breast", False)
    assert named.method in {"id", "name"}
    assert map_one("brown_rice").method == "id"


def test_alias_alone_maps_but_waits_for_review():
    result = map_one("cilantro")
    assert result.ingredient_id == "coriander"
    assert result.method == "alias"
    assert result.needs_review and result.status == "needs_review"


def test_similarity_above_floor_maps_flagged_and_below_floor_is_unmatched():
    plural = map_one("tomatoes")
    assert (plural.ingredient_id, plural.method, plural.needs_review) == ("tomato", "similarity", True)
    stranger = map_one("brown sugar")
    assert stranger.status == "unmatched"
    assert stranger.ingredient_id is None
    assert stranger.suggestions  # kept for the review list


def test_hierarchy_parent_step():
    child = map_one("baby spinach")
    assert (child.ingredient_id, child.method, child.needs_review) == ("spinach", "hierarchy", True)
    longer = map_one("boneless chicken breast fillet")
    assert (longer.ingredient_id, longer.method) == ("chicken_breast", "hierarchy")


def test_mixed_script_line_goes_to_review_even_when_it_maps():
    result = map_one("chicken 鸡肉")
    assert result.ingredient_id == "chicken"
    assert result.needs_review
    assert any("Chinese" in reason for reason in result.review_reasons)


def test_lines_are_matched_in_one_batched_call():
    calls = []

    class Counting(IngredientMatcher):
        def suggest_all(self, terms, *, limit=4):
            calls.append(list(terms))
            return super().suggest_all(terms, limit=limit)

    coverage = map_response_ingredients(
        plan_response([[("chicken breast", 300), ("brown rice", 200)], [("unknown leaf", 50), ("tomato", 50)]]),
        names=NAMES,
        aliases=ALIASES,
        matcher=Counting(NAMES, aliases=ALIASES, mode="spelling"),
    )
    assert len(calls) == 1 and len(calls[0]) == 4
    assert [dish.coverage for dish in coverage.dishes] == [1.0, 0.5]
    assert coverage.total_grams == 600
    assert coverage.mapped_grams == 550


def plan_response(dishes: list[list[tuple[str, float]]]) -> BaselineResponse:
    return BaselineResponse.model_validate(
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
                                "name": f"Dish {index}",
                                "servings": 2,
                                "cooking_time_minutes": 30,
                                "steps": ["Cook."],
                                "ingredients": [{"name": name, "quantity_g": grams} for name, grams in lines],
                            }
                            for index, lines in enumerate(dishes)
                        ],
                    }
                ]
            },
        }
    )
