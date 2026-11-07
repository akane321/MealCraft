from datetime import UTC, datetime

from app.schemas.fairprice_cart import cart_lines, fingerprint
from app.schemas.product import GroceryLineEstimate, GroceryPackageAllocation, ProductResponse


def product(product_id: str, price: float) -> ProductResponse:
    return ProductResponse(
        external_id=product_id,
        name=product_id,
        brand=None,
        category=None,
        package_size=500,
        package_unit="g",
        price_sgd=price,
        product_url=f"https://example.test/{product_id}",
        image_url=None,
        in_stock=True,
        source="fairprice",
        fetched_at=datetime.now(UTC),
    )


def test_mixed_grocery_contract_expands_to_distinct_checkout_rows():
    allocations = [
        GroceryPackageAllocation(product=product("large", 4), packages_required=1, purchase_cost_sgd=4),
        GroceryPackageAllocation(product=product("small", 3), packages_required=2, purchase_cost_sgd=6),
    ]
    line = GroceryLineEstimate(
        ingredient_name="rice",
        ingredient_display_name="Rice",
        required_quantity=1000,
        unit="g",
        pantry_deduction=0,
        remaining_quantity=1000,
        product=None,
        match_score=None,
        packages_required=0,
        purchase_cost_sgd=10,
        consumed_cost_sgd=8,
        excess_quantity=500,
        note=None,
        allocations=allocations,
    )
    rows = cart_lines([line])
    assert [(row.product.external_id, row.packages_required, row.purchase_cost_sgd) for row in rows] == [
        ("large", 1, 4),
        ("small", 2, 6),
    ]
    assert rows[0].allocation_product_id != rows[1].allocation_product_id
    assert fingerprint([line]) == fingerprint(rows)
