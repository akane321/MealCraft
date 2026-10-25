from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.db.base import Base
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.repositories.recipe import RecipeRepository, _planning_pool, clear_planning_pool
from app.schemas.recommendation import RecipeRecommendationRequest
from app.services import recommendation as recommendation_module
from app.services.recommendation import RecipeRecommendationService


class CountingProducts:
    def __init__(self) -> None:
        self.searched: list[str] = []

    def search(self, name: str, *, live: bool, limit: int) -> SimpleNamespace:
        self.searched.append(name)
        return SimpleNamespace(warning=None, items=[])


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        data = repository_root() / "data"
        import_catalog(session, load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json"))
        unmapped = Ingredient(normalized_name="unmapped_test_spice", display_name="Unmapped test spice", allergens=[])
        session.add(unmapped)
        session.flush()
        curated = {row.normalized_name: row for row in session.scalars(select(Ingredient))}
        _release(session, "priced", "main", [curated["chicken_breast"], curated["brown_rice"]])
        _release(session, "unpriced", "main", [curated["chicken_breast"], unmapped])
        _release(session, "sauce", "sauce_condiment", [curated["lemon"], curated["brown_rice"]])
        session.commit()
        yield session


def _release(session: Session, name: str, course: str, ingredients: list[Ingredient]) -> None:
    recipe = Recipe(
        slug=f"v2-{name}",
        title=name,
        description=name,
        cuisine="test",
        meal_type=course,
        course=course,
        servings=2,
        prep_time_minutes=5,
        cook_time_minutes=5,
        dietary_tags=[],
        release_version="v2",
        external_id=f"RCP2_{name.upper()}",
        nutrition=RecipeNutrition(
            calories_kcal=500, protein_g=30, carbohydrate_g=50, fat_g=15, sodium_mg=400, sugar_g=5
        ),
        recipe_ingredients=[
            RecipeIngredient(ingredient=item, quantity=100, unit="g", sort_order=index)
            for index, item in enumerate(ingredients, start=1)
        ],
        steps=[RecipeStep(step_number=1, instruction="Cook.")],
    )
    session.add(recipe)


def _slugs(recipes: list[Recipe]) -> set[str]:
    return {recipe.slug for recipe in recipes if recipe.slug.startswith("v2-")}


def test_candidates_cover_the_whole_catalog_but_only_meal_courses(session: Session) -> None:
    repository = RecipeRepository(session)
    everything = repository.list_for_recommendation()
    assert len(everything) == 32
    assert _slugs(everything) == {"v2-priced", "v2-unpriced"}
    assert _slugs(repository.list_for_planning()) == {"v2-priced"}
    assert len(repository.list_for_planning()) == 31
    sauce = session.scalar(select(Recipe.id).where(Recipe.slug == "v2-sauce"))
    assert [recipe.slug for recipe in repository.list_by_ids([sauce])] == ["v2-sauce"]


def test_unmatchable_ingredients_are_never_searched_for_products(session: Session) -> None:
    products = CountingProducts()
    recipe = session.scalar(select(Recipe).where(Recipe.slug == "v2-unpriced"))
    estimate = GroceryEstimator(products).estimate(recipe, RecipeRecommendationRequest(household_size=2))
    assert products.searched == ["Chicken breast"]
    assert estimate.complete is False


def test_nutrition_ranking_observes_visibility_order_and_limits(session: Session) -> None:
    private = session.scalar(select(Recipe).where(Recipe.slug == "v2-unpriced"))
    private.owner_household_id = 7
    private.nutrition.protein_g = 1000
    repository = RecipeRepository(session)

    visible = repository.rank_by_nutrition("protein_g", descending=True, household_id=1, limit=3)
    visible_values = [recipe.nutrition.protein_g for recipe in visible]
    assert "v2-unpriced" not in {recipe.slug for recipe in visible}
    assert visible_values == sorted(visible_values, reverse=True)

    household_recipes = repository.rank_by_nutrition("protein_g", descending=True, household_id=7, limit=1)
    assert household_recipes[0].slug == "v2-unpriced"


def test_recipe_reads_are_scoped_to_shared_and_calling_household(session: Session) -> None:
    own = session.scalar(select(Recipe).where(Recipe.slug == "v2-priced"))
    own.owner_household_id = 7
    other = session.scalar(select(Recipe).where(Recipe.slug == "v2-unpriced"))
    other.owner_household_id = 8
    chicken = session.scalar(select(Ingredient).where(Ingredient.normalized_name == "chicken_breast"))
    _release(session, "shared", "main", [chicken])
    session.flush()

    default = RecipeRepository(session)
    household = RecipeRepository(session, household_id=7)
    assert _slugs(default.list_for_recommendation()) == {"v2-shared"}
    assert _slugs(household.list_for_recommendation()) == {"v2-priced", "v2-shared"}
    assert household.get_by_slug("v2-unpriced") is None
    assert household.list_by_ids([other.id]) == []


def test_global_planning_cache_never_contains_household_recipes(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    clear_planning_pool()
    monkeypatch.setattr(get_settings(), "planning_pool_cache_seconds", 300)
    own = session.scalar(select(Recipe).where(Recipe.slug == "v2-priced"))
    own.owner_household_id = 7
    other = session.scalar(select(Recipe).where(Recipe.slug == "v2-unpriced"))
    other.owner_household_id = 8
    chicken = session.scalar(select(Ingredient).where(Ingredient.normalized_name == "chicken_breast"))
    _release(session, "shared", "main", [chicken])
    session.commit()

    try:
        household_recipes = RecipeRepository(session, household_id=7).list_for_planning()
        cached = _planning_pool[id(session.get_bind())][1]
        assert "v2-priced" in _slugs(household_recipes)
        assert "v2-priced" not in _slugs(cached)
        assert "v2-unpriced" not in _slugs(cached)
    finally:
        clear_planning_pool()


@pytest.mark.parametrize(
    ("metric", "limit"),
    [("fibre_g", 3), ("protein_g", 0), ("protein_g", 11)],
)
def test_nutrition_ranking_rejects_unsupported_metrics_and_limits(session: Session, metric: str, limit: int) -> None:
    with pytest.raises(ValueError):
        RecipeRepository(session).rank_by_nutrition(metric, descending=True, household_id=1, limit=limit)


def test_recommendations_keep_the_best_scored_up_to_the_candidate_limit(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recommendation_module, "CANDIDATE_LIMIT", 3)
    service = RecipeRecommendationService(RecipeRepository(session), GroceryEstimator(CountingProducts()))
    result = service.recommend(RecipeRecommendationRequest(household_size=2, max_cooking_time_minutes=60))
    scores = [item.total_score for item in result.recommendations]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True)


def test_explicit_soft_preferences_use_recipe_nutrition_tags_and_ingredient_weights(session: Session) -> None:
    chicken = session.scalar(select(Ingredient).where(Ingredient.normalized_name == "chicken_breast"))
    spinach = session.scalar(select(Ingredient).where(Ingredient.normalized_name == "baby_spinach"))
    recipe = Recipe(
        slug="v2-preference-candidate",
        title="Preference candidate",
        description="test",
        cuisine="test",
        meal_type="main",
        course="main",
        servings=2,
        prep_time_minutes=5,
        cook_time_minutes=5,
        dietary_tags=[],
        flavor_tags=["fragrant"],
        nutrition=RecipeNutrition(
            calories_kcal=400, protein_g=30, carbohydrate_g=30, fat_g=10, sodium_mg=300, sugar_g=5
        ),
        recipe_ingredients=[
            RecipeIngredient(ingredient=chicken, quantity=100, unit="g", sort_order=1),
            RecipeIngredient(ingredient=spinach, quantity=200, unit="g", sort_order=2),
        ],
    )
    session.add(recipe)
    session.flush()
    request = RecipeRecommendationRequest.model_validate(
        {
            "household_size": 2,
            "planning_preferences": {
                "more_vegetables": True,
                "lighter": True,
                "flavor_boosts": [{"flavor": "fragrant"}],
            },
        }
    )
    reasons: list[str] = []

    score = RecipeRecommendationEngine()._preference_score(recipe, request, reasons)

    assert score is not None and score > 80
    assert any("weighed ingredients" in reason for reason in reasons)
    assert any("sodium and fat" in reason for reason in reasons)
    assert any("flavor tags" in reason for reason in reasons)


def test_every_withdrawn_recipe_says_why() -> None:
    import json

    from app.core.paths import repository_root
    from app.repositories.recipe import withdrawn_slugs

    items = json.loads((repository_root() / "data/recipes/withdrawn.json").read_text(encoding="utf-8"))["recipes"]
    assert withdrawn_slugs() == tuple(item["slug"] for item in items)
    assert all(item["reason"].strip() for item in items)
