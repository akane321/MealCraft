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
    Dish,
    Line,
    catalog_ingredients,
    curated_dishes,
    dish_vegetable_led,
    ingredient_entries,
    release_dishes,
    rule_tags,
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
    assert bacon.values["protein_sources"] == ["pork"]


def test_a_stock_is_not_the_soups_protein_and_a_noodle_soup_is_one_bowl() -> None:
    soup = tags("Carrot Soup", "soup", [("chicken_broth", 1000), ("carrot", 300)], "Simmer, then blend until smooth.")
    assert soup["meal_role"] == "soup"
    assert soup["protein_sources"] == []
    assert soup["equipment"] == [["blender"]]
    pho = tags("Beef Pho", "soup", [("rice_noodles", 200), ("beef", 250), ("beef_broth", 1500), ("bean_sprouts", 100)])
    assert pho["meal_role"] == "one_bowl"
    assert pho["protein_sources"] == ["beef"]


def test_baked_goods_go_by_title_and_sugar_and_a_cakes_eggs_are_not_protein() -> None:
    bread = tags("Classic Focaccia", "baked_good", [("bread_flour", 500), ("olive_oil", 50), ("yeast", 7)], sugar_g=1.0)
    assert bread["meal_role"] == "staple"
    cake = tags("Chocolate Cake", "baked_good", [("flour", 250), ("sugar", 200), ("egg", 200)], sugar_g=30.0)
    assert cake["meal_role"] == "dessert"
    assert cake["protein_sources"] == []


def test_minor_protein_lines_are_not_the_main_protein_and_poultry_counts_as_chicken() -> None:
    found = tags("Turkey Meatloaf", "main", [("turkey", 900), ("egg", 50), ("breadcrumbs", 60), ("onion", 100)])
    assert found["protein_sources"] == ["chicken"]
    goat = tags("Goat Curry", "main", [("goat", 800), ("potato", 300), ("curry_powder", 10)])
    assert goat["protein_sources"] == ["lamb"]


def test_meat_the_lines_do_not_name_is_left_to_the_model() -> None:
    # A title naming meat that no line holds: the release lost the line.
    lost = rule_tags(dish("Mutton Biryani", "main", [("yogurt", 245), ("anise", 1.4), ("cumin", 1.1)]))
    assert lost.values["protein_sources"] is None
    assert "protein_sources" in lost.open
    game = rule_tags(dish("Braised Rabbit", "main", [("rabbit", 900), ("carrot", 200)]))
    assert game.values["protein_sources"] is None
    assert game.values["meal_role"] == "protein_main"


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
    # Every side the planner's rule admits as a vegetable dish is tagged one.
    sides = [key for key, item in dishes().items() if item.course == "side" and dish_vegetable_led(item)]
    assert sides and all(entries[key]["meal_role"] == "vegetable" for key in sides)


def test_the_tag_files_are_current_with_the_rules() -> None:
    """A rule-decided value is what the rules give today; re-run `python -m app.data.recipe_tags` after a change."""
    entries = committed(tag_files.RECIPE_TAGS, "recipes")
    stale = []
    for key, item in dishes().items():
        found = rule_tags(item)
        for field, estimate in entries[key]["estimated"].items():
            if estimate["method"] == "rule" and found.values[field] != entries[key][field]:
                stale.append((key, field))
            if estimate["method"] == "llm" and field not in {"contains_staple", *found.open}:
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
