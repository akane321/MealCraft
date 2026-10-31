import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data import release_v2
from app.data.catalog import import_catalog, load_catalog
from app.data.halal import halal_labels, recipe_halal_status
from app.data.release_v2 import import_release_v2, release_dir
from app.db.base import Base
from app.models.recipe import Ingredient, Recipe

SAMPLE = 60


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
    source = release_dir()
    for name in ("release_manifest.json", "ingredients.jsonl"):
        shutil.copy(source / name, tmp_path / name)
    with (source / "recipes.jsonl").open(encoding="utf-8") as handle:
        records = [json.loads(next(handle)) for _ in range(SAMPLE)]
    (tmp_path / "recipes.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return tmp_path


def _statuses(session: Session) -> dict[str, str | None]:
    return {recipe.slug: recipe.halal_status for recipe in session.scalars(select(Recipe))}


def test_curated_recipes_and_ingredients_get_a_status(session: Session) -> None:
    statuses = _statuses(session)
    assert statuses["lemon-herb-chicken-rice-bowl"] == "needs_certification"
    assert statuses["tofu-vegetable-soba"] == statuses["salmon-quinoa-bowl"] == "halal"
    assert set(statuses.values()) <= {"halal", "needs_certification"}  # the curated catalog has no pork or alcohol
    ingredients = {row.normalized_name: row.halal_status for row in session.scalars(select(Ingredient))}
    assert ingredients["chicken_breast"] == "halal" and ingredients["broccoli"] == "halal"
    assert None not in ingredients.values()


def test_release_recipes_get_the_status_of_their_lines(session: Session, release: Path) -> None:
    import_release_v2(session, release)
    recipes = session.scalars(select(Recipe).where(Recipe.release_version.is_not(None))).all()
    assert len(recipes) == SAMPLE and all(recipe.halal_status for recipe in recipes)
    for recipe in recipes:
        names = [line.ingredient.normalized_name for line in recipe.recipe_ingredients]
        assert recipe.halal_status == recipe_halal_status(names)
    assert {recipe.halal_status for recipe in recipes} - {"halal"}  # the sample is not all plain
    for row in session.scalars(select(Ingredient).where(Ingredient.provenance.is_(None))):
        label = halal_labels().get(row.normalized_name)
        assert row.halal_status == (label["status"] if label else "uncertain")


def test_an_existing_row_gets_its_status_on_the_next_import(session: Session, release: Path) -> None:
    import_release_v2(session, release)
    session.query(Recipe).update({Recipe.halal_status: None})
    session.query(Ingredient).update({Ingredient.halal_status: None})
    session.commit()
    import_release_v2(session, release, force=True)
    assert all(
        recipe.halal_status for recipe in session.scalars(select(Recipe).where(Recipe.release_version.is_not(None)))
    )
    # Only the curated-only ingredients are outside the release, so only the curated import sets them.
    in_release = {
        release_v2.normalized_name(json.loads(line)["ingredient_id"])
        for line in (release / "ingredients.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert all(row.halal_status for row in session.scalars(select(Ingredient)) if row.normalized_name in in_release)


def test_a_relabelled_catalog_reimports(session: Session, release: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = release_v2.release_digest(release)
    monkeypatch.setattr(release_v2, "halal_file_bytes", lambda: b"changed labels")
    assert release_v2.release_digest(release) != before
