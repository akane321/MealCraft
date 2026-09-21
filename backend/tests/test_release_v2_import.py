import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import (
    import_release_v2,
    map_allergens,
    names_meat,
    recipe_allergens,
    release_dir,
    unlisted_allergens,
)
from app.db.base import Base
from app.models.recipe import CatalogImport, Ingredient, Recipe, RecipeIngredient

SAMPLE = 25


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        data = repository_root() / "data"
        import_catalog(session, load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json"))
        yield session


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """The first real v2 recipes plus one with a single ingredient line, which must be skipped."""
    source = release_dir()
    for name in ("release_manifest.json", "ingredients.jsonl"):
        shutil.copy(source / name, tmp_path / name)
    with (source / "recipes.jsonl").open(encoding="utf-8") as handle:
        records = [json.loads(next(handle)) for _ in range(SAMPLE)]
    short = dict(records[0], recipe_id="RCP2_SHORT", ingredients=records[0]["ingredients"][:1])
    _write_recipes(tmp_path, [*records, short])
    return tmp_path


def _write_recipes(directory: Path, records: list[dict]) -> None:
    lines = [json.dumps(record) for record in records]
    (directory / "recipes.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _curated(session: Session) -> list[str]:
    return list(session.scalars(select(Recipe.slug).where(Recipe.release_version.is_(None)).order_by(Recipe.slug)))


def test_release_is_added_beside_the_curated_catalog(session: Session, release: Path) -> None:
    curated_before = _curated(session)
    report = import_release_v2(session, release)

    assert report.recipes_skipped == ["RCP2_SHORT"]
    # Two of the first real recipes ask for bread or pasta that no line lists.
    assert report.recipes_incomplete == {"RCP2_001FC1CA72F4": ["gluten"], "RCP2_002B2E45CF31": ["gluten"]}
    assert report.recipes_imported == SAMPLE - 2
    assert _curated(session) == curated_before
    imported = session.scalars(select(Recipe).where(Recipe.release_version == "v2")).all()
    assert len(imported) == SAMPLE - 2
    assert all(recipe.slug.startswith("v2-") and recipe.external_id.startswith("RCP2_") for recipe in imported)
    assert all(set(recipe.allergens) <= checked_allergens() for recipe in imported)
    assert all(recipe.nutrition is not None and recipe.steps for recipe in imported)
    lines = session.scalars(select(RecipeIngredient).join(Recipe).where(Recipe.release_version == "v2")).all()
    assert lines and all(line.quantity == line.grams and line.original_text for line in lines)
    assert all(set(row.allergens) <= checked_allergens() for row in session.scalars(select(Ingredient)))
    assert session.get(CatalogImport, "v2").recipe_count == SAMPLE - 2
    assert report.meat_free_tags_removed == ["RCP2_0044D5F2C74C"]
    tags = session.scalar(select(Recipe.dietary_tags).where(Recipe.external_id == "RCP2_0044D5F2C74C"))
    assert not {"vegetarian", "vegan"} & set(tags)


def test_same_release_is_skipped_and_a_changed_one_drops_stale_recipes(session: Session, release: Path) -> None:
    import_release_v2(session, release)
    assert import_release_v2(session, release).skipped_unchanged

    with (release / "recipes.jsonl").open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    dropped = records[-2]
    _write_recipes(release, [record for record in records if record is not dropped])
    report = import_release_v2(session, release)

    assert not report.skipped_unchanged
    assert report.recipes_removed == 1
    count = session.scalar(select(func.count()).select_from(Recipe).where(Recipe.release_version == "v2"))
    assert count == SAMPLE - 3
    assert session.scalar(select(Recipe).where(Recipe.external_id == dropped["recipe_id"])) is None


def test_release_allergen_names_map_to_the_runtime_vocabulary() -> None:
    assert map_allergens(["milk", "eggs", "molluscs", "crustaceans", "gluten_candidate", "sulfites"]) == [
        "dairy",
        "egg",
        "gluten",
        "shellfish",
    ]
    with pytest.raises(ValueError):
        map_allergens(["lupin"])


def _record(title: str, steps: list[str], lines: list[tuple[str, list[str]]], tags: list[str] | None = None) -> dict:
    return {
        "title": title,
        "instructions": [{"step_number": i, "text": text} for i, text in enumerate(steps, start=1)],
        "ingredients": [{"canonical_ingredient_id": iid, "allergens": allergens} for iid, allergens in lines],
        "allergens": sorted({a for _, allergens in lines for a in allergens}),
        "dietary_tags": tags or [],
    }


def test_a_dish_whose_list_misses_what_its_text_names_is_caught() -> None:
    quiche = _record(
        "Crab Meat Quiche",
        ["Make the crust.", "Beat the eggs with the milk, fold in the crab and bake."],
        [("ING_FLOUR", ["gluten"]), ("ING_SHORTENING", []), ("ING_SALT", [])],
    )
    assert unlisted_allergens(quiche, recipe_allergens(quiche)) == ["dairy", "egg", "shellfish"]

    stew = _record("Coconut Curry", ["Stir in the coconut milk and cream the paste."], [("ING_COCONUT_MILK", [])])
    assert unlisted_allergens(stew, recipe_allergens(stew)) == []


def test_stricter_allergens_cover_what_the_usual_product_carries() -> None:
    burrito = _record("Bean Burrito", ["Fill the tortillas."], [("ING_TORTILLA", []), ("ING_BUTTER_OR_MARGARINE", [])])
    assert recipe_allergens(burrito) == ["dairy", "gluten"]
    assert unlisted_allergens(burrito, recipe_allergens(burrito)) == []


def test_meat_in_the_text_is_what_strips_meat_free_tags() -> None:
    assert names_meat(_record("Fried Rice", ["Serve with chicken adobo."], [], ["vegetarian"]))
    assert not names_meat(_record("Butternut Soup", ["Blend the squash."], [], ["vegan"]))
