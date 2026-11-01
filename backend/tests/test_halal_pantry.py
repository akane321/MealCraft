"""A halal household does not assume a basic that needs a certified product (docs/design/halal.md, ADR-0107):
soy sauce is on the list and bought only as a Halal-marked product. Other households keep it at home.

The labels, the certification facts and the release products are built here; no data file of the halal feature is
read. Only the list of pantry basics (soy sauce is one) comes from its file.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.data import halal as halal_data
from app.models.recipe import Ingredient, RecipeIngredient
from app.planning import grocery_estimator, household_slots
from app.schemas.household_rules import HouseholdPlanning
from tests.test_planning_capability import _dish, dish_client

NOW = datetime(2026, 10, 31, tzinfo=UTC).isoformat()
HOUSEHOLD = {"members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}]}
BODY = {
    "start_date": "2027-01-03",
    "household_size": 2,
    "day_count": 1,
    "pricing_mode": "fixture",
    "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
    "household": HOUSEHOLD,
}


def label(certify=False):
    return {"status": "halal", "needs_certification": certify, "source": "test", "reason": "test"}


def entry(*products):
    def item(external_id, price):
        return {
            "external_id": external_id,
            "name": external_id,
            "brand": None,
            "category": None,
            "package_grams": 500,
            "price_sgd": price,
            "product_url": f"https://www.fairprice.com.sg/product/{external_id}",
            "in_stock": True,
            "fetched_at": NOW,
            "query": "soy sauce",
        }

    return {"status": "mapped", "products": [item(*product) for product in products]}


@pytest.fixture(autouse=True)
def facts(monkeypatch):
    built = {name: {"normalized_name": name, **label(name == "soy_sauce")} for name in ("soy_sauce", "chickpea")}
    monkeypatch.setattr(halal_data, "halal_labels", lambda: built)
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {"cert": True})
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset())
    household_slots._assumed.cache_clear()  # keyed by the flag, not by the labels this test builds
    yield
    household_slots._assumed.cache_clear()


def releases(monkeypatch, soy_sauce):
    products = {"chickpea": entry(("plain-chickpea", 2.0))}
    if soy_sauce:
        products["soy_sauce"] = entry(*soy_sauce)
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: products)


def soy_dish():
    dish = _dish("soy-chickpeas", "main", "chickpea", 300, calories=450)
    dish.halal_status = "needs_certification"
    dish.recipe_ingredients.append(
        RecipeIngredient(
            ingredient=Ingredient(normalized_name="soy_sauce", display_name="soy sauce"),
            quantity=Decimal(30),
            unit="g",
            sort_order=2,
        )
    )
    return dish


def plan(client, **request):
    return client.post("/api/plans/generate", json={"requires_halal": True, **BODY, **request})


def test_a_halal_week_buys_soy_sauce_as_the_certified_product(monkeypatch):
    releases(monkeypatch, [("cheap", 1.5), ("cert", 3.0)])
    with dish_client(monkeypatch, [soy_dish()]) as client:
        response = plan(client)
        assert response.status_code == 201, response.text
        week = response.json()
        assert [day["recipe"]["slug"] for day in week["days"]] == ["soy-chickpeas"]
        soy = next(i for i in week["grocery_estimate"]["items"] if i["ingredient_name"] == "soy_sauce")
        assert soy["product"]["external_id"] == "cert" and soy["product"]["halal_certified"] is True
        assert not any("assumed at home" in w and "soy" in w for w in week["warnings"])


def test_without_a_certified_soy_sauce_the_dish_is_not_planned_for_a_halal_household(monkeypatch):
    releases(monkeypatch, [("cheap", 1.5)])  # nothing carries FairPrice's Halal mark
    with dish_client(monkeypatch, [soy_dish()]) as client:
        assert plan(client).status_code == 422


def test_a_household_that_is_not_halal_still_has_soy_sauce_at_home(monkeypatch):
    releases(monkeypatch, [("cheap", 1.5)])
    with dish_client(monkeypatch, [soy_dish()]) as client:
        response = plan(client, requires_halal=False)
        assert response.status_code == 201, response.text
        week = response.json()
        assert "soy_sauce" not in {i["ingredient_name"] for i in week["grocery_estimate"]["items"]}
        assert any(w.startswith("Pantry basics are assumed at home") for w in week["warnings"])
        assert not any("Halal-marked" in w for w in week["warnings"])


def test_the_assumed_basics_leave_out_what_needs_certification_only_for_a_halal_household():
    household = HouseholdPlanning(members=[{"name": "Ann", "servings": 1}])
    assert "soy_sauce" in household_slots.assumed_basics(household, [])
    halal = household_slots.assumed_basics(household, [], requires_halal=True)
    assert "soy_sauce" not in halal and halal
    assert "soy_sauce" in household_slots.assumed_basics(household, [])  # the cache keys on the flag


def test_the_weekly_list_of_a_halal_household_buys_its_soy_sauce_certified_and_says_so(monkeypatch):
    """The aggregator behind saved weeks, replans and the cart (`WeeklyGroceryAggregator`) follows the same rule."""
    from app.planning.weekly_grocery import WeeklyGroceryAggregator
    from app.schemas.meal_plan import WeeklyMealPlanRequest

    releases(monkeypatch, [("cheap", 1.5), ("cert", 3.0)])
    dish = soy_dish()
    salt = Ingredient(normalized_name="salt", display_name="salt")  # a basic still at home: the note is shown
    dish.recipe_ingredients.append(RecipeIngredient(ingredient=salt, quantity=Decimal(2), unit="g", sort_order=3))
    aggregator = WeeklyGroceryAggregator(product_service=None)
    lists = {
        halal: aggregator.estimate([dish], WeeklyMealPlanRequest.model_validate({**BODY, "requires_halal": halal}))
        for halal in (True, False)
    }
    soy = next(item for item in lists[True].items if item.ingredient_name == "soy_sauce")
    assert soy.product.external_id == "cert" and soy.product.halal_certified is True
    assert any("Halal-marked product are bought" in w for w in lists[True].warnings)
    assert "soy_sauce" not in {item.ingredient_name for item in lists[False].items}
    assert not any("Halal-marked" in w for w in lists[False].warnings)
