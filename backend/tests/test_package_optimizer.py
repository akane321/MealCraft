import pytest

from app.planning.package_optimizer import optimize_packages
from app.schemas.planning_v2 import PlanningProductOption


def packages():
    return [
        PlanningProductOption(
            ingredient_id="rice", product_id=name, package_quantity=q, package_unit="g", price_sgd=price
        )
        for name, q, price in [("large", 600, 4), ("small", 400, 3)]
    ]


def test_mixed_packages_are_cheaper_than_repeating_one_product():
    result = optimize_packages("rice", 1000, "g", packages())
    assert result.status == "optimal"
    assert [(p.product_id, p.packages) for p in result.allocations] == [("large", 1), ("small", 1)]
    assert result.purchase_cost_sgd == 7
    assert result.surplus_quantity == 0
    assert result == optimize_packages("rice", 1000, "g", list(reversed(packages())))


def test_free_product_minimizes_surplus_and_does_not_loop():
    products = [packages()[0].model_copy(update={"price_sgd": 0})]
    result = optimize_packages("rice", 1000, "g", products)
    assert result.purchase_cost_sgd == 0
    assert result.allocations[0].packages == 2
    assert result.surplus_quantity == 200


@pytest.mark.parametrize("required,unit", [(None, "g"), (1, None), (float("inf"), "g"), (-1, "g")])
def test_missing_or_invalid_demand_is_explicit(required, unit):
    assert optimize_packages("rice", required, unit, packages()).status == "needs_data"


def test_limit_does_not_claim_an_optimum():
    assert optimize_packages("rice", 1000, "g", packages(), max_combinations=1).status == "limit_exceeded"


def test_unavailable_wrong_ingredient_and_unit_are_not_substituted():
    products = [
        packages()[0].model_copy(update={"available": False}),
        packages()[1].model_copy(update={"ingredient_id": "wheat"}),
    ]
    assert optimize_packages("rice", 1000, "g", products).status == "needs_data"
    assert optimize_packages("rice", 1000, "kg", packages()).status == "needs_data"


def test_decimal_amounts_do_not_underbuy_at_float_boundary():
    products = [packages()[0].model_copy(update={"package_quantity": 0.1, "price_sgd": 0.1})]
    result = optimize_packages("rice", 0.3, "g", products)
    assert result.allocations[0].packages == 3
    assert result.purchase_cost_sgd == 0.3
    assert result.surplus_quantity == 0


def test_zero_demand_needs_no_products():
    result = optimize_packages("rice", 0, "g", [])
    assert result.status == "optimal"
    assert result.purchase_cost_sgd == 0
    assert result.allocations == ()


def test_ambiguous_id_outside_compatible_subset_is_unknown():
    catalog = packages()
    catalog.append(catalog[0].model_copy(update={"ingredient_id": "wheat"}))
    assert optimize_packages("rice", 1000, "g", catalog).status == "needs_data"


def test_extreme_finite_price_does_not_crash_or_emit_infinity():
    catalog = [packages()[0].model_copy(update={"price_sgd": 1e308})]
    assert optimize_packages("rice", 1000, "g", catalog).status == "needs_data"


@pytest.mark.parametrize("cap", [True, 1.5, 0])
def test_resource_cap_must_be_a_positive_integer(cap):
    with pytest.raises(ValueError):
        optimize_packages("rice", 1, "g", packages(), max_combinations=cap)
