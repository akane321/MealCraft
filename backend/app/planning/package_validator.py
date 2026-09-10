"""Validate mixed-package arithmetic independently from package enumeration."""

from fractions import Fraction
from math import isfinite

from app.planning.package_optimizer import PackageResult
from app.schemas.planning_v2 import PlanningProductOption


def validate_packages(
    ingredient_id: str, demand: float, unit: str, result: PackageResult, products: list[PlanningProductOption]
) -> tuple[str, ...]:
    """Return violations of coverage, identity and arithmetic, not optimality proof."""
    errors = set()
    if result.status != "optimal":
        return ("not_completed",)
    if not isfinite(demand) or demand < 0:
        return ("invalid_demand",)
    seen = set()
    cost, supplied = Fraction(0), Fraction(0)
    for allocation in result.allocations:
        if allocation.product_id in seen:
            errors.add("duplicate_product")
        seen.add(allocation.product_id)
        if isinstance(allocation.packages, bool) or not isinstance(allocation.packages, int) or allocation.packages < 1:
            errors.add("invalid_packages")
            continue
        matches = [p for p in products if p.product_id == allocation.product_id]
        if len(matches) != 1:
            errors.add("product_identity")
            continue
        p = matches[0]
        if not p.available or p.ingredient_id != ingredient_id or p.package_unit != unit:
            errors.add("incompatible_product")
            continue
        if not isfinite(p.price_sgd) or not isfinite(p.package_quantity):
            errors.add("invalid_product_numbers")
            continue
        price, quantity = Fraction(str(p.price_sgd)), Fraction(str(p.package_quantity))
        if price < 0 or quantity <= 0 or (price * 100).denominator != 1:
            errors.add("invalid_product_numbers")
            continue
        cost += price * allocation.packages
        supplied += quantity * allocation.packages
    needed = Fraction(str(demand))
    if supplied < needed:
        errors.add("insufficient_coverage")
    for code, actual, expected in [
        ("purchase_cost", result.purchase_cost_sgd, cost),
        ("supplied_quantity", result.supplied_quantity, supplied),
        ("surplus_quantity", result.surplus_quantity, supplied - needed),
    ]:
        if actual is None or not isfinite(actual) or abs(Fraction(str(actual)) - expected) > Fraction(1, 10**9):
            errors.add(code)
    return tuple(sorted(errors))
