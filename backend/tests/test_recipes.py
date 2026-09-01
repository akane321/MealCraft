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


def test_agent_clarifies_unknown_pantry_quantity_then_becomes_ready(
    recipe_client: TestClient,
) -> None:
    response = recipe_client.post(
        "/api/agent/sessions",
        json={
            "message": (
                "Plan for 2 people with S$15 per meal, low sodium and a peanut allergy. I already have chicken breast."
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "collecting"
    assert payload["constraints"]["household_size"] == 2
    assert payload["constraints"]["budget_per_meal_sgd"] == 15
    assert payload["constraints"]["allergens"] == ["peanut"]
    assert payload["constraints"]["health_preferences"] == ["low-sodium"]
    assert payload["constraints"]["available_ingredients"] == [
        {"normalized_name": "chicken_breast", "quantity": None, "unit": None}
    ]
    assert "available_ingredients.chicken_breast.quantity" in payload["missing_fields"]
    assert payload["can_confirm"] is False

    response = recipe_client.post(
        f"/api/agent/sessions/{payload['id']}/messages",
        json={"message": "unknown"},
    )
    assert response.status_code == 200
    ready = response.json()
    assert ready["status"] == "ready"
    assert ready["missing_fields"] == []
    assert ready["can_confirm"] is True


def test_agent_confirmation_calls_weekly_planner_and_persists_plan_link(
    recipe_client: TestClient,
) -> None:
    created = recipe_client.post(
        "/api/agent/sessions",
        json={"message": "Build a weekly plan for 2 people with a S$20 per meal budget."},
    ).json()
    assert created["status"] == "ready"

    response = recipe_client.post(f"/api/agent/sessions/{created['id']}/confirm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["status"] == "planned"
    assert payload["session"]["plan_id"] == payload["plan"]["id"]
    assert len(payload["plan"]["days"]) == 7

    persisted = recipe_client.get(f"/api/agent/sessions/{created['id']}").json()
    assert persisted["status"] == "planned"
    assert persisted["plan_id"] == payload["plan"]["id"]
    assert persisted["messages"][-1]["content"].endswith(f"plan #{payload['plan']['id']}.")


def test_agent_enforces_non_medical_boundary_without_inventing_constraints(
    recipe_client: TestClient,
) -> None:
    response = recipe_client.post(
        "/api/agent/sessions",
        json={"message": "Create a diabetes treatment diet for 2 people."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["constraints"]["health_preferences"] == []
    assert "does not provide disease-specific" in payload["messages"][-1]["content"]


def test_agent_keeps_explicit_exclusions_separate_from_allergens(
    recipe_client: TestClient,
) -> None:
    response = recipe_client.post(
        "/api/agent/sessions",
        json={"message": "Plan for 2 people with no peanuts and no tofu."},
    )

    assert response.status_code == 201
    constraints = response.json()["constraints"]
    assert constraints["allergens"] == []
    assert constraints["excluded_ingredients"] == ["firm_tofu", "peanut"]


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


def test_meal_checkin_is_idempotent_and_dashboard_counts_completed_meals(recipe_client: TestClient) -> None:
    generated = recipe_client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-15",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "pricing_mode": "fixture",
            "nutrition_targets": {"calories_kcal": 500, "protein_g": 35},
        },
    )
    assert generated.status_code == 201
    plan = generated.json()
    first_day, second_day = plan["days"][:2]
    assert first_day["status"] == "planned"
    assert first_day["consumed_at"] is None
    assert first_day["entry_id"] > 0

    completed = recipe_client.patch(
        f"/api/plans/{plan['id']}/entries/{first_day['entry_id']}",
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    completed_day = completed.json()["days"][0]
    assert completed_day["status"] == "completed"
    assert completed_day["consumed_at"] is not None

    repeated = recipe_client.patch(
        f"/api/plans/{plan['id']}/entries/{first_day['entry_id']}",
        json={"status": "completed"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["days"][0]["consumed_at"] == completed_day["consumed_at"]

    skipped = recipe_client.patch(
        f"/api/plans/{plan['id']}/entries/{second_day['entry_id']}",
        json={"status": "skipped"},
    )
    assert skipped.status_code == 200
    assert skipped.json()["days"][1]["consumed_at"] is None

    dashboard = recipe_client.get(f"/api/plans/{plan['id']}/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["status_counts"] == {"planned": 5, "completed": 1, "skipped": 1}
    assert payload["completion_rate"] == 14.3
    assert payload["nutrition_targets"]["calories_kcal"] == 500
    assert payload["completed_nutrition_per_person"] == first_day["nutrition_per_person"]
    assert (
        payload["planned_nutrition_per_person"]["calories_kcal"]
        > payload["completed_nutrition_per_person"]["calories_kcal"]
    )


def test_meal_checkin_rejects_unknown_entry_and_invalid_status(recipe_client: TestClient) -> None:
    generated = recipe_client.post(
        "/api/plans/generate",
        json={
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "pricing_mode": "fixture",
        },
    )
    plan_id = generated.json()["id"]

    missing = recipe_client.patch(
        f"/api/plans/{plan_id}/entries/999999",
        json={"status": "completed"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Meal-plan entry not found"}

    invalid = recipe_client.patch(
        f"/api/plans/{plan_id}/entries/{generated.json()['days'][0]['entry_id']}",
        json={"status": "ate-something-else"},
    )
    assert invalid.status_code == 422


def _generate_replanning_fixture(recipe_client: TestClient, start_date: str) -> dict:
    response = recipe_client.post(
        "/api/plans/generate",
        json={
            "start_date": start_date,
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "weekly_budget_sgd": 60,
            "pricing_mode": "fixture",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_replanning_preview_is_non_mutating_and_confirmation_persists_revision(
    recipe_client: TestClient,
) -> None:
    plan = _generate_replanning_fixture(recipe_client, "2026-09-22")
    target = plan["days"][0]

    preview = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={
            "event_type": "REPLACE_MEAL",
            "entry_id": target["entry_id"],
            "reason": "I need a different dinner.",
        },
    )

    assert preview.status_code == 201
    event = preview.json()
    assert event["status"] == "previewed"
    assert event["base_revision"] == 1
    assert event["before_entry"]["recipe_slug"] == target["recipe"]["slug"]
    assert event["after_entry"]["recipe_slug"] != target["recipe"]["slug"]
    assert event["grocery_delta"]

    unchanged = recipe_client.get(f"/api/plans/{plan['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["days"][0]["recipe"]["slug"] == target["recipe"]["slug"]

    confirmed = recipe_client.post(f"/api/plans/{plan['id']}/replan/{event['id']}/confirm")
    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["event"]["status"] == "applied"
    assert payload["event"]["applied_revision"] == 2
    assert payload["plan"]["revision"] == 2
    assert payload["plan"]["days"][0]["recipe"]["slug"] == event["after_entry"]["recipe_slug"]

    history = recipe_client.get(f"/api/plans/{plan['id']}/events")
    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == event["id"]


def test_replanning_rejects_stale_preview_after_another_change(recipe_client: TestClient) -> None:
    plan = _generate_replanning_fixture(recipe_client, "2026-09-29")
    target = plan["days"][0]
    body = {"event_type": "REPLACE_MEAL", "entry_id": target["entry_id"]}
    first = recipe_client.post(f"/api/plans/{plan['id']}/replan/preview", json=body).json()
    stale = recipe_client.post(f"/api/plans/{plan['id']}/replan/preview", json=body).json()

    assert recipe_client.post(f"/api/plans/{plan['id']}/replan/{first['id']}/confirm").status_code == 200
    response = recipe_client.post(f"/api/plans/{plan['id']}/replan/{stale['id']}/confirm")

    assert response.status_code == 409
    assert "stale" in response.json()["detail"]


def test_lock_event_protects_meal_from_future_replanning(recipe_client: TestClient) -> None:
    plan = _generate_replanning_fixture(recipe_client, "2026-10-06")
    target = plan["days"][1]
    preview = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"event_type": "LOCK_MEAL", "entry_id": target["entry_id"]},
    ).json()
    confirmed = recipe_client.post(f"/api/plans/{plan['id']}/replan/{preview['id']}/confirm")

    assert confirmed.status_code == 200
    assert confirmed.json()["plan"]["days"][1]["is_locked"] is True
    rejected = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"event_type": "REPLACE_MEAL", "entry_id": target["entry_id"]},
    )
    assert rejected.status_code == 422
    assert "locked" in rejected.json()["detail"]


def test_item_unavailable_and_cancel_events_update_only_the_target_meal(
    recipe_client: TestClient,
) -> None:
    plan = _generate_replanning_fixture(recipe_client, "2026-10-13")
    first = plan["days"][0]
    unavailable = "chicken_breast" if first["recipe"]["slug"] == "lemon-chicken" else "firm_tofu"
    preview = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={
            "event_type": "ITEM_UNAVAILABLE",
            "entry_id": first["entry_id"],
            "unavailable_ingredient": unavailable,
        },
    )
    assert preview.status_code == 201
    assert preview.json()["after_entry"]["recipe_slug"] != first["recipe"]["slug"]
    applied = recipe_client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")
    assert applied.status_code == 200

    second = applied.json()["plan"]["days"][1]
    cancel_preview = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"event_type": "CANCEL_MEAL", "entry_id": second["entry_id"]},
    )
    assert cancel_preview.status_code == 201
    assert cancel_preview.json()["after_entry"]["status"] == "skipped"
    cancelled = recipe_client.post(f"/api/plans/{plan['id']}/replan/{cancel_preview.json()['id']}/confirm")
    assert cancelled.status_code == 200
    result = cancelled.json()["plan"]
    assert result["revision"] == 3
    assert result["days"][1]["status"] == "skipped"
    assert (
        result["nutrition_summary_per_person"]["calories_kcal"]
        < applied.json()["plan"]["nutrition_summary_per_person"]["calories_kcal"]
    )
    assert result["days"][0]["recipe"]["slug"] == preview.json()["after_entry"]["recipe_slug"]
