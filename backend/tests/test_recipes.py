from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep


@pytest.fixture
def recipe_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        chicken = Ingredient(normalized_name="chicken_breast", display_name="Chicken breast")
        lemon = Ingredient(normalized_name="lemon", display_name="Lemon")
        recipe = Recipe(
            slug="lemon-chicken",
            title="Lemon Chicken",
            description="A simple high-protein main meal.",
            cuisine="Mediterranean-inspired",
            meal_type="main",
            servings=2,
            prep_time_minutes=10,
            cook_time_minutes=20,
            dietary_tags=["high-protein"],
            nutrition=RecipeNutrition(
                calories_kcal=Decimal("480"),
                protein_g=Decimal("42"),
                carbohydrate_g=Decimal("36"),
                fat_g=Decimal("18"),
                sodium_mg=Decimal("590"),
                sugar_g=Decimal("5"),
            ),
            recipe_ingredients=[
                RecipeIngredient(ingredient=chicken, quantity=Decimal("300"), unit="g", sort_order=1),
                RecipeIngredient(ingredient=lemon, quantity=Decimal("1"), unit="whole", sort_order=2),
            ],
            steps=[RecipeStep(step_number=1, instruction="Cook the chicken and finish with lemon.")],
        )
        tofu = Ingredient(normalized_name="firm_tofu", display_name="Firm tofu", allergen="soy")
        soba = Ingredient(normalized_name="soba_noodle", display_name="Soba noodles", allergen="gluten")
        tofu_recipe = Recipe(
            slug="tofu-soba",
            title="Tofu Soba",
            description="A vegetarian noodle main meal.",
            cuisine="Japanese-inspired",
            meal_type="main",
            servings=2,
            prep_time_minutes=15,
            cook_time_minutes=25,
            dietary_tags=["vegetarian", "dairy-free"],
            nutrition=RecipeNutrition(
                calories_kcal=Decimal("510"),
                protein_g=Decimal("25"),
                carbohydrate_g=Decimal("64"),
                fat_g=Decimal("18"),
                sodium_mg=Decimal("680"),
                sugar_g=Decimal("9"),
            ),
            recipe_ingredients=[
                RecipeIngredient(ingredient=tofu, quantity=Decimal("300"), unit="g", sort_order=1),
                RecipeIngredient(ingredient=soba, quantity=Decimal("160"), unit="g", sort_order=2),
            ],
            steps=[RecipeStep(step_number=1, instruction="Cook the tofu and soba.")],
        )
        session.add_all([recipe, tofu_recipe])
        session.commit()

    def override_database() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_list_recipes_returns_cursor_collection(recipe_client: TestClient) -> None:
    response = recipe_client.get("/api/recipes", params={"limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["next_cursor"] is None
    assert len(payload["items"]) == 2
    assert payload["items"][0]["slug"] == "lemon-chicken"
    assert payload["items"][0]["total_time_minutes"] == 30
    assert payload["items"][0]["nutrition"]["sodium_mg"] == 590.0


def test_get_recipe_returns_ingredients_and_steps(recipe_client: TestClient) -> None:
    response = recipe_client.get("/api/recipes/lemon-chicken")

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Lemon Chicken"
    assert payload["ingredients"][0] == {
        "name": "Chicken breast",
        "normalized_name": "chicken_breast",
        "quantity": 300.0,
        "unit": "g",
        "preparation": None,
        "allergen": None,
    }
    assert payload["steps"] == [{"step_number": 1, "instruction": "Cook the chicken and finish with lemon."}]


def test_get_recipe_returns_not_found(recipe_client: TestClient) -> None:
    response = recipe_client.get("/api/recipes/not-a-recipe")

    assert response.status_code == 404
    assert response.json() == {"detail": "Recipe not found"}


def test_recommendations_apply_hard_filters_and_return_score_reasons(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/recommendations/recipes",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 45,
            "allergens": ["soy"],
            "health_preferences": ["low-sodium"],
            "nutrition_targets": {"calories_kcal": 500, "protein_g": 40},
            "available_ingredients": [
                {"normalized_name": "lemon", "quantity": None, "unit": None},
                {"normalized_name": "chicken_breast", "quantity": 150, "unit": "g"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["recipe"]["slug"] for item in payload["recommendations"]] == ["lemon-chicken"]
    assert payload["recommendations"][0]["score_breakdown"]["nutrition"] is not None
    assert payload["recommendations"][0]["score_breakdown"]["pantry"] > 0
    assert any("flexible 700 mg" in reason for reason in payload["recommendations"][0]["reasons"])
    assert payload["excluded"][0]["slug"] == "tofu-soba"
    assert payload["excluded"][0]["reasons"] == ["Contains selected allergen: soy."]


def test_recommendations_explain_deferred_budget_scoring(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/recommendations/recipes",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "budget_per_meal_sgd": 8,
        },
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == [
        "Budget was recorded but is not scored until live FairPrice product pricing is connected."
    ]


def test_recommendation_rejects_known_quantity_without_unit(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/recommendations/recipes",
        json={
            "available_ingredients": [
                {"normalized_name": "lemon", "quantity": 1, "unit": None},
            ]
        },
    )

    assert response.status_code == 422
