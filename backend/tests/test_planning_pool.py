from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.planning_pool import COURSE, INCOMPLETE, NO_ROLE, UNPRICED, WAITS, WITHDRAWN, markdown, report
from app.db.base import Base
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning.grocery_estimator import priceable_ingredients
from app.repositories.recipe import POOL_COURSES, RecipeRepository, withdrawn_slugs


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        data = repository_root() / "data"
        import_catalog(session, load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json"))
        session.add_all(
            Ingredient(normalized_name=name, display_name=name, allergens=[]) for name in ("test_spice", "test_herb")
        )
        session.flush()
        items = {row.normalized_name: row for row in session.scalars(select(Ingredient))}
        chicken, rice = items["chicken_breast"], items["brown_rice"]
        _release(session, "priced", "main", [chicken, rice], role="protein_main", cuisine="malaysian_singaporean")
        _release(session, "untagged", "main", [chicken, rice], cuisine="malaysian_singaporean")
        _release(session, "porridge", "breakfast", [rice], role="breakfast")
        _release(session, "waits", "main", [chicken, rice], role="protein_main", model=True)
        _release(session, "dessert", "dessert", [rice], role="dessert")
        _release(session, "spiced", "main", [chicken, items["test_spice"]], role="protein_main")
        _release(session, "spiced-herbed", "main", [chicken, items["test_spice"], items["test_herb"]])
        _release(session, "herbed", "side", [rice, items["test_herb"]])
        _release(session, "sauce", "sauce_condiment", [items["test_spice"]])
        _release(session, "withdrawn", "main", [chicken, rice], withdrawn=True)
        _release(session, "thin", "main", [chicken, rice], kcal=60)
        session.commit()
        yield session


def _release(
    session: Session,
    name: str,
    course: str,
    ingredients: list[Ingredient],
    *,
    role: str | None = None,
    model: bool = False,
    withdrawn: bool = False,
    kcal: float = 500,
    cuisine: str = "test",
) -> None:
    estimated = {"meal_role": {"method": "llm", "batch": "recipe-tags-v1/llm", "reviewed": False}} if model else None
    session.add(
        Recipe(
            slug=f"v2-{name}",
            title=name,
            description=name,
            cuisine=cuisine,
            meal_type=course,
            course=course,
            servings=2,
            prep_time_minutes=5,
            cook_time_minutes=5,
            dietary_tags=[],
            release_version="v2",
            external_id=f"RCP2_{name.upper()}",
            meal_role=role,
            protein_sources=["chicken"] if role == "protein_main" else [],
            estimated=estimated,
            withdrawn_at=datetime.now(UTC) if withdrawn else None,
            nutrition=RecipeNutrition(
                calories_kcal=kcal, protein_g=30, carbohydrate_g=50, fat_g=15, sodium_mg=400, sugar_g=5
            ),
            recipe_ingredients=[
                RecipeIngredient(ingredient=item, quantity=100, unit="g", sort_order=index)
                for index, item in enumerate(ingredients, start=1)
            ],
            steps=[RecipeStep(step_number=1, instruction="Cook.")],
        )
    )


def _report(session: Session, *, release_only: bool = False) -> dict:
    recipes = [
        recipe
        for recipe in session.scalars(select(Recipe)).unique().all()
        if not release_only or recipe.release_version is not None
    ]
    return report(recipes, priceable=priceable_ingredients(), withdrawn=frozenset(withdrawn_slugs()))


def test_the_report_pool_is_the_planning_pool(session: Session) -> None:
    result = _report(session)
    pool = RecipeRepository(session)._load_for_planning(session, sorted(POOL_COURSES))
    assert sum(result["pool"].values()) == len(pool)
    assert result["pool"]["release"] == sum(1 for recipe in pool if recipe.release_version is not None)
    assert result["recipes"]["release"] == 11


def test_each_excluded_recipe_counts_once_under_its_first_gate(session: Session) -> None:
    result = _report(session, release_only=True)
    assert result["excluded"]["release"] == {COURSE: 1, UNPRICED: 3, WITHDRAWN: 1, INCOMPLETE: 1}
    assert result["incomplete"] == {"too few kcal for a main": 1}
    assert result["not_usable"] == {WAITS: 1, NO_ROLE: 1, "not a breakfast, lunch or dinner role (dessert)": 1}
    assert result["usable_roles"] == {"breakfast": 1, "protein_main": 1}
    assert result["usable"] == 2
    assert result["usable_by_meal"] == {"lunch or dinner": 1, "breakfast": 1}
    assert result["local"] == {"recipes": 2, "pool": 2, "usable": 1}


def test_unpriced_ingredients_rank_by_use_and_recover_whole_recipes_only(session: Session) -> None:
    priced = _report(session)["unpriced"]
    # The sauce's spice is never counted: its course is excluded first.
    assert priced["ingredients"] == 2
    assert priced["per_recipe"] == {"1": 2, "2": 1}
    assert priced["top"] == [
        {"ingredient": "test_herb", "recipes": 2, "only_missing": 1},
        {"ingredient": "test_spice", "recipes": 2, "only_missing": 1},
    ]
    assert priced["recovered_if_top_priced"] == {"all": 3}


def test_the_markdown_names_its_sources(session: Session) -> None:
    result = _report(session)
    result["sources"] = {
        "release_version": "v2",
        "release_digest": "r",
        "recipe_tags_sha256": "t",
        "priceable_sha256": "p",
    }
    text = markdown(result)
    assert "Release v2 (digest `r`)" in text
    assert "| **In the planning pool** | 5 | 30 |" in text
    meals = result["usable_by_meal"]
    assert f"{meals['lunch or dinner']} a lunch or dinner role and {meals['breakfast']} a breakfast one" in text
    assert "2 recipes, 2 in the planning pool, 1 fill a role" in text
