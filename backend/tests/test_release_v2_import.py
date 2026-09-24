import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import RELEASE_VERSION, import_release_v2, map_allergens, release_dir
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
    """The first real release recipes plus one with a single ingredient line, which must be skipped."""
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


def _release_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Recipe).where(Recipe.release_version == RELEASE_VERSION))


def test_release_is_added_beside_the_curated_catalog(session: Session, release: Path) -> None:
    curated_before = _curated(session)
    report = import_release_v2(session, release)

    assert report.recipes_skipped == ["RCP2_SHORT"]
    assert report.recipes_imported == SAMPLE
    assert _curated(session) == curated_before
    imported = session.scalars(select(Recipe).where(Recipe.release_version == RELEASE_VERSION)).all()
    assert len(imported) == SAMPLE
    assert all(recipe.slug.startswith("v2-") and recipe.external_id.startswith("RCP2_") for recipe in imported)
    assert all(set(recipe.allergens) <= checked_allergens() for recipe in imported)
    assert all(recipe.nutrition is not None and recipe.steps for recipe in imported)
    lines = session.scalars(
        select(RecipeIngredient).join(Recipe).where(Recipe.release_version == RELEASE_VERSION)
    ).all()
    assert lines and all(line.quantity == line.grams and line.original_text for line in lines)
    assert all(set(row.allergens) <= checked_allergens() for row in session.scalars(select(Ingredient)))
    assert session.get(CatalogImport, RELEASE_VERSION).recipe_count == SAMPLE


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
    assert _release_count(session) == SAMPLE - 1
    assert session.scalar(select(Recipe).where(Recipe.external_id == dropped["recipe_id"])) is None


def test_an_earlier_release_is_upgraded_in_place(session: Session, release: Path) -> None:
    import_release_v2(session, release)
    ids_before = dict(
        session.execute(select(Recipe.external_id, Recipe.id).where(Recipe.release_version.is_not(None))).all()
    )
    # Pretend the rows came from release v2, as a database imported before v2.1 holds them.
    session.execute(update(Recipe).where(Recipe.release_version.is_not(None)).values(release_version="v2"))
    session.execute(delete(CatalogImport))
    session.commit()

    import_release_v2(session, release)

    ids_after = dict(
        session.execute(select(Recipe.external_id, Recipe.id).where(Recipe.release_version.is_not(None))).all()
    )
    assert ids_after == ids_before
    assert _release_count(session) == SAMPLE


def test_release_allergen_names_map_to_the_runtime_vocabulary() -> None:
    assert map_allergens(["milk", "eggs", "molluscs", "crustaceans", "gluten_candidate", "sulfites"]) == [
        "dairy",
        "egg",
        "gluten",
        "shellfish",
    ]
    with pytest.raises(ValueError):
        map_allergens(["lupin"])


def test_a_combined_ingredient_carries_its_options(session: Session, release: Path) -> None:
    import_release_v2(session, release)

    def row(name: str) -> Ingredient:
        return session.scalars(select(Ingredient).where(Ingredient.normalized_name == name)).one()

    beef_or_turkey = row("beef_or_turkey").alternatives
    assert [option["normalized_name"] for option in beef_or_turkey] == ["ground_beef", "turkey"]
    butter = row("butter_or_margarine").alternatives[0]
    # Copied from the imported option row, so its allergens are in the runtime vocabulary.
    assert butter == {"normalized_name": "butter", "display_name": row("butter").display_name, "allergens": ["dairy"]}
    assert row("butter").alternatives is None


def _release_with(tmp_path: Path, recipe_ids: set[str], edit=None) -> Path:
    source = release_dir()
    for name in ("release_manifest.json", "ingredients.jsonl"):
        shutil.copy(source / name, tmp_path / name)
    with (source / "recipes.jsonl").open(encoding="utf-8") as handle:
        records = [record for record in map(json.loads, handle) if record["recipe_id"] in recipe_ids]
    _write_recipes(tmp_path, [edit(record) if edit else record for record in records])
    return tmp_path


POMELO_RECIPE = "RCP2_8559F3848205"


def test_a_line_the_release_mapped_wrongly_is_corrected(session: Session, tmp_path: Path) -> None:
    import_release_v2(session, _release_with(tmp_path, {POMELO_RECIPE}))

    line = session.scalars(
        select(RecipeIngredient)
        .join(Recipe)
        .where(Recipe.external_id == POMELO_RECIPE, RecipeIngredient.original_text == "1 ounce pomelo juice")
    ).one()
    assert line.ingredient.normalized_name == "pomelo_juice"
    assert line.ingredient.display_name == "pomelo juice"
    # Pomelo juice has no FairPrice mapping, so priced planning leaves the recipe out
    # instead of buying grapefruit juice for it.
    from app.planning.grocery_estimator import priceable_ingredients

    assert "pomelo_juice" not in priceable_ingredients()


def test_a_correction_that_no_longer_matches_the_release_stops_the_import(session: Session, tmp_path: Path) -> None:
    def reworded(record: dict) -> dict:
        for line in record["ingredients"]:
            if line["original_text"] == "1 ounce pomelo juice":
                line["original_text"] = "30 ml pomelo juice"
        return record

    with pytest.raises(ValueError, match="no longer matches the release"):
        import_release_v2(session, _release_with(tmp_path, {POMELO_RECIPE}, reworded))
