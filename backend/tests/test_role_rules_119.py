"""Owner's 2026-10-23 evidence-only extensions, with explicit negative boundaries."""

from dataclasses import replace

import pytest

from app.data.recipe_tags import Dish, Line, homemade_staple, rule_tags
from app.planning.vegetable_led import vegetable_led, vegetable_share


def dish(title, lines, course="side", sugar=2, carbs=40):
    return Dish(
        "test",
        title,
        course,
        "test",
        4,
        400,
        10,
        sugar,
        carbs,
        [Line(name, grams, None) for name, grams in lines],
        "Cook.",
        curated=True,
    )


@pytest.mark.parametrize(
    "title",
    [
        "Spaetzles",
        "Spatzles",
        "Corn Bread",
        "Cornbread",
        "Spoon Bread",
        "Fry Bread",
        "Mealie Pap",
        "Putupap",
        "Pap",
        "Mandarin Pancakes",
        "Moo Shu Pancakes",
        "Pupusas",
        "Yorkshire Pudding",
    ],
)
def test_new_names_still_need_a_majority_of_actual_starch(title):
    recipe = dish(title, [("flour", 600), ("egg", 400)])
    assert rule_tags(recipe).values["meal_role"] == "staple"
    assert rule_tags(recipe).values["protein_sources"] == []
    assert not homemade_staple(replace(recipe, lines=[Line("flour", 499, None), Line("egg", 501, None)]))
    assert not homemade_staple(replace(recipe, lines=[Line("egg", 1000, None)]))


@pytest.mark.parametrize("title", ["Pancakes", "Chocolate Pudding", "Noodle Cake"])
def test_pancakes_and_other_puddings_do_not_gain_the_exception(title):
    assert not homemade_staple(dish(title, [("flour", 600), ("egg", 400)]))


@pytest.mark.parametrize("course", ["side", "main", "baked_good"])
def test_homemade_sweetness_boundary_is_twenty_percent(course):
    recipe = dish("Cornbread", [("cornmeal", 600), ("egg", 100)], course, sugar=20, carbs=100)
    assert not homemade_staple(recipe)
    assert rule_tags(recipe).values["meal_role"] != "staple"
    result = rule_tags(recipe)
    if "meal_role" in result.open:
        assert "staple" not in result.allowed_roles
    assert homemade_staple(replace(recipe, sugar_g=19.9))


def test_yorkshire_lactose_exception_still_needs_half_flour():
    # Actual released unsweetened recipe: the milk's lactose pushes total sugar/carbs above .2.
    recipe = dish("Yorkshire Pudding", [("egg", 100), ("milk", 488), ("flour", 125)], sugar=6.3, carbs=29.9)
    assert rule_tags(recipe).values["meal_role"] == "staple"
    assert rule_tags(recipe).values["protein_sources"] == []
    assert not homemade_staple(replace(recipe, lines=[Line("flour", 99, None), Line("egg", 101, None)]))
    assert not homemade_staple(replace(recipe, title="Vanilla Pudding"))


@pytest.mark.parametrize("title", ["Sweet Potato Gnocchi", "Gnocches"])
def test_gnocchi_uses_listed_sweet_potato(title):
    assert homemade_staple(dish(title, [("sweet_potato", 600), ("egg", 100)]))
    assert not homemade_staple(dish(title, [("egg", 600), ("sweet_potato", 100)]))


@pytest.mark.parametrize(
    "title",
    ["Taco Shells", "Soft Shell Tacos", "Empanadas", "Wonton Wrappers", "Quiche", "Pastry Shells", "Tart", "Pie"],
)
def test_shells_require_dough_only_ingredient_evidence(title):
    recipe = dish(title, [("flour", 500), ("shortening", 100), ("vinegar", 5)], "main")
    assert rule_tags(recipe).values["meal_role"] == "sauce"
    filled = replace(recipe, lines=recipe.lines + [Line("beef", 300, None)])
    assert rule_tags(filled).values["meal_role"] != "sauce"


def test_shell_name_alone_does_not_make_a_component():
    assert rule_tags(dish("Stuffed Shells", [("pasta", 200), ("beef", 500)], "main")).values["meal_role"] == "one_bowl"
    assert rule_tags(dish("Pasta Shells", [("pasta", 200), ("beef", 500)], "main")).values["meal_role"] != "sauce"


@pytest.mark.parametrize("potato", ["potato", "instant_mashed_potato"])
def test_potato_dumplings_are_staples_not_protein_mains(potato):
    recipe = dish("Potato Dumplings", [(potato, 500), ("flour", 100), ("egg", 100)], "main")
    assert rule_tags(recipe).values["meal_role"] == "staple"
    assert rule_tags(recipe).values["protein_sources"] == []


@pytest.mark.parametrize("protein", ["chicken_breast", "fish_fillet", "tofu", "meat"])
def test_dumpling_exception_never_erases_protein_or_unknown_source(protein):
    recipe = dish(
        "Chicken & Dumplings" if protein == "chicken_breast" else "Dumplings",
        [("flour", 600), ("potato", 300), (protein, 100)],
        "main",
    )
    assert not homemade_staple(recipe)
    assert rule_tags(recipe).values["protein_sources"] != []
    assert not homemade_staple(replace(recipe, lines=recipe.lines[:-1] + [Line(protein, None, None)]))


def test_wrapped_dumplings_keep_the_wrapped_meal_rules():
    assert not homemade_staple(dish("Pierogi Dumplings", [("flour", 600), ("potato", 300), ("egg", 100)]))
    assert not homemade_staple(dish("Dumplings", [("cornmeal", 600), ("egg", 100)]))


def test_filled_homemade_pizza_counts_flour_as_its_carrier():
    recipe = dish("Homemade Pizza", [("flour", 300), ("beef", 300), ("tomato", 100)], "main")
    assert rule_tags(recipe).values["meal_role"] == "one_bowl"
    assert rule_tags(replace(recipe, title="Beef With Flour")).values["meal_role"] != "one_bowl"
    assert (
        rule_tags(replace(recipe, lines=[Line("flour", 300, None), Line("water", 100, None)])).values["meal_role"]
        == "sauce"
    )


@pytest.mark.parametrize("vegetables,expected", [(39, False), (40, True), (50, True)])
def test_tuber_allowance_starts_at_forty_percent_other_vegetables(vegetables, expected):
    lines = [("potato", 50), ("carrot", vegetables), ("cheddar", 50 - vegetables)]
    assert vegetable_led(lines) is expected
    assert vegetable_share(lines) == pytest.approx((50 + vegetables if expected else vegetables) / 100)


def test_tuber_allowance_does_not_relax_meat_or_majority_limits():
    assert vegetable_led([("carrot", 400), ("potato", 400), ("bacon", 200)])
    assert not vegetable_led([("carrot", 400), ("potato", 399), ("bacon", 201)])
    assert not vegetable_led([("carrot", 400), ("potato", 400), ("chicken_breast", 200)])
    assert not vegetable_led([("carrot", 400), ("potato", 400), ("bacon", None)])
    assert not vegetable_led([("carrot", 400), ("potato", 90), ("cheddar", 510)])
    assert not vegetable_led([("potato", 1000)])


@pytest.fixture(scope="module")
def catalog():
    from app.data.recipe_tags import release_dishes

    return {row.key: row for row in release_dishes()}


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("RCP2_C7CFCE59ABE9", True),
        ("RCP2_76DAFDABA87D", True),
        ("RCP2_91E87A1057FC", True),
        ("RCP2_9C278A40B536", True),
        ("RCP2_212042A4393F", True),
        ("RCP2_01D48A672ACA", False),
        ("RCP2_9B204E51C88D", False),
        ("RCP2_B8E67A023CFD", False),
    ],
)
def test_owner_catalog_tuber_examples(catalog, rid, expected):
    recipe = catalog[rid]
    assert vegetable_led([(x.name, x.grams, x.text) for x in recipe.lines]) is expected


def test_released_yorkshire_and_sweet_festivals_are_distinct(catalog):
    assert rule_tags(catalog["RCP2_C25D9C4D878B"]).values["meal_role"] == "staple"
    assert rule_tags(catalog["RCP2_02600E447144"]).values["meal_role"] != "staple"
    assert "staple" not in rule_tags(catalog["RCP2_02600E447144"]).allowed_roles
    assert rule_tags(catalog["RCP2_57F7D87302B2"]).values["meal_role"] == "sauce"


def test_the_two_pupusas_are_staples_not_cheese_protein_mains(catalog):
    for rid in ("RCP2_3C310D373BB9", "RCP2_BBD46E78E711"):
        assert rule_tags(catalog[rid]).values["meal_role"] == "staple"


@pytest.mark.parametrize(
    "rid",
    [
        "RCP2_3D533F04D12A",
        "RCP2_4117AD098162",
        "RCP2_6BE1A90E3B64",
        "RCP2_B237C38BB623",
        "RCP2_F5D923D65747",
    ],
)
def test_the_five_actual_homemade_pizzas_have_a_staple_carrier(catalog, rid):
    assert rule_tags(catalog[rid]).values["meal_role"] == "one_bowl"
