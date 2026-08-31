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


def test_recommendations_enforce_budget_with_fixture_product_costs(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/recommendations/recipes",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "budget_per_meal_sgd": 4.3,
            "pricing_mode": "fixture",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["recipe"]["slug"] for item in payload["recommendations"]] == ["tofu-soba"]
    assert payload["recommendations"][0]["grocery_estimate"]["complete"] is True
    assert payload["recommendations"][0]["grocery_estimate"]["within_budget"] is True
    assert payload["excluded"] == [
        {
            "id": 1,
            "slug": "lemon-chicken",
            "title": "Lemon Chicken",
            "reasons": ["Estimated ingredient-use cost S$4.60 is above the S$4.30 meal budget."],
        }
    ]
    assert payload["warnings"] == [
        "Stable fixture prices are shown for reproducible planning; select live pricing to query FairPrice."
    ]


def test_known_pantry_quantity_is_deducted_but_unknown_quantity_is_not(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/recommendations/recipes",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 35,
            "available_ingredients": [
                {"normalized_name": "chicken_breast", "quantity": 300, "unit": "g"},
                {"normalized_name": "lemon", "quantity": None, "unit": None},
            ],
        },
    )

    assert response.status_code == 200
    estimate = response.json()["recommendations"][0]["grocery_estimate"]
    chicken, lemon = estimate["items"]
    assert chicken["pantry_deduction"] == 300
    assert chicken["packages_required"] == 0
    assert lemon["pantry_deduction"] == 0
    assert lemon["packages_required"] == 1


def test_product_search_endpoint_returns_stable_fixture_products(recipe_client: TestClient) -> None:
    response = recipe_client.get("/api/products/search", params={"q": "brown rice", "live": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_used"] == "fixture"
    assert payload["fallback_used"] is False
    assert payload["items"][0]["external_id"] == "fixture-brown-rice-1kg"


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


def test_weekly_plan_is_persisted_without_consecutive_repeats(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-01",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "weekly_budget_sgd": 40,
            "pricing_mode": "fixture",
            "available_ingredients": [
                {"normalized_name": "chicken_breast", "quantity": 300, "unit": "g"},
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["start_date"] == "2026-09-01"
    assert payload["end_date"] == "2026-09-07"
    assert len(payload["days"]) == 7
    slugs = [day["recipe"]["slug"] for day in payload["days"]]
    assert all(current != following for current, following in zip(slugs, slugs[1:], strict=False))
    assert payload["nutrition_summary_per_person"]["calories_kcal"] > 3000
    assert payload["grocery_estimate"]["complete"] is True

    chicken = next(item for item in payload["grocery_estimate"]["items"] if item["ingredient_name"] == "chicken_breast")
    assert chicken["required_quantity"] > 300
    assert chicken["pantry_deduction"] == 300

    stored = recipe_client.get(f"/api/plans/{payload['id']}")
    assert stored.status_code == 200
    assert [day["recipe"]["slug"] for day in stored.json()["days"]] == slugs
    assert stored.json()["grocery_estimate"]["purchase_total_sgd"] == payload["grocery_estimate"]["purchase_total_sgd"]

    collection = recipe_client.get("/api/plans")
    assert collection.status_code == 200
    assert collection.json()["items"][0]["id"] == payload["id"]


def test_weekly_plan_respects_allergen_filter_and_explains_unavoidable_repeat(
    recipe_client: TestClient,
) -> None:
    response = recipe_client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-08",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "allergens": ["soy"],
            "pricing_mode": "fixture",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert {day["recipe"]["slug"] for day in payload["days"]} == {"lemon-chicken"}
    assert any("consecutive repetition could not be avoided" in warning for warning in payload["warnings"])
    assert any("contains 1 recipe" in warning for warning in payload["warnings"])


def test_weekly_plan_returns_422_when_no_recipe_meets_hard_constraints(recipe_client: TestClient) -> None:
    response = recipe_client.post(
        "/api/plans/generate",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 20,
            "pricing_mode": "fixture",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "No recipes satisfy the supplied hard constraints."}
