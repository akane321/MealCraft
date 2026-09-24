"""An "A or B" recipe line is cooked with the first option the household can eat and can buy."""

import json

from app.core.paths import repository_root
from app.data.alternatives import options
from app.data.ingredient_hierarchy import expand_exclusions
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition
from app.planning import alternatives
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.schemas.recommendation import RecipeRecommendationRequest


def option(name, display, allergens=()):
    return {"normalized_name": name, "display_name": display, "allergens": list(allergens)}


BUTTER_OR_MARGARINE = [option("butter", "butter", ["dairy"]), option("margarine", "margarine", ["dairy"])]
BUTTER_OR_OIL = [option("butter", "butter", ["dairy"]), option("vegetable_oil", "vegetable oil")]
BEEF_OR_TURKEY = [option("ground_beef", "ground beef"), option("turkey", "turkey")]


def household(**changes):
    return RecipeRecommendationRequest(household_size=2, **changes)


def test_the_first_option_is_kept_when_the_household_can_eat_it():
    assert alternatives.choose(BUTTER_OR_MARGARINE, household()).normalized_name == "butter"


def test_an_excluded_option_gives_way_to_the_next():
    assert alternatives.choose(BUTTER_OR_MARGARINE, household(excluded_ingredients=["butter"])).normalized_name == (
        "margarine"
    )


def test_an_allergen_rules_out_every_option_that_carries_it():
    assert alternatives.choose(BUTTER_OR_OIL, household(allergens=["dairy"])).normalized_name == "vegetable_oil"
    assert alternatives.choose(BUTTER_OR_MARGARINE, household(allergens=["dairy"])) is None


def test_an_option_the_planner_cannot_buy_is_never_chosen():
    # Turkey has no FairPrice mapping, so a no-beef household cannot be given it.
    assert alternatives.choose(BEEF_OR_TURKEY, household(excluded_ingredients=["ground_beef"])) is None


def recipe_with(combined_allergens, options_):
    combined = Ingredient(
        normalized_name="butter_or_veg_oil",
        display_name="butter or vegetable oil",
        allergens=list(combined_allergens),
        alternatives=options_,
    )
    flour = Ingredient(normalized_name="flour", display_name="flour", allergens=["gluten"])
    return Recipe(
        id=1,
        slug="pancakes",
        title="Pancakes",
        servings=2,
        prep_time_minutes=5,
        cook_time_minutes=15,
        dietary_tags=[],
        nutrition=RecipeNutrition(sodium_mg=100),
        recipe_ingredients=[
            RecipeIngredient(ingredient=combined, quantity=30, unit="g", sort_order=1),
            RecipeIngredient(ingredient=flour, quantity=200, unit="g", sort_order=2),
        ],
    )


def test_a_dairy_free_household_keeps_the_recipe_and_cooks_it_with_oil():
    recipe = recipe_with(["dairy"], BUTTER_OR_OIL)
    request = household(allergens=["dairy"])

    cooked = alternatives.lines(recipe, request)
    reasons = RecipeRecommendationEngine()._exclusion_reasons(
        recipe, request, expand_exclusions(request.excluded_ingredients)
    )

    assert cooked[0].ingredient.normalized_name == "vegetable_oil"
    assert cooked[0].chosen_from == "butter or vegetable oil"
    assert cooked[1] is recipe.recipe_ingredients[1]  # an ordinary line is passed through untouched
    assert reasons == []


def test_with_no_option_left_the_recipe_is_excluded_as_before():
    recipe = recipe_with(["dairy"], BUTTER_OR_MARGARINE)
    reasons = RecipeRecommendationEngine()._exclusion_reasons(recipe, household(allergens=["dairy"]), [])

    assert any("dairy" in reason for reason in reasons)


def test_the_options_table_names_real_catalog_ingredients():
    release = repository_root() / "data-engineering/data/release/v2.1/ingredients.jsonl"
    names = {
        json.loads(line)["ingredient_id"][4:].lower()
        for line in release.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    for combined, choices in options().items():
        assert combined in names, combined
        assert len(choices) >= 2, combined
        assert set(choices) <= names, (combined, choices)
