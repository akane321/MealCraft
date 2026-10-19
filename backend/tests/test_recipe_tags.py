"""The tag rules on fixtures, the committed tag files, and the importers' overlay of them."""

import json
import re
import shutil
from functools import cache
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from sqlalchemy import CheckConstraint, create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data import release_v2, tag_files
from app.data.catalog import import_catalog, load_catalog
from app.data.recipe_tags import (
    ONE_BOWL_SHARE,
    RICE_DISH,
    RICE_GRAINS,
    Dish,
    Line,
    catalog_ingredients,
    component,
    curated_dishes,
    dish_vegetable_led,
    ingredient_entries,
    merge_answer,
    release_dishes,
    rule_tags,
    staple_share,
)
from app.data.release_v2 import IMPORTER_VERSION, import_release_v2, release_digest, release_dir
from app.db.base import Base
from app.models.recipe import Ingredient, Recipe
from app.schemas.catalog_tags import CookingMethod, EquipmentNeeds, FlavorTag, MealRole, ProteinSource, RecipeEstimates


def dish(title: str, course: str, lines: list[tuple[str, float | None]], steps: str = "Mix.", **nutrition) -> Dish:
    values = {"kcal": 400.0, "fat_g": 15.0, "sugar_g": 5.0, "carbohydrate_g": 40.0} | nutrition
    return Dish(
        key="RCP2_TEST",
        title=title,
        course=course,
        cuisine="chinese",
        servings=4,
        lines=[Line(name, grams, None) for name, grams in lines],
        steps=steps,
        **values,
    )


def tags(*args, **kwargs) -> dict:
    return rule_tags(dish(*args, **kwargs)).values


# --- the rules ---------------------------------------------------------------------------------------------


def test_a_meat_main_is_a_protein_main_and_its_sauces_are_not_protein() -> None:
    found = tags(
        "Garlic Chicken Stir-Fry",
        "main",
        [("chicken_thigh", 400), ("broccoli", 200), ("soy_sauce", 30), ("oyster_sauce", 15), ("garlic", 10)],
        "Stir-fry the chicken in a hot wok until browned. Add broccoli and the sauces.",
    )
    assert found["meal_role"] == "protein_main"
    assert found["contains_staple"] is False
    # Soy sauce is made from soybeans and oyster sauce from oysters; neither is the dish's protein.
    assert found["protein_sources"] == ["chicken"]
    assert "stir_fry" in found["cooking_methods"]


def test_a_main_carrying_its_rice_is_one_bowl() -> None:
    found = tags("Egg Fried Rice", "main", [("rice", 300), ("egg", 150), ("peas", 100), ("vegetable_oil", 30)])
    assert found["meal_role"] == "one_bowl"
    assert found["contains_staple"] is True
    assert found["protein_sources"] == ["egg"]


def test_the_vegetable_role_follows_the_vegetable_led_rule() -> None:
    greens = dish("Garlic Bok Choy", "side", [("bok_choy", 400), ("garlic", 10), ("oyster_sauce", 15)])
    assert dish_vegetable_led(greens)
    assert rule_tags(greens).values["meal_role"] == "vegetable"
    assert rule_tags(greens).values["protein_sources"] == []

    # Bacon makes it a dish with meat (owner, 2026-10-02): never a vegetable, and the rules leave it open.
    bacon = rule_tags(dish("Cabbage With Bacon", "side", [("cabbage", 400), ("bacon", 60)]))
    assert bacon.values["meal_role"] is None
    assert "vegetable" not in bacon.allowed_roles and "salad" not in bacon.allowed_roles
    # A side is never the meal's main, and a dish with no main protein never a protein main.
    assert "protein_main" not in bacon.allowed_roles
    plain = rule_tags(dish("Cornmeal Bake", "main", [("cornmeal", 300), ("milk", 200)]))
    assert plain.values["meal_role"] is None and "protein_main" not in plain.allowed_roles
    assert bacon.values["protein_sources"] == ["pork"]


def test_a_stock_is_not_the_soups_protein_and_a_noodle_soup_is_one_bowl() -> None:
    soup = tags("Carrot Soup", "soup", [("chicken_broth", 1000), ("carrot", 300)], "Simmer, then blend until smooth.")
    assert soup["meal_role"] == "soup"
    assert soup["protein_sources"] == []
    assert soup["equipment"] == [["blender"]]
    pho = tags("Beef Pho", "soup", [("rice_noodles", 200), ("beef", 250), ("beef_broth", 1500), ("bean_sprouts", 100)])
    assert pho["meal_role"] == "one_bowl"
    assert pho["protein_sources"] == ["beef"]
    # No noodle word in the title, but the noodles are a good part of it.
    prawn = tags("Vietnamese Prawn Soup", "soup", [("rice_noodles", 120), ("shrimp", 300), ("water", 1500)])
    assert prawn["meal_role"] == "one_bowl"


def test_baked_goods_go_by_title_and_sugar_and_a_cakes_eggs_are_not_protein() -> None:
    bread = tags("Classic Focaccia", "baked_good", [("bread_flour", 500), ("olive_oil", 50), ("yeast", 7)], sugar_g=1.0)
    assert bread["meal_role"] == "staple"
    cake = tags("Chocolate Cake", "baked_good", [("flour", 250), ("sugar", 200), ("egg", 200)], sugar_g=30.0)
    assert cake["meal_role"] == "dessert"
    assert cake["protein_sources"] == []


COMPONENTS = (
    ("Taco Meat Filling", "main"),
    ("Beef Taco Filling", "main"),
    ("Taco Filling (Ground Beef)", "main"),
    ("Carnitas Filling", "main"),
    ("Egg Filling For Pita Bread", "breakfast"),
    ("Cheese And Prosciutto Manicotti Filling", "main"),
    ("Herbed Ricotta Filling For Manicotti", "main"),
    ("Spinach Pizza Topping", "side"),
    ("Menma Ramen Topping", "main"),
    ("Italian Pizza Dough", "baked_good"),
    ("Egg Pasta Dough", "main"),
    ("Curry Sauce", "main"),
    ("Spaghetti Sauce", "main"),
    ("Chicken Teriyaki Marinade", "main"),
    ("Lamb Shish Kebab Marinade", "main"),
    ("Manicotti(Batter)", "main"),
    ("Kolache Dough", "baked_good"),
    ("Masa De Empanadas (Empanada Dough)", "baked_good"),
    ("Great Pizza Crust", "baked_good"),
    ("Broccoli Pizza Crust", "main"),
    ("Pizza Crust I", "baked_good"),
    ("Basic New York-Style Pizza Dough Recipe", "baked_good"),
    ("Garlic And Oregano Pizza Dough", "baked_good"),
    ("Grilled Chicken Marinade - Super Easy; Great For Fajitas!", "main"),
    ("Pancake Batter For Tacos", "side"),
    ("Jamaican Jerk Rub", "main"),
    ("Chicken Stock", "soup"),
)
DISHES = (
    ("Chicken With Mushroom Filling", "main"),
    ("Pizza With Spinach Topping", "main"),
    ("Chicken In Tarragon Sauce", "main"),
    ("Satay With Peanut Sauce", "main"),
    ("Pizza With A Hamburger Crust", "main"),
    ("Cauliflower Crust Pizza", "main"),
    ("No Crust Quiche", "main"),
    ("Two-Step Batter Fried Chicken", "main"),
    ("Meatballs For Spaghetti Sauce", "main"),
    ("Meatballs And Marinara Sauce", "main"),
    ("Steak 'N Korean Sauce", "main"),
    ("Pan-fried hake, white bean & chorizo broth", "main"),
    ("Ca Kho To (Vietnamese Fish In Caramel Sauce)", "main"),
    ("Squash Dressing", "side"),
)


@pytest.mark.parametrize(("title", "course"), COMPONENTS)
def test_a_component_recipe_is_a_sauce_and_fills_no_meal(title: str, course: str) -> None:
    found = rule_tags(dish(title, course, [("chicken_thigh", 400), ("flour", 300), ("rice", 300)]))
    assert found.values["meal_role"] == "sauce", title
    assert found.values["contains_staple"] is False and found.values["protein_sources"] == []
    assert found.methods["meal_role"] == "rule" and not found.open


@pytest.mark.parametrize(("title", "course"), DISHES)
def test_a_dish_with_a_component_in_its_title_stays_a_dish(title: str, course: str) -> None:
    assert not component(title, course), title


def test_minor_protein_lines_are_not_the_main_protein_and_poultry_counts_as_chicken() -> None:
    found = tags("Turkey Meatloaf", "main", [("turkey", 900), ("egg", 50), ("breadcrumbs", 60), ("onion", 100)])
    assert found["protein_sources"] == ["chicken"]
    goat = tags("Goat Curry", "main", [("goat", 800), ("potato", 300), ("curry_powder", 10)])
    assert goat["protein_sources"] == ["lamb"]


def test_missing_meat_is_not_fabricated_from_a_title_or_asked_of_a_model() -> None:
    missing = rule_tags(dish("Mutton Biryani", "main", [("yogurt", 245), ("anise", 1.4)]))
    assert missing.values["protein_sources"] is None and missing.values["meal_role"] is None
    assert missing.incomplete_reason == "named mutton but lists none" and missing.open == []
    lost = tags("Chicken Fried Rice", "main", [("rice", 300), ("egg", 150), ("chicken", 10), ("soy_sauce", 20)])
    assert lost["protein_sources"] == ["egg"]  # The real chicken line is below the main-source threshold.
    assert tags("Turkey Banh Mi", "main", [("baguette", 200), ("carrot", 100)])["protein_sources"] is None
    assert tags("Meat Loaf (Beef)", "main", [("meat", 900), ("breadcrumbs", 60)])["protein_sources"] is None
    # Lines holding meat win over the title; mock meat and what a dish is served with do not count.
    assert tags("Chicken Fried Steak", "main", [("beef_steak", 600), ("flour", 60)])["protein_sources"] == ["beef"]
    assert tags('Tempeh "Bacon"', "side", [("tempeh", 200), ("soy_sauce", 20)])["protein_sources"] == ["soy"]
    assert tags("Toasted Rice For Fish", "side", [("rice", 200), ("butter", 20)])["protein_sources"] == []
    game = rule_tags(dish("Braised Rabbit", "main", [("rabbit", 900), ("carrot", 200)]))
    assert game.values["protein_sources"] is None and "protein_sources" not in game.open
    assert game.values["meal_role"] == "protein_main"


def test_the_models_answer_keeps_only_what_the_lines_support() -> None:
    meat = rule_tags(dish("Fried Rice", "main", [("rice", 300), ("meat", 200), ("egg", 100)]))
    merge_answer(meat, {"protein_sources": ["pork", "beef", "egg", "legume"]})
    # Neither an animal nor a major source may be guessed for generic meat.
    assert meat.values["protein_sources"] is None
    assert "protein_sources" not in meat.methods
    cookie = rule_tags(dish("Kifliks", "baked_good", [("flour", 300), ("egg", 100), ("walnut", 100)], sugar_g=8.0))
    assert cookie.values["meal_role"] is None and cookie.values["protein_sources"] == ["egg"]
    merge_answer(cookie, {"meal_role": "dessert", "protein_sources": None})
    # A dessert's eggs are not its protein, whoever decided the role.
    assert cookie.values["protein_sources"] == [] and cookie.methods["protein_sources"] == "llm"


def test_explicit_ingredient_wording_beats_generic_ids_and_does_not_split_mixed_weights() -> None:
    beef = dish("Pasties", "main", [("meat", 900), ("onion", 200)])
    beef.lines[0].text = "5 lb. meat, cut small (beef stew or chuck roast)"
    assert rule_tags(beef).values["protein_sources"] == ["beef"]
    mixed = dish("Spiedies", "main", [("meat", 900)])
    mixed.lines[0].text = "5 lbs meat, cut into cubes (pork & chicken)"
    found = rule_tags(mixed)
    assert found.values["protein_sources"] is None and found.allowed_sources == {"pork", "chicken"}
    assert found.values["meal_role"] == "protein_main" and found.values["contains_staple"] is False
    mixed.lines[0].text = "5 lbs pork or chicken"
    assert rule_tags(mixed).values["protein_sources"] is None


def test_complete_carriers_count_but_a_meatloaf_binder_and_legumes_are_not_staples() -> None:
    bobotie = tags("Bobotie", "main", [("beef", 454), ("bread", 58), ("egg", 100), ("onion", 110)])
    assert bobotie["meal_role"] == "protein_main" and bobotie["contains_staple"] is False
    sandwich = tags("Steak Sandwiches", "main", [("beef_steak", 2041), ("bread", 348), ("onion", 640)])
    assert sandwich["meal_role"] == "one_bowl" and sandwich["contains_staple"] is True
    pasties = tags("Beef Pasties", "main", [("flour", 1750), ("beef", 2268), ("potato", 6350)])
    assert pasties["meal_role"] == "one_bowl" and pasties["contains_staple"] is True
    lentils = rule_tags(dish("Sweet And Sour Lentils", "side", [("lentil", 192), ("onion", 110)]))
    assert lentils.values["meal_role"] is None and "one_bowl" not in lentils.allowed_roles
    gratin = rule_tags(dish("Cauliflower Au Gratin", "side", [("cauliflower", 588), ("ham", 113)]))
    assert gratin.values["meal_role"] is None and "soup" not in gratin.allowed_roles


def test_cooked_rice_is_not_multiplied_by_the_dry_rice_yield_again() -> None:
    from app.data.recipe_tags import staple_share

    cooked = dish("Rice", "main", [("rice", 100), ("egg", 100)])
    cooked.lines[0].text = "100 g cooked rice"
    assert staple_share(cooked) == 0.5
    cooked.lines[0].text = "100 g dry rice"
    assert staple_share(cooked) == pytest.approx(250 / 350)


def test_rice_meals_filed_as_sides_keep_their_real_staple_without_lowering_thresholds() -> None:
    spanish = dish("Spanish Rice", "side", [("rice", 316), ("bell_pepper", 120), ("tomato", 123), ("onion", 110)])
    spanish.lines[0].text = "2 c. cooked rice"
    assert rule_tags(spanish).values["meal_role"] == "staple"
    pumpkin = dish("Pumpkin Fried Rice", "side", [("rice", 316), ("pumpkin", 245), ("egg", 100), ("onion", 55)])
    pumpkin.lines[0].text = "2 cups Cooked White Rice"
    found = rule_tags(pumpkin).values
    assert found["meal_role"] == "one_bowl" and found["contains_staple"] is True
    # A title cannot supply rice that is absent or present only as a tiny garnish.
    absent = tags("Cauliflower Rice", "side", [("cauliflower", 500)])
    assert absent["contains_staple"] is False
    tiny = dish("Vegetables With Rice", "side", [("rice", 10), ("carrot", 500)])
    tiny.lines[0].text = "10 g cooked rice"
    assert rule_tags(tiny).values["meal_role"] != "staple"


def test_imitation_crab_is_not_reinterpreted_as_real_crab_by_a_word_match() -> None:
    imitation = dish("Crab Salad", "salad", [("imitation_crab", 227), ("tomato", 246)])
    imitation.lines[0].text = "8 oz. imitation crab meat, chunked"
    assert rule_tags(imitation).values["protein_sources"] == ["fish"]
    real = dish("Crab Salad", "salad", [("crab", 227), ("tomato", 246)])
    real.lines[0].text = "8 oz. fresh crab meat"
    assert rule_tags(real).values["protein_sources"] == ["shellfish"]


def test_owner_reviewed_source_conflict_is_unknown_without_erasing_the_known_soup_role() -> None:
    soup = dish("Korean Fusion Butternut Squash Soup", "soup", [("sausage", 255), ("butternut_squash", 800)])
    soup.key = "RCP2_0DA06DF48EDB"
    soup.lines[0].text = "3 Italian sausages (I use Turkey, can substitute vegan alternative)"
    found = rule_tags(soup)
    assert found.values["meal_role"] == "soup" and found.values["contains_staple"] is False
    assert found.values["protein_sources"] is None and found.open == []
    assert found.incomplete_reason.startswith("ingredient/step conflict")


def test_rule_regeneration_keeps_the_unreviewed_model_batch_frozen(monkeypatch) -> None:
    from app.data import recipe_tags

    item = dish("Bobotie", "main", [("beef", 454), ("bread", 58), ("egg", 100), ("onion", 110)])
    old = {
        "meal_role": "one_bowl",
        "contains_staple": True,
        "estimated": {
            name: {"method": "llm", "batch": recipe_tags.LLM_BATCH, "reviewed": False}
            for name in ("meal_role", "contains_staple")
        },
    }
    monkeypatch.setattr(recipe_tags, "curated_dishes", lambda: [])
    monkeypatch.setattr(recipe_tags, "release_dishes", lambda: [item])
    monkeypatch.setattr(recipe_tags, "previous_file", lambda: {"recipes": {item.key: old}})
    monkeypatch.setattr(recipe_tags, "ask_model", lambda *a: pytest.fail("No model call authorized"))
    fresh = rule_tags(item)
    assert fresh.values["meal_role"] == "protein_main"
    frozen = recipe_tags.build(False, 0)["tagged"][0][1]
    assert frozen.values["meal_role"] == "one_bowl" and frozen.methods["meal_role"] == "llm"
    entry = recipe_tags.recipe_entry(frozen, old)
    assert entry["estimated"]["meal_role"]["reviewed"] is False


def test_a_known_role_is_not_erased_but_unknown_main_sources_are_not_structured_candidates() -> None:
    from types import SimpleNamespace

    from app.planning.meal_composition import meal_role_of

    recipe = SimpleNamespace(meal_role="protein_main", protein_sources=None, estimated={})
    assert meal_role_of(recipe) is None
    assert recipe.meal_role == "protein_main"  # Known taxonomy and planning eligibility are different facts.
    recipe.protein_sources = ["pork", "chicken"]
    assert meal_role_of(recipe) == "protein_main"


def test_cooking_methods_and_equipment_come_from_keywords() -> None:
    either = tags("Wings", "main", [("chicken_wings", 900), ("salt", 5)], "Bake in the oven, or air fry at 200C.")
    assert either["equipment"] == [["oven", "air_fryer"]]
    assert "bake" in either["cooking_methods"]
    # A Dutch oven is a pot.
    stew = tags("Beef Stew", "main", [("beef", 900), ("carrot", 200)], "Braise in a Dutch oven on the stove.")
    assert stew["equipment"] == []
    assert "braise" in stew["cooking_methods"]
    fish = tags("Steamed Fish", "main", [("cod", 500), ("ginger", 20)], "Steam over high heat for 10 minutes.")
    assert fish["equipment"] == [["steamer"]]
    assert fish["cooking_methods"] == ["steam"]
    fried = tags("Fried Chicken", "main", [("chicken", 900), ("flour", 100)], "Deep-fry in batches until golden.")
    assert "deep_fry" in fried["cooking_methods"]
    assert "pan_fry" not in fried["cooking_methods"]
    raw = tags("Cucumber Salad", "salad", [("cucumber", 400), ("rice_vinegar", 20)], "Slice and toss.")
    assert raw["cooking_methods"] == ["raw"]
    assert raw["meal_role"] == "salad"


def test_flavor_tags() -> None:
    hot = tags("Sambal Kangkung", "side", [("spinach", 400), ("sambal_oelek", 40), ("garlic", 10)])
    assert "spicy" in hot["flavor_tags"]
    aromatic = tags("Herb Chicken", "main", [("chicken", 600), ("garlic", 10), ("ginger", 10), ("lemongrass", 10)])
    assert "fragrant" in aromatic["flavor_tags"]
    rich = tags("Cream Pasta", "main", [("pasta", 300), ("cream", 300)], kcal=800.0, fat_g=50.0)
    assert "rich" in rich["flavor_tags"] and "light" not in rich["flavor_tags"]
    light = tags("Poached Chicken", "main", [("chicken_breast", 600), ("cucumber", 200)], kcal=300.0, fat_g=6.0)
    assert "light" in light["flavor_tags"] and "rich" not in light["flavor_tags"]


def test_ingredient_rules() -> None:
    entries = ingredient_entries()
    assert entries["spinach"]["perishable"] and entries["bean_sprouts"]["perishable"]
    assert entries["shrimp"]["perishable"] and entries["salmon"]["perishable"]
    # A curated cut takes its release ingredient's class and group; canned fish and meat are not short-lived.
    assert entries["salmon_fillet"]["perishable"] and entries["salmon_fillet"]["food_group"] == "protein"
    assert not entries["canned_tuna"]["perishable"]
    assert not entries["chicken_breast"]["perishable"] and not entries["cabbage"]["perishable"]
    assert entries["salt"]["basic_seasoning"] and entries["soy_sauce"]["basic_seasoning"]
    assert not entries["curry_paste"]["basic_seasoning"]
    assert entries["baby_spinach"]["methods"]["food_group"] == "hierarchy"


# --- the committed tag files -------------------------------------------------------------------------------


@cache
def committed(relative: str, key: str) -> dict:
    return json.loads((repository_root() / relative).read_text(encoding="utf-8"))[key]


@cache
def dishes() -> dict[str, Dish]:
    return {item.key: item for item in curated_dishes() + release_dishes()}


def test_every_imported_recipe_and_catalog_ingredient_has_an_entry() -> None:
    assert set(committed(tag_files.RECIPE_TAGS, "recipes")) == set(dishes())
    assert set(committed(tag_files.INGREDIENT_TAGS, "ingredients")) == set(catalog_ingredients())


def _check_values(table: str, name: str) -> set[str]:
    constraint = next(
        item
        for item in Base.metadata.tables[table].constraints
        if isinstance(item, CheckConstraint) and item.name == name
    )
    return set(re.findall(r"'([^']*)'", str(constraint.sqltext)))


def test_every_written_value_is_one_the_types_and_the_check_constraint_accept() -> None:
    adapters = {
        "meal_role": TypeAdapter(MealRole | None),
        "contains_staple": TypeAdapter(bool | None),
        "protein_sources": TypeAdapter(list[ProteinSource] | None),
        "cooking_methods": TypeAdapter(list[CookingMethod] | None),
        "equipment": TypeAdapter(EquipmentNeeds | None),
        "flavor_tags": TypeAdapter(list[FlavorTag] | None),
        "estimated": TypeAdapter(RecipeEstimates),
    }
    allowed_roles = _check_values("recipes", "recipes_meal_role_valid")
    for key, entry in committed(tag_files.RECIPE_TAGS, "recipes").items():
        # Only tag fields: allergen, halal and diet labels are never estimated or written from here.
        assert set(entry) == set(adapters), key
        for field, adapter in adapters.items():
            adapter.validate_python(entry[field], strict=True)
        assert entry["meal_role"] is None or entry["meal_role"] in allowed_roles
        assert set(entry["estimated"]) == {field for field in tag_files.RECIPE_TAG_FIELDS if entry[field] is not None}
        assert entry["contains_staple"] == (
            None if entry["meal_role"] is None else entry["meal_role"] in {"one_bowl", "staple"}
        )
    for name, entry in committed(tag_files.INGREDIENT_TAGS, "ingredients").items():
        assert isinstance(entry["perishable"], bool) and isinstance(entry["basic_seasoning"], bool), name
        assert entry["food_group"] is None or isinstance(entry["food_group"], str)


def test_the_vegetable_role_agrees_with_the_planners_vegetable_led_rule() -> None:
    entries = committed(tag_files.RECIPE_TAGS, "recipes")
    for key, entry in entries.items():
        if entry["meal_role"] == "vegetable":
            assert dish_vegetable_led(dishes()[key]), key
    # Every side the planner's rule admits as a vegetable dish is tagged one, unless it is a part of a dish (a batter).
    sides = [
        key
        for key, item in dishes().items()
        if item.course == "side" and dish_vegetable_led(item) and not component(item.title, item.course)
    ]
    assert sides and all(
        entries[key]["meal_role"] == "vegetable"
        or (
            entries[key]["meal_role"] in {"staple", "one_bowl"}
            and RICE_DISH.search(dishes()[key].title.lower())
            and staple_share(dishes()[key], RICE_GRAINS) >= ONE_BOWL_SHARE
        )
        for key in sides
    )


def test_the_tag_files_are_current_with_the_rules() -> None:
    """A rule-decided value is what the rules give today; re-run `python -m app.data.recipe_tags` after a change."""
    entries = committed(tag_files.RECIPE_TAGS, "recipes")
    stale = []
    for key, item in dishes().items():
        found = rule_tags(item)
        for field, estimate in entries[key]["estimated"].items():
            if estimate["method"] == "rule" and found.values[field] != entries[key][field]:
                stale.append((key, field))
            sweet = field == "protein_sources" and entries[key]["meal_role"] in {"dessert", "drink", "sauce"}
            if (
                estimate["method"] == "llm"
                and estimate["reviewed"]
                and field not in {"contains_staple", *found.open}
                and not sweet
            ):
                stale.append((key, field))
    assert not stale, stale[:10]
    assert committed(tag_files.INGREDIENT_TAGS, "ingredients") == ingredient_entries()


# --- the importers' overlay --------------------------------------------------------------------------------

SAMPLE = 25


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def release(tmp_path: Path) -> Path:
    for name in ("release_manifest.json", "ingredients.jsonl"):
        shutil.copy(release_dir() / name, tmp_path / name)
    with (release_dir() / "recipes.jsonl").open(encoding="utf-8") as handle:
        lines = [next(handle) for _ in range(SAMPLE)]
    (tmp_path / "recipes.jsonl").write_text("".join(lines), encoding="utf-8")
    return tmp_path


def _curated(session: Session) -> None:
    data = repository_root() / "data"
    import_catalog(session, load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json"))


def test_the_importers_copy_the_tag_files_onto_the_rows(session: Session, release: Path) -> None:
    _curated(session)
    import_release_v2(session, release)
    entries = committed(tag_files.RECIPE_TAGS, "recipes")
    recipes = session.scalars(select(Recipe)).all()
    assert len(recipes) == 30 + SAMPLE
    for recipe in recipes:
        entry = entries[recipe.external_id or recipe.slug]
        for field in tag_files.RECIPE_TAG_FIELDS:
            assert getattr(recipe, field) == entry[field], (recipe.slug, field)
        assert recipe.estimated == entry["estimated"]
        assert recipe.halal_status is None and recipe.unknown_safety is None
    ingredients = committed(tag_files.INGREDIENT_TAGS, "ingredients")
    rows = session.scalars(select(Ingredient)).all()
    assert rows
    for row in rows:
        entry = ingredients[row.normalized_name]
        assert (row.food_group, row.perishable, row.basic_seasoning) == (
            entry["food_group"],
            entry["perishable"],
            entry["basic_seasoning"],
        )


def test_a_missing_entry_is_null_and_a_runtime_write_wins(
    session: Session, release: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _curated(session)
    spinach = session.scalars(select(Ingredient).where(Ingredient.normalized_name == "baby_spinach")).one()
    # A runtime path (external intake) has already decided this row.
    spinach.provenance = {"origin": "external_intake"}
    spinach.perishable = False
    session.commit()
    monkeypatch.setattr(tag_files, "recipe_tags", dict)
    monkeypatch.setattr(tag_files, "ingredient_tags", dict)
    import_release_v2(session, release)
    _curated(session)

    assert all(recipe.meal_role is None and recipe.estimated is None for recipe in session.scalars(select(Recipe)))
    assert spinach.perishable is False
    # With no tag entry the release's food group still lands; a curated-only id has none.
    tofu = session.scalars(select(Ingredient).where(Ingredient.normalized_name == "tofu")).one()
    assert tofu.food_group == "protein" and tofu.perishable is None


def test_the_tag_files_are_part_of_the_release_digest(release: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert IMPORTER_VERSION == "6"
    before = release_digest(release)
    monkeypatch.setattr(release_v2, "tag_file_bytes", lambda: b"re-tagged")
    assert release_digest(release) != before


def test_a_recipe_tag_a_runtime_path_wrote_survives_a_re_import(session: Session, release: Path) -> None:
    _curated(session)
    import_release_v2(session, release)
    first, second, third = session.scalars(select(Recipe).where(Recipe.external_id.is_not(None))).all()[:3]
    # A person set the role (so it is no longer an estimate), confirmed one, and left the third alone.
    first.meal_role = "snack"
    first.estimated = {name: value for name, value in first.estimated.items() if name != "meal_role"}
    second.estimated = second.estimated | {"flavor_tags": second.estimated["flavor_tags"] | {"reviewed": True}}
    second.flavor_tags = ["spicy"]
    third.meal_role = "drink"
    session.commit()
    import_release_v2(session, release, force=True)

    entries = committed(tag_files.RECIPE_TAGS, "recipes")
    assert first.meal_role == "snack" and "meal_role" not in first.estimated
    assert second.flavor_tags == ["spicy"] and second.estimated["flavor_tags"]["reviewed"] is True
    # A value still marked as the tag file's own estimate is the tag file's to change.
    assert third.meal_role == entries[third.external_id]["meal_role"]
    assert first.cooking_methods == entries[first.external_id]["cooking_methods"]


def test_accepting_a_batch_marks_its_model_values_reviewed_and_a_re_run_keeps_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.data import recipe_tags

    target = tmp_path / tag_files.RECIPE_TAGS
    target.parent.mkdir(parents=True)
    shutil.copy(repository_root() / tag_files.RECIPE_TAGS, target)
    monkeypatch.setattr(recipe_tags, "repository_root", lambda: tmp_path)
    before = json.loads(target.read_text(encoding="utf-8"))
    model = sum(e["method"] == "llm" for entry in before["recipes"].values() for e in entry["estimated"].values())
    assert model and recipe_tags.accept_batch("recipe-tags-v1/other") == 0

    assert recipe_tags.accept_batch(recipe_tags.LLM_BATCH) == model
    after = json.loads(target.read_text(encoding="utf-8"))
    assert {k: v for k, v in after.items() if k != "recipes"} == {k: v for k, v in before.items() if k != "recipes"}
    for key, entry in after["recipes"].items():
        for name, estimate in entry["estimated"].items():
            assert estimate["reviewed"] is (estimate["method"] == "llm"), (key, name)
            assert entry[name] == before["recipes"][key][name]
    assert recipe_tags.accept_batch(recipe_tags.LLM_BATCH) == 0

    # A re-run keeps an accepted value reviewed while it is unchanged, and a changed one goes back to review.
    key, entry = next((k, e) for k, e in after["recipes"].items() if e["estimated"]["meal_role"]["method"] == "llm")
    tags = recipe_tags.Tags(values={name: entry[name] for name in tag_files.RECIPE_TAG_FIELDS})
    tags.methods = {name: e["method"] for name, e in entry["estimated"].items()}
    assert recipe_tags.recipe_entry(tags, entry)["estimated"]["meal_role"]["reviewed"] is True
    tags.values["meal_role"] = "snack" if entry["meal_role"] != "snack" else "dessert"
    assert recipe_tags.recipe_entry(tags, entry)["estimated"]["meal_role"]["reviewed"] is False
