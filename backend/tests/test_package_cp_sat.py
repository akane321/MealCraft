from dataclasses import replace

import pytest

pytest.importorskip("ortools")

from app.planning.package_cp_sat import solve_packages_cp_sat
from app.planning.package_optimizer import optimize_packages
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import PlanningProductOption


def products():
    return [
        PlanningProductOption(ingredient_id="rice", product_id=name, package_quantity=q, package_unit="g", price_sgd=p)
        for name, q, p in [("a", 600, 4), ("b", 400, 3)]
    ]


@pytest.mark.parametrize("demand", [0.1, 400, 600, 1000, 1200, 1800])
@pytest.mark.parametrize("price", [0, 0.01, 3, 4])
def test_independent_solver_matches_enumerated_cost_and_surplus(demand, price):
    catalog = products()
    catalog[1] = catalog[1].model_copy(update={"price_sgd": price})
    actual = solve_packages_cp_sat("rice", demand, "g", catalog)
    expected = optimize_packages("rice", demand, "g", catalog)
    assert actual.status == "optimal"
    assert (actual.result.purchase_cost_sgd, actual.result.surplus_quantity) == (
        expected.purchase_cost_sgd,
        expected.surplus_quantity,
    )
    assert validate_packages("rice", demand, "g", actual.result, catalog) == ()
    assert actual == solve_packages_cp_sat("rice", demand, "g", list(reversed(catalog)))


def test_mixed_purchase_and_forged_cost():
    answer = solve_packages_cp_sat("rice", 1000, "g", products())
    assert answer.result.purchase_cost_sgd == 7
    assert len(answer.result.allocations) == 2
    assert "purchase_cost" in validate_packages(
        "rice", 1000, "g", replace(answer.result, purchase_cost_sgd=0), products()
    )


def test_limit_and_precision_do_not_claim_infeasibility():
    assert solve_packages_cp_sat("rice", 1000, "g", products(), max_products=1).status == "limit_exceeded"
    assert solve_packages_cp_sat("rice", 0.0000001, "g", products()).status == "unsupported_numeric"
    assert solve_packages_cp_sat("rice", 1e20, "g", products()).status == "unsupported_numeric"
    assert solve_packages_cp_sat("rice", 1000, "g", products(), deterministic_limit=1e-12).status == "limit_exceeded"


def test_unknown_products_and_zero_demand():
    assert solve_packages_cp_sat("rice", None, "g", products()).status == "needs_data"
    assert solve_packages_cp_sat("rice", 1, "g", []).status == "needs_data"
    assert solve_packages_cp_sat("rice", 0, "g", []).result.purchase_cost_sgd == 0


def test_decimal_coverage_is_exact():
    catalog = [products()[0].model_copy(update={"package_quantity": 0.1, "price_sgd": 0.1})]
    result = solve_packages_cp_sat("rice", 0.3, "g", catalog).result
    assert result.allocations[0].packages == 3
    assert result.surplus_quantity == 0
