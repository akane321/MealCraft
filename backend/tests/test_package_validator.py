from dataclasses import replace

import pytest

from app.planning.package_optimizer import PackageAllocation, optimize_packages
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import PlanningProductOption


def case():
    products = [
        PlanningProductOption(
            ingredient_id="rice", product_id=str(q), package_quantity=q, package_unit="g", price_sgd=price
        )
        for q, price in [(600, 4), (400, 3)]
    ]
    return products, optimize_packages("rice", 1000, "g", products)


def test_independent_mixed_package_arithmetic():
    products, result = case()
    assert validate_packages("rice", 1000, "g", result, products) == ()


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("purchase_cost_sgd", 0, "purchase_cost"),
        ("supplied_quantity", 1, "supplied_quantity"),
        ("surplus_quantity", 10, "surplus_quantity"),
    ],
)
def test_forged_result_fields_are_rejected(field, value, code):
    products, result = case()
    assert code in validate_packages("rice", 1000, "g", replace(result, **{field: value}), products)


def test_package_coverage_is_recomputed_after_selection_change():
    products, result = case()
    result = replace(result, allocations=(PackageAllocation("400", 1),))
    assert "insufficient_coverage" in validate_packages("rice", 1000, "g", result, products)


@pytest.mark.parametrize("update", [{"price_sgd": -1}, {"price_sgd": 0.001}, {"package_quantity": -1}])
def test_invalid_snapshot_numbers_are_rejected_independently(update):
    products, result = case()
    products[0] = products[0].model_copy(update=update)
    assert "invalid_product_numbers" in validate_packages("rice", 1000, "g", result, products)
