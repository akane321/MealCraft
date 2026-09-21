from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.db.base import Base
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning.grocery_estimator import GroceryEstimator
from app.repositories.recipe import RecipeRepository
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


def test_recommendations_keep_the_best_scored_up_to_the_candidate_limit(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recommendation_module, "CANDIDATE_LIMIT", 3)
    service = RecipeRecommendationService(RecipeRepository(session), GroceryEstimator(CountingProducts()))
    result = service.recommend(RecipeRecommendationRequest(household_size=2, max_cooking_time_minutes=60))
    scores = [item.total_score for item in result.recommendations]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True)
