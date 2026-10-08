from types import SimpleNamespace

import pytest

from app.planning.recipe_quality import incomplete


def recipe(title, kcal, ingredients, course="main", release="v2.1"):
    return SimpleNamespace(
        title=title,
        course=course,
        release_version=release,
        nutrition=SimpleNamespace(calories_kcal=kcal),
        recipe_ingredients=[SimpleNamespace(ingredient=SimpleNamespace(normalized_name=n)) for n in ingredients],
    )


def test_a_main_that_lost_its_main_line_is_not_planned():
    assert incomplete(recipe("Steak Teriyaki", 64, ["soy_sauce", "brown_sugar"])) is not None
    assert incomplete(recipe("Korean Pork Chops", 420, ["soy_sauce", "sesame_seed"])) == "named pork but lists none"


def test_complete_dishes_soups_and_curated_recipes_are_kept():
    assert incomplete(recipe("Korean Pork Chops", 387, ["pork_chop", "soy_sauce"])) is None
    assert incomplete(recipe("Gazpacho", 109, ["tomato", "cucumber"], course="soup")) is None
    assert incomplete(recipe("Lemon Chicken", 90, ["lemon"], release=None)) is None


@pytest.mark.parametrize(
    ("title", "course", "ingredients"),
    [
        ("Magdalena's Empanadas", "main", ["flour", "water", "butter", "salt"]),
        ("Cannelloni", "main", ["flour", "milk", "egg"]),
        ("Rolled Dumplings", "main", ["flour", "salt", "shortening", "milk"]),
        (
            "Pot Pie (Square Dumplings)",
            "soup",
            ["flour", "salt", "milk", "baking powder", "shortening"],
        ),
        ("Rolled Dumplings", "side", ["flour", "salt", "shortening", "milk"]),
    ],
)
def test_wrapper_or_dough_only_recipes_are_not_planned(title, course, ingredients):
    assert incomplete(recipe(title, 400, ingredients, course=course)) == "wrapper or dough with no filling"


def test_a_filled_wrapper_and_a_real_vegetable_soup_remain_plannable():
    assert (
        incomplete(
            recipe(
                "Beef Empanadas",
                500,
                ["flour", "water", "butter", "salt", "ground beef", "onion"],
            )
        )
        is None
    )
    assert (
        incomplete(
            recipe(
                "Potato Dumpling Soup",
                250,
                ["potato", "onion", "chicken broth", "flour", "milk"],
                course="soup",
            )
        )
        is None
    )


def test_a_broth_based_dumpling_soup_is_not_dough_only():
    assert (
        incomplete(recipe("Chicken Dumpling Soup", 250, ["flour", "salt", "milk", "chicken_broth"], course="soup"))
        is None
    )


def test_planning_repository_drops_dough_only_recipes_but_keeps_filled_dishes():
    from decimal import Decimal

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base
    from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition
    from app.repositories.recipe import RecipeRepository

    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    ingredients = {}

    def release_recipe(slug, title, course, ingredient_names):
        for name in ingredient_names:
            ingredients.setdefault(name, Ingredient(normalized_name=name, display_name=name))
        return Recipe(
            slug=slug,
            title=title,
            description="Test release recipe",
            cuisine="test",
            meal_type=course,
            course=course,
            servings=4,
            prep_time_minutes=10,
            cook_time_minutes=20,
            release_version="v2.1",
            nutrition=RecipeNutrition(
                calories_kcal=Decimal("400"),
                protein_g=Decimal("20"),
                carbohydrate_g=Decimal("40"),
                fat_g=Decimal("10"),
                sodium_mg=Decimal("500"),
                sugar_g=Decimal("5"),
            ),
            recipe_ingredients=[
                RecipeIngredient(
                    ingredient=ingredients[name],
                    quantity=Decimal("10"),
                    unit="g",
                    sort_order=index,
                )
                for index, name in enumerate(ingredient_names, start=1)
            ],
        )

    with Session(engine) as session:
        session.add_all(
            [
                release_recipe("wrapper", "Magdalena's Empanadas", "main", ["flour", "water", "butter", "salt"]),
                release_recipe(
                    "filled", "Beef Empanadas", "main", ["flour", "water", "butter", "salt", "beef", "onion"]
                ),
                release_recipe("dough-side", "Rolled Dumplings", "side", ["flour", "salt", "shortening", "milk"]),
            ]
        )
        session.commit()
        planned = RecipeRepository(session)._load_for_planning(session, ["main", "side", "soup"])

    assert [item.slug for item in planned] == ["filled"]


def test_dish_families_group_variants_of_one_dish():
    from app.planning.recipe_quality import dish_family, dish_kind

    assert dish_family("Chinese-Style Fried Rice") == dish_family("Basic Fried Rice (Easy)") == "fried rice"
    assert dish_family("Fried Rice in a Flash") == "fried rice"
    assert dish_family("Magdalena's Empanadas") == "empanadas"
    assert dish_family("Thai Green Curry") != dish_family("Thai Red Curry")
    assert dish_family("Chicken Rice Bowl") != dish_family("Salmon Rice Bowl")
    assert dish_kind("Teriyaki Fried Rice") == dish_kind("Easy Chinese Egg Fried Rice") == "fried rice"
