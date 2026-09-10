"""Exact mixed-package selection for bounded, normalized developer inputs."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import ceil, isfinite, prod
from typing import Literal

from app.schemas.planning_v2 import PlanningProductOption


@dataclass(frozen=True)
class PackageAllocation:
    product_id: str
    packages: int


@dataclass(frozen=True)
class PackageResult:
    status: Literal["optimal", "needs_data", "limit_exceeded"]
    allocations: tuple[PackageAllocation, ...] = ()
    purchase_cost_sgd: float | None = None
    supplied_quantity: float | None = None
    surplus_quantity: float | None = None
    combinations: int = 0


def optimize_packages(
    ingredient_id: str,
    required: float | None,
    unit: str | None,
    products: list[PlanningProductOption],
    *,
    max_combinations: int = 100000,
) -> PackageResult:
    """Minimize checkout cost, then surplus, then product/count IDs.

    Every product type may contribute packages. Enumeration is exact only when
    the reported bounds fit the configured cap. No unit conversion or substitution
    is inferred. Zero demand needs no product evidence.
    """
    if isinstance(max_combinations, bool) or not isinstance(max_combinations, int) or max_combinations < 1:
        raise ValueError("max_combinations must be positive")
    if required is None or not isfinite(required) or required < 0 or unit is None:
        return PackageResult("needs_data")
    if required == 0:
        return PackageResult("optimal", (), 0, 0, 0, 1)
    candidates = sorted(
        (p for p in products if p.ingredient_id == ingredient_id and p.available and p.package_unit == unit),
        key=lambda p: p.product_id,
    )
    if not candidates or any(sum(p.product_id == c.product_id for p in products) != 1 for c in candidates):
        return PackageResult("needs_data")
    if any(not isfinite(p.price_sgd) or not isfinite(p.package_quantity) for p in candidates):
        return PackageResult("needs_data")
    demand = Fraction(str(required))
    quantities = [Fraction(str(p.package_quantity)) for p in candidates]
    prices = [Fraction(str(p.price_sgd)) for p in candidates]
    if any(q <= 0 for q in quantities) or any(p < 0 or (p * 100).denominator != 1 for p in prices):
        return PackageResult("needs_data")
    # An optimum never needs more than ceil(demand/package) of one product:
    # removing excess packages reduces cost or, for free products, surplus.
    bounds = [ceil(demand / q) for q in quantities]
    combinations = prod(n + 1 for n in bounds)
    if combinations > max_combinations:
        return PackageResult("limit_exceeded", combinations=combinations)
    best = None
    for counts in product(*(range(n + 1) for n in bounds)):
        supplied = sum((q * count for q, count in zip(quantities, counts, strict=True)), Fraction(0))
        if supplied < demand:
            continue
        cost = sum((p * count for p, count in zip(prices, counts, strict=True)), Fraction(0))
        selected = tuple((p.product_id, count) for p, count in zip(candidates, counts, strict=True) if count)
        key = (cost, supplied - demand, selected)
        if best is None or key < best:
            best = key
    cost, surplus, selected = best
    try:
        numbers = [float(cost), float(demand + surplus), float(surplus)]
    except OverflowError:
        return PackageResult("needs_data", combinations=combinations)
    if not all(isfinite(value) for value in numbers):
        return PackageResult("needs_data", combinations=combinations)
    return PackageResult(
        "optimal",
        tuple(PackageAllocation(p, n) for p, n in selected),
        float(cost),
        float(demand + surplus),
        float(surplus),
        combinations,
    )
