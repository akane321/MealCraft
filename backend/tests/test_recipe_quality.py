from types import SimpleNamespace

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


def test_dish_families_group_variants_of_one_dish():
    from app.planning.recipe_quality import dish_family, dish_kind

    assert dish_family("Chinese-Style Fried Rice") == dish_family("Basic Fried Rice (Easy)") == "fried rice"
    assert dish_family("Fried Rice in a Flash") == "fried rice"
    assert dish_family("Magdalena's Empanadas") == "empanadas"
    assert dish_family("Thai Green Curry") != dish_family("Thai Red Curry")
    assert dish_family("Chicken Rice Bowl") != dish_family("Salmon Rice Bowl")
    assert dish_kind("Teriyaki Fried Rice") == dish_kind("Easy Chinese Egg Fried Rice") == "fried rice"
