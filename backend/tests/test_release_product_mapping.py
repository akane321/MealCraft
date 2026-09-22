from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.recipe import Ingredient, Recipe, RecipeIngredient
from app.planning import grocery_estimator
from app.planning.grocery_estimator import GroceryEstimator
from app.schemas.product import ProductResponse
from app.schemas.recommendation import RecipeRecommendationRequest

FETCHED = "2026-09-21T08:00:00+00:00"


def _product(external_id: str, grams: float, price: float, *, in_stock: bool = True) -> dict:
    return {
        "external_id": external_id,
        "name": f"Fenugreek {external_id}",
        "brand": None,
        "category": "Spices",
        "package_grams": grams,
        "package_grams_basis": "printed weight",
        "price_sgd": price,
        "product_url": f"https://www.fairprice.com.sg/product/{external_id}",
        "in_stock": in_stock,
        "query": "fenugreek",
        "fetched_at": FETCHED,
    }


SNAPSHOT = {
    "fenugreek": {
        "status": "mapped",
        "review_status": "proposed",
        "products": [
            _product("big", 500, 4.00),  # cheaper per gram, but S$4.00 to buy
            _product("small", 100, 1.00),  # three packs cover 300 g for S$3.00
            _product("cheapest-but-gone", 1000, 2.00, in_stock=False),
        ],
    },
    "water": {"status": "not_purchased", "review_status": "proposed"},
}


class Products:
    def __init__(self, items: list[ProductResponse] | None = None) -> None:
        self.items = items or []
        self.searched: list[tuple[str, bool]] = []

    def search(self, name: str, *, live: bool, limit: int) -> SimpleNamespace:
        self.searched.append((name, live))
        return SimpleNamespace(warning=None, items=self.items)


@pytest.fixture(autouse=True)
def snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: SNAPSHOT)


def _recipe() -> Recipe:
    lines = [("fenugreek", "Fenugreek", 300), ("water", "Water", 500)]
    return Recipe(
        servings=2,
        recipe_ingredients=[
            RecipeIngredient(
                ingredient=Ingredient(normalized_name=name, display_name=display, allergens=[]),
                quantity=grams,
                unit="g",
                sort_order=index,
            )
            for index, (name, display, grams) in enumerate(lines, start=1)
        ],
    )


def _live(external_id: str, price: float) -> ProductResponse:
    return ProductResponse(
        external_id=external_id,
        name="whatever the site calls it",
        brand=None,
        category=None,
        package_size=1,
        package_unit="whole",
        price_sgd=price,
        product_url="https://www.fairprice.com.sg/product/x",
        image_url=None,
        in_stock=True,
        source="fairprice",
        fetched_at=datetime.now(UTC),
    )


def test_reviewed_mapping_prices_by_the_gram_and_water_costs_nothing() -> None:
    products = Products()
    estimate = GroceryEstimator(products).estimate(_recipe(), RecipeRecommendationRequest(household_size=2))

    fenugreek, water = estimate.items
    assert products.searched == []
    assert fenugreek.product.external_id == "small" and fenugreek.product.package_unit == "g"
    assert fenugreek.packages_required == 3 and fenugreek.purchase_cost_sgd == 3.00
    assert water.product is None and water.purchase_cost_sgd == 0 and water.consumed_cost_sgd == 0
    assert estimate.complete is True


def test_live_mode_keeps_only_reviewed_products_with_their_mapped_package() -> None:
    products = Products([_live("small", 0.50), _live("unreviewed", 0.01)])
    request = RecipeRecommendationRequest(household_size=2, pricing_mode="live")
    fenugreek = GroceryEstimator(products).estimate(_recipe(), request).items[0]

    assert products.searched == [("fenugreek", True)]
    assert fenugreek.product.external_id == "small" and fenugreek.product.package_size == 100
    assert fenugreek.product.price_sgd == 0.50 and fenugreek.product.source == "fairprice"


def test_live_mode_without_a_reviewed_product_is_visible_and_unpriced() -> None:
    request = RecipeRecommendationRequest(household_size=2, pricing_mode="live")
    estimate = GroceryEstimator(Products([_live("unreviewed", 0.01)])).estimate(_recipe(), request)

    assert estimate.items[0].product is None
    assert estimate.unmapped_ingredients == ["fenugreek"]
    assert any("did not return a reviewed product for Fenugreek" in warning for warning in estimate.warnings)


def test_a_week_keeps_lines_in_units_that_cannot_be_added() -> None:
    from app.planning.weekly_grocery import WeeklyGroceryAggregator

    carrot = Ingredient(normalized_name="carrot", display_name="Carrot", allergens=[])

    def dish(quantity: float, unit: str) -> Recipe:
        return Recipe(
            servings=2,
            recipe_ingredients=[RecipeIngredient(ingredient=carrot, quantity=quantity, unit=unit, sort_order=1)],
        )

    lines = WeeklyGroceryAggregator._aggregate_ingredients([dish(1, "whole"), dish(64, "g"), dish(36, "g")], 2)
    assert [(line.unit, line.required_quantity) for line in lines] == [("g", 100.0), ("whole", 1.0)]
