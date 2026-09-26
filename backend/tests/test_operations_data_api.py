"""Console slice 3 (ADR-0047 Data): recipes, ingredients and product mappings."""

from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.ingredient_matcher import catalog_aliases
from app.core.config import Settings, get_settings
from app.data.overrides import reload
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.platform import AuditEvent, CatalogOverride, User
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning.grocery_estimator import priceable_ingredients, release_products
from app.planning.recipe_similarity import in_english
from app.repositories.recipe import RecipeRepository, withdrawn_slugs

NUTRITION = {"calories_kcal": 500, "protein_g": 30, "carbohydrate_g": 50, "fat_g": 18, "sodium_mg": 600, "sugar_g": 6}


def _recipe(slug, title, ingredient, *, course=None, meal_types=None, release=None) -> Recipe:
    return Recipe(
        slug=slug,
        title=title,
        description=f"{title} for the data tests.",
        cuisine="Test",
        meal_type="main",
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=20,
        dietary_tags=["dairy-free"],
        course=course,
        meal_types=meal_types,
        release_version=release,
        nutrition=RecipeNutrition(**{key: Decimal(str(value)) for key, value in NUTRITION.items()}),
        recipe_ingredients=[RecipeIngredient(ingredient=ingredient, quantity=Decimal("200"), unit="g", sort_order=1)],
        steps=[RecipeStep(step_number=1, instruction="Cook it."), RecipeStep(step_number=2, instruction="Serve.")],
    )


@pytest.fixture
def console() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database:
        # Real catalog names, so the alias files and the FairPrice snapshot have entries for them.
        beans = Ingredient(normalized_name="adzuki_bean", display_name="Adzuki bean")
        agar = Ingredient(normalized_name="agar", display_name="Agar", allergens=[])
        tofu = Ingredient(normalized_name="firm_tofu", display_name="Firm tofu", allergens=["soy"])
        database.add_all(
            [
                _recipe("bean-stew", "Bean Stew", beans, course="main", meal_types=["dinner", "lunch"], release="v2.1"),
                _recipe("agar-jelly", "Agar Jelly", agar, course="dessert", meal_types=["snack"], release="v2.1"),
                _recipe("tofu-bowl", "Tofu Bowl", tofu),
                _recipe(withdrawn_slugs()[0], "Reviewed Withdrawal", tofu, course="main", meal_types=["dinner"]),
            ]
        )
        database.commit()
    test_settings = Settings(environment="test", database_url="sqlite+pysqlite://", auth_cookie_secure=False)

    def override_database() -> Generator[Session, None, None]:
        with factory() as database:
            yield database

    app.dependency_overrides[get_db_session] = override_database
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"email": "ops@example.test", "display_name": "Ops", "password": "correct-horse-battery-staple"},
        )
        assert registered.status_code == 201
        client.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        with factory() as database:
            database.scalars(select(User)).one().system_role = "admin"
            database.commit()
        yield client, factory
    app.dependency_overrides.clear()
    # Console edits live in this process too; put the files back in charge for the next test.
    with factory() as database:
        database.execute(delete(CatalogOverride))
        database.commit()
        reload(database)
    engine.dispose()


def _id(factory: sessionmaker, model, **where) -> int:
    with factory() as database:
        return database.scalars(select(model.id).filter_by(**where)).one()


def _audit(factory: sessionmaker, action: str) -> list[AuditEvent]:
    with factory() as database:
        return list(database.scalars(select(AuditEvent).where(AuditEvent.action == action)))


def _planned_slugs(factory: sessionmaker) -> set[str]:
    with factory() as database:
        recipes = RecipeRepository(database).list_for_planning(courses=["main", "dessert"])
        return {recipe.slug for recipe in recipes}


# --- recipes ---


def test_the_data_endpoints_need_console_access(console) -> None:
    client, factory = console
    with factory() as database:
        database.scalars(select(User)).one().system_role = "ordinary_user"
        database.commit()
    # The console answers as if it were not there, like the rest of /api/ops.
    assert client.get("/api/ops/data/recipes").status_code == 404
    assert client.get("/api/ops/data/ingredients").status_code == 404
    assert client.put("/api/ops/data/mappings/agar", json={"product": PRODUCT}).status_code == 404


def test_recipes_are_searched_filtered_and_shown_in_full(console) -> None:
    client, factory = console
    listed = client.get("/api/ops/data/recipes").json()
    assert listed["total"] == 4
    assert [item["slug"] for item in client.get("/api/ops/data/recipes", params={"q": "STEW"}).json()["items"]] == [
        "bean-stew"
    ]
    assert client.get("/api/ops/data/recipes", params={"course": "dessert"}).json()["total"] == 1
    assert client.get("/api/ops/data/recipes", params={"meal_type": "lunch"}).json()["items"][0]["slug"] == "bean-stew"
    assert client.get("/api/ops/data/recipes", params={"origin": "curated"}).json()["total"] == 2
    page = client.get("/api/ops/data/recipes", params={"offset": 1, "limit": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    # The reviewed file's withdrawal shows with its reason.
    withdrawn = client.get("/api/ops/data/recipes", params={"withdrawn": True}).json()["items"]
    assert [(item["withdrawn"], bool(item["withdrawn_reason"])) for item in withdrawn] == [("file", True)]
    assert client.get("/api/ops/data/recipes", params={"course": "starter"}).status_code == 422

    detail = client.get(f"/api/ops/data/recipes/{_id(factory, Recipe, slug='bean-stew')}").json()
    assert detail["ingredients"][0]["name"] == "Adzuki bean"
    assert detail["steps"] == ["Cook it.", "Serve."]
    assert detail["nutrition"]["protein_g"] == 30
    assert client.get("/api/ops/data/recipes/999999").status_code == 404


def test_a_recipe_edit_changes_its_fields_and_is_audited(console) -> None:
    client, factory = console
    recipe_id = _id(factory, Recipe, slug="agar-jelly")

    response = client.patch(
        f"/api/ops/data/recipes/{recipe_id}",
        json={"title": " Agar Squares ", "dietary_tags": ["vegan", "vegan"], "course": "main", "meal_types": ["lunch"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["dietary_tags"], body["course"], body["meal_types"]) == (
        "Agar Squares",
        ["vegan"],
        "main",
        ["lunch"],
    )
    (event,) = _audit(factory, "recipe.updated")
    assert event.target_id == "agar-jelly"
    assert event.details["before"]["course"] == "dessert"
    assert event.details["after"]["title"] == "Agar Squares"
    assert client.patch(f"/api/ops/data/recipes/{recipe_id}", json={"dietary_tags": ["keto"]}).status_code == 422
    assert client.patch("/api/ops/data/recipes/999999", json={"title": "x"}).status_code == 404


def test_a_withdrawn_recipe_stays_browsable_but_is_never_planned(console) -> None:
    client, factory = console
    recipe_id = _id(factory, Recipe, slug="bean-stew")
    assert "bean-stew" in _planned_slugs(factory)
    # The reviewed file's withdrawal is not planned either.
    assert withdrawn_slugs()[0] not in _planned_slugs(factory)

    withdrawn = client.post(f"/api/ops/data/recipes/{recipe_id}/withdraw", json={"reason": "Tastes of soap."})

    assert withdrawn.status_code == 200
    assert (withdrawn.json()["withdrawn"], withdrawn.json()["withdrawn_reason"]) == ("console", "Tastes of soap.")
    assert "bean-stew" not in _planned_slugs(factory)
    assert client.get(f"/api/ops/data/recipes/{recipe_id}").status_code == 200
    assert client.post(f"/api/ops/data/recipes/{recipe_id}/withdraw", json={"reason": "again"}).status_code == 409
    assert _audit(factory, "recipe.withdrawn")[0].details == {"reason": "Tastes of soap."}

    restored = client.post(f"/api/ops/data/recipes/{recipe_id}/restore")
    assert restored.status_code == 200 and restored.json()["withdrawn"] is None
    assert "bean-stew" in _planned_slugs(factory)
    assert _audit(factory, "recipe.restored")[0].details["reason"] == "Tastes of soap."
    assert client.post(f"/api/ops/data/recipes/{recipe_id}/restore").status_code == 409
    # The reviewed file stays the place to restore its own withdrawals.
    reviewed = client.post(f"/api/ops/data/recipes/{_id(factory, Recipe, slug=withdrawn_slugs()[0])}/restore")
    assert reviewed.status_code == 409
    assert "withdrawn.json" in reviewed.json()["detail"]


# --- ingredients ---


def test_ingredients_are_searched_by_any_of_their_names(console) -> None:
    client, _ = console
    listed = client.get("/api/ops/data/ingredients").json()
    assert listed["total"] == 3
    beans = next(item for item in listed["items"] if item["normalized_name"] == "adzuki_bean")
    assert beans["zh_names"] and beans["aliases"]
    assert beans["recipes"] == 1
    assert [
        item["normalized_name"]
        for item in client.get("/api/ops/data/ingredients", params={"q": beans["zh_names"][0]}).json()["items"]
    ] == ["adzuki_bean"]
    assert client.get("/api/ops/data/ingredients", params={"q": "tofu"}).json()["items"][0]["allergens"] == ["soy"]


def test_an_ingredient_edit_reaches_the_parser_names_and_is_audited(console) -> None:
    client, factory = console
    tofu_id = _id(factory, Ingredient, normalized_name="firm_tofu")

    response = client.patch(
        f"/api/ops/data/ingredients/{tofu_id}",
        json={
            "display_name": "Firm beancurd",
            "zh_names": ["老豆腐", " 老豆腐 ", ""],
            "aliases": ["beancurd"],
            "allergens": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["display_name"], body["zh_names"], body["aliases"]) == ("Firm beancurd", ["老豆腐"], ["beancurd"])
    # Allergens are rule-derived: the console cannot change them.
    assert body["allergens"] == ["soy"]
    assert "老豆腐" in catalog_aliases()["firm_tofu"] and "beancurd" in catalog_aliases()["firm_tofu"]
    assert "firm tofu" in in_english("我要老豆腐")
    (event,) = _audit(factory, "ingredient.updated")
    assert event.target_id == "firm_tofu"
    assert event.details["before"]["display_name"] == "Firm tofu"
    assert event.details["after"]["zh_names"] == ["老豆腐"]
    assert client.patch("/api/ops/data/ingredients/999999", json={"display_name": "x"}).status_code == 404


def test_names_set_back_to_the_file_leave_no_override(console) -> None:
    client, factory = console
    beans = next(
        item
        for item in client.get("/api/ops/data/ingredients", params={"q": "adzuki"}).json()["items"]
        if item["normalized_name"] == "adzuki_bean"
    )
    client.patch(f"/api/ops/data/ingredients/{beans['id']}", json={"aliases": ["red bean"]})
    with factory() as database:
        assert database.get(CatalogOverride, ("aliases", "adzuki_bean")).value == ["red bean"]

    client.patch(f"/api/ops/data/ingredients/{beans['id']}", json={"aliases": beans["aliases"]})

    with factory() as database:
        assert database.get(CatalogOverride, ("aliases", "adzuki_bean")) is None
    assert catalog_aliases()["adzuki_bean"][: len(beans["aliases"])] == beans["aliases"]


# --- product mappings ---

PRODUCT = {
    "external_id": "999001",
    "name": "Test Agar Strips",
    "brand": "Test",
    "category": "Jelly Powder & Mix",
    "package_grams": 25,
    "package_grams_basis": "printed 25 G",
    "price_sgd": 2.5,
    "product_url": "https://www.fairprice.com.sg/product/test-agar-strips-999001",
    "in_stock": True,
    "query": "agar strips",
    "fetched_at": "2026-09-28T10:00:00+00:00",
}


def test_the_mapping_list_shows_the_reviewed_snapshot(console) -> None:
    client, _ = console
    listed = client.get("/api/ops/data/mappings").json()
    assert listed["total"] == len(release_products())
    agar = client.get("/api/ops/data/mappings", params={"q": "agar"}).json()["items"][0]
    assert (agar["ingredient"], agar["display_name"], agar["source"]) == ("agar", "Agar", "file")
    assert agar["products"][0]["price_sgd"] > 0
    assert client.get("/api/ops/data/mappings", params={"status": "not_purchased"}).json()["total"] == 2


def test_a_mapping_change_is_what_the_estimator_prices_with(console) -> None:
    client, factory = console

    response = client.put("/api/ops/data/mappings/agar", json={"product": PRODUCT})

    assert response.status_code == 200
    assert (response.json()["source"], response.json()["review_status"]) == ("console", "console")
    assert [item["external_id"] for item in release_products()["agar"]["products"]] == ["999001"]
    assert client.get("/api/ops/data/mappings", params={"status": "console"}).json()["items"][0]["ingredient"] == "agar"
    (event,) = _audit(factory, "mapping.changed")
    assert event.details["before"]["review_status"] == "proposed"
    assert event.details["after"]["products"][0]["name"] == "Test Agar Strips"
    assert client.put("/api/ops/data/mappings/unicorn_horn", json={"product": PRODUCT}).status_code == 404
    assert (
        client.put("/api/ops/data/mappings/agar", json={"product": {**PRODUCT, "package_grams": 0}}).status_code == 422
    )


def test_a_removed_mapping_leaves_the_ingredient_unpriced(console) -> None:
    client, factory = console
    assert "agar" in priceable_ingredients() and "agar-jelly" in _planned_slugs(factory)

    response = client.delete("/api/ops/data/mappings/agar")

    assert response.status_code == 200 and response.json()["status"] == "removed"
    assert "agar" not in release_products() and "agar" not in priceable_ingredients()
    # A release recipe with an unpriceable line is never planned.
    assert "agar-jelly" not in _planned_slugs(factory)
    assert _audit(factory, "mapping.removed")[0].details["after"] == {"status": "removed"}
    assert client.delete("/api/ops/data/mappings/agar").status_code == 404
    # It can be mapped again.
    assert client.put("/api/ops/data/mappings/agar", json={"product": PRODUCT}).status_code == 200
    assert "agar" in priceable_ingredients()
