"""Owner's 2026-10-23 role decisions: staple vocabulary, tuber mains, bean sides, condiment sides, reviewer roles."""

from functools import cache

import pytest

from app.data import recipe_tags
from app.data.recipe_tags import (
    MEAL_ROLES,
    STARCHY,
    Dish,
    Line,
    Tags,
    _llm_payload,
    catalog_ingredients,
    curated_dishes,
    release_dishes,
    review_roles,
    rule_tags,
)
from app.planning.vegetable_led import COOKED_STAPLES, STARCHY_TUBERS


def dish(title, lines, course="main", sugar=2, carbs=40):
    return Dish("test", title, course, "test", 4, 400, 10, sugar, carbs, [Line(n, g, None) for n, g in lines], "Cook.")


def role(*args, **kwargs):
    return rule_tags(dish(*args, **kwargs)).values["meal_role"]


@cache
def catalog() -> dict[str, Dish]:
    return {item.key: item for item in curated_dishes() + release_dishes()}


def test_starchy_is_derived_from_the_vegetable_rules_tubers_and_adds_plantain():
    assert STARCHY_TUBERS <= STARCHY
    assert {"cassava", "taro", "ube", "plantain"} <= STARCHY


@pytest.mark.parametrize(
    "name",
    [
        "STAPLES",
        "STARCHY",
        "BREAD_CARRIERS",
        "DOUGH_FLOUR",
        "HOMEMADE_STARCH",
        "BATTER_STARCH",
        "PIZZA_BATTER",
        "SHELL_DOUGH",
        "RICE_GRAINS",
        "SOUP_STAPLES",
        "WHOLE_SOYBEANS",
    ],
)
def test_every_staple_and_starch_id_exists_in_the_release_or_curated_catalog(name):
    assert set(getattr(recipe_tags, name)) - set(catalog_ingredients()) == set()
    assert COOKED_STAPLES <= set(catalog_ingredients())


def test_cassava_and_plantain_fufu_is_a_staple():
    tags = rule_tags(catalog()["RCP2_2848D4DD38CE"])
    assert tags.values["meal_role"] == "staple" and tags.values["contains_staple"] is True


def test_a_protein_less_tuber_main_is_a_staple_from_sixty_percent():
    assert role("Potato Stew", [("potato", 600), ("onion", 400)]) == "staple"
    assert role("Potato Stew", [("potato", 590), ("onion", 410)]) != "staple"
    assert role("Cassava Stew", [("cassava", 300), ("plantain", 300), ("tomato", 400)]) == "staple"
    # A main protein keeps it a protein main, and an unknown meat is not "no protein".
    assert role("Potato Stew", [("potato", 600), ("chicken", 400)]) == "protein_main"
    assert role("Potato Stew", [("potato", 600), ("meat", 400)]) != "staple"


@pytest.mark.parametrize("rice", [0, 100])
def test_a_bean_led_side_is_offered_staple_but_not_assigned_it(rice):
    beans = dish("Black Beans", [("black_beans", 600), ("onion", 100), ("rice", rice)], course="side")
    tags = rule_tags(beans)
    assert tags.values["meal_role"] is None and tags.values["protein_sources"] == ["legume"]
    assert "protein_main" not in review_roles(beans, tags) and "staple" in review_roles(beans, tags)
    # Without any listed staple only the reviewer gains it; the model prompt's options are unchanged.
    assert ("staple" in tags.allowed_roles) is bool(rice)


def test_a_cornmeal_coating_does_not_make_oven_fried_chicken_a_staple():
    assert rule_tags(catalog()["RCP2_CF1AE85FDA4E"]).values["meal_role"] == "protein_main"
    assert role("Cornmeal Crusted Catfish", [("catfish", 600), ("cornmeal", 200)]) == "protein_main"


@pytest.mark.parametrize(
    "title,starch",
    [
        ("Hush Puppies", "cornmeal"),
        ("Arepas", "corn_flour_masa"),
        ("Easy Sopes", "corn_flour_masa"),
        ("Injera", "teff_flour"),
        ("Fufu", "cassava"),
    ],
)
def test_corn_masa_and_tuber_staples_need_a_staple_title(title, starch):
    assert role(title, [(starch, 600), ("water", 300), ("egg", 50)], course="side") == "staple"
    assert role(title, [(starch, 400), ("egg", 600)], course="side") != "staple"
    if starch != "cassava":
        assert role("Corn Fritters", [(starch, 600), ("egg", 50)], course="side") != "staple"


def test_plantain_is_a_side_staple_but_not_inside_a_protein_main():
    assert role("Fried Plantains", [("plantain", 600), ("vegetable_oil", 50)], course="side") == "staple"
    assert role("Chicken With Plantains", [("chicken", 500), ("plantain", 500)]) == "protein_main"


@pytest.mark.parametrize("key", ["RCP2_E8D667BA918A", "RCP2_9150197BEBD9", "RCP2_472B6677B22B"])
def test_condiment_type_protein_sides_are_not_protein_mains(key):
    # Fake Feta, Ajitsuke Tamago (for ramen), Tofu Feta.
    assert rule_tags(catalog()[key]).values["meal_role"] != "protein_main"


def test_the_condiment_criterion_is_the_title_not_every_protein_side():
    lines = [("egg", 300), ("salt", 3)]
    assert role("Rolled Omelette", lines, course="side") == "protein_main"
    assert role("Omelette With Cheese", lines, course="side") == "protein_main"
    # A dish made with feta, ricotta or paneer is not that cheese.
    assert role("Spinach And Feta Frittata", lines, course="side") == "protein_main"
    assert role("Frittata With Ricotta", lines, course="side") == "protein_main"
    for title in ("Mock Cheese", "Tofu Feta", "Marinated Egg For Ramen", "Scrambled Egg Garnish"):
        assert role(title, lines, course="side") != "protein_main", title


def test_the_reviewer_gets_staple_and_one_bowl_but_the_model_prompt_does_not():
    souffle = dish("Spinach Souffle", [("egg", 200), ("spinach", 150), ("cheddar", 150)], course="side")
    tags = rule_tags(souffle)
    assert tags.values["meal_role"] is None
    assert not {"staple", "one_bowl"} & set(tags.allowed_roles)
    assert not {"staple", "one_bowl"} & set(_llm_payload(souffle, tags)["allowed_meal_roles"])
    assert {"staple", "one_bowl"} <= set(review_roles(souffle, tags))
    # A decided role, or an incomplete recipe, offers the reviewer nothing more.
    assert review_roles(souffle, Tags(values={"meal_role": "vegetable"})) == ["vegetable"]
    assert review_roles(souffle, Tags(values={"meal_role": None})) == []


def test_reviewer_roles_widen_model_roles_only_by_staple_and_one_bowl_across_the_catalog():
    for item in catalog().values():
        tags = rule_tags(item)
        model = [tags.values["meal_role"]] if tags.values["meal_role"] else list(tags.allowed_roles) * bool(tags.open)
        review = review_roles(item, tags)
        assert set(model) <= set(review) and set(review) - set(model) <= {"staple", "one_bowl"}, item.key
        assert review == [r for r in MEAL_ROLES if r in review]
