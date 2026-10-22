"""Owner's three role refinements: evidence, boundaries, and unchanged batch freeze."""

import pytest

from app.data.recipe_tags import Dish, Line, rule_tags
from app.planning.vegetable_led import meat_share, vegetable_led


def tags(title, lines, course="side"):
    return rule_tags(
        Dish(
            "test",
            title,
            course,
            "test",
            4,
            400,
            10,
            2,
            40,
            [Line(*line) if len(line) == 3 else Line(*line, None) for line in lines],
            "Cook.",
        )
    )


@pytest.mark.parametrize(
    "title,starch",
    [
        ("Homemade Noodles", "flour"),
        ("Pasta", "semolina"),
        ("Polenta", "cornmeal"),
        ("Gnocchi", "potato"),
        ("Roti", "whole_wheat_flour"),
        ("Chapati", "flour"),
        ("Paratha", "flour"),
        ("Naan", "flour"),
        ("Flatbread", "flour"),
        ("Tortilla", "masa"),
        ("Tortilla", "corn_flour_masa"),
        ("Pasta", "semolina_flour"),
        ("Noodles", "brown_rice_flour"),
        ("Spaetzle", "flour"),
        ("Mantou", "flour"),
        ("Bao", "rice_flour"),
    ],
)
def test_homemade_staples_need_listed_majority_starch_and_binder_egg_is_not_main(title, starch):
    result = tags(title, [(starch, 200), ("egg", 200)])
    assert result.values["meal_role"] == "staple"
    assert result.values["contains_staple"] is True
    assert result.values["protein_sources"] == []
    assert result.methods["meal_role"] == "rule"
    assert tags(title, [(starch, None), ("egg", 200)]).values["meal_role"] != "staple"
    assert tags(title, [(starch, 199), ("egg", 201)]).values["meal_role"] != "staple"
    assert tags(title, [("egg", 200)]).values["meal_role"] != "staple"


@pytest.mark.parametrize(
    "title,course",
    [("Pasta Dough", "side"), ("Pie Crust", "side"), ("Pizza Dough", "side"), ("Noodle Cake", "dessert")],
)
def test_components_and_desserts_do_not_become_staples(title, course):
    assert tags(title, [("flour", 500), ("egg", 50)], course).values["meal_role"] != "staple"


def test_sweet_baked_flatbread_and_noodle_cake_keep_their_old_roles():
    dish = Dish(
        "sweet",
        "Sweet Stuffed Flatbread",
        "baked_good",
        "test",
        4,
        400,
        5,
        30,
        60,
        [Line("flour", 500, None), Line("egg", 50, None)],
        "Bake.",
    )
    assert rule_tags(dish).values["meal_role"] == "dessert"
    assert tags("Noodle Cake", [("flour", 500), ("egg", 50)]).values["meal_role"] != "staple"


@pytest.mark.parametrize(
    "protein,source", [("egg", "egg"), ("tofu", "soy"), ("chicken_breast", "chicken"), ("shrimp", "shellfish")]
)
def test_half_egg_soy_flesh_sides_are_mains(protein, source):
    result = tags("Cooked side", [(protein, 200), ("potato", 199), ("water", 2000), ("olive_oil", 90)])
    assert result.values["meal_role"] == "protein_main"
    assert source in result.values["protein_sources"]
    assert tags("Cooked side", [(protein, 199), ("potato", 201)]).values["meal_role"] != "protein_main"
    assert tags("Cooked side", [(protein, None), ("potato", 201)]).values["meal_role"] != "protein_main"
    assert tags("Cooked side", [(protein, 200), ("potato", 200)]).values["meal_role"] == "protein_main"
    assert tags("Cooked side", [("egg", 200), ("spinach", 200)]).values["meal_role"] == "protein_main"


@pytest.mark.parametrize("bean", ["pinto_beans", "kidney_bean", "chickpea"])
def test_pulse_led_sides_stay_deferred(bean):
    assert tags("Refried Beans", [(bean, 500), ("onion", 30)]).values["meal_role"] != "protein_main"


def test_generic_meat_can_establish_a_main_role_but_not_its_species_or_admission():
    from types import SimpleNamespace

    from app.planning.meal_composition import meal_role_of

    result = tags("Meat side", [("meat", 600), ("onion", 100)]).values
    assert result["meal_role"] == "protein_main" and result["protein_sources"] is None
    assert meal_role_of(SimpleNamespace(**result)) is None


def test_measured_flesh_threshold_is_combined_and_dressing_does_not_dilute_it():
    assert vegetable_led([("cabbage", 800), ("bacon", 150), ("shrimp", 50)])
    assert not vegetable_led([("cabbage", 800), ("bacon", 100), ("shrimp", 100)])
    assert not vegetable_led([("cabbage", 799), ("bacon", 100), ("shrimp", 101), ("water", 5000)])
    assert meat_share([("cabbage", 800), ("bacon", 200)]) == 0.2
    for grams in (None, 0, -1):
        assert meat_share([("cabbage", 800), ("bacon", grams)]) is None
        assert not vegetable_led([("cabbage", 800), ("bacon", grams)])
    assert meat_share([("cabbage", 800), ("garlic", 3, "garlic or 4 ounces cooked chicken")]) is None
    assert tags("Bacon cabbage", [("cabbage", 800), ("bacon", 200)]).values["meal_role"] == "vegetable"


@pytest.mark.parametrize("bean", ["edamame", "soybean", "fermented_soybeans"])
def test_whole_soybean_sides_do_not_gain_a_protein_main_role(bean):
    assert tags("Soybean side", [(bean, 500), ("onion", 30)]).values["meal_role"] != "protein_main"
    if bean == "edamame":
        assert tags("Teriyaki Edamame", [(bean, 500), ("onion", 30)]).values["meal_role"] == "vegetable"


@pytest.mark.parametrize("title", ["Yorkshire Puddings", "Egg Pancakes", "Crepes", "Savory Batter"])
def test_batter_side_names_are_not_protein_mains(title):
    assert tags(title, [("egg", 590), ("flour", 410)]).values["meal_role"] != "protein_main"


@pytest.mark.parametrize("starch", ["flour", "cornstarch", "potato_starch"])
def test_substantive_batter_starch_cannot_make_a_protein_main(starch):
    assert tags("Savory side", [("egg", 850), (starch, 150)]).values["meal_role"] != "protein_main"
    assert tags("Savory side", [("egg", 851), (starch, 149)]).values["meal_role"] == "protein_main"
