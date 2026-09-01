import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.data.catalog import Catalog, import_catalog, load_catalog
from app.db.base import Base
from app.evaluation.runner import evaluate
from app.models.recipe import Ingredient, Recipe

ROOT = Path("/app") if Path("/app/data").exists() else Path(__file__).resolve().parents[2]
INGREDIENTS = ROOT / "data/ingredients/ingredients.json"
RECIPES = ROOT / "data/recipes/recipes.json"
SCENARIOS = ROOT / "data/evaluation/scenarios.json"
FIXTURES = ROOT / "data/fixtures/fairprice-products.json"


def test_reference_catalog_is_complete_and_valid() -> None:
    catalog = load_catalog(INGREDIENTS, RECIPES)

    assert len(catalog.recipes) >= 30
    assert len(catalog.ingredients) >= 30
    assert all(recipe.nutrition.calories_kcal > 0 for recipe in catalog.recipes)
    assert all(len(recipe.steps) >= 2 for recipe in catalog.recipes)


def test_catalog_rejects_unknown_ingredient() -> None:
    ingredients = json.loads(INGREDIENTS.read_text(encoding="utf-8"))
    recipes = json.loads(RECIPES.read_text(encoding="utf-8"))
    recipes[0]["ingredients"][0]["ingredient"] = "not_in_dictionary"

    with pytest.raises(ValidationError, match="unknown ingredients"):
        Catalog.model_validate({"ingredients": ingredients, "recipes": recipes})


def test_catalog_import_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    catalog = load_catalog(INGREDIENTS, RECIPES)

    with Session(engine) as session:
        import_catalog(session, catalog)
        import_catalog(session, catalog)
        assert session.scalar(select(func.count()).select_from(Recipe)) == len(catalog.recipes)
        assert session.scalar(select(func.count()).select_from(Ingredient)) == len(catalog.ingredients)


def test_mvp_evaluation_quality_gates_pass() -> None:
    report = evaluate(
        ingredient_path=INGREDIENTS,
        recipe_path=RECIPES,
        scenario_path=SCENARIOS,
        fixture_path=FIXTURES,
    )

    assert report["passed"], report
