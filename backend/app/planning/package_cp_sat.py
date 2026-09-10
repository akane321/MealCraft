"""Optional offline CP-SAT oracle for a single normalized ingredient demand."""

from dataclasses import dataclass
from fractions import Fraction
from math import ceil, isfinite, lcm
from typing import Literal

from app.planning.package_optimizer import PackageAllocation, PackageResult
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import PlanningProductOption


@dataclass(frozen=True)
class PackageOracleResult:
    status: Literal["optimal", "needs_data", "limit_exceeded", "unsupported_numeric", "solver_error"]
    result: PackageResult | None = None
    detail: str = ""
    solver_version: str | None = None


def solve_packages_cp_sat(
    ingredient_id: str,
    required: float | None,
    unit: str | None,
    products: list[PlanningProductOption],
    *,
    deterministic_limit: float = 1.0,
    max_products: int = 32,
) -> PackageOracleResult:
    """Prove minimum cost then minimum surplus using exact integer coefficients.

    Quantity scaling is exact and capped at 10**6; oversized integer models are
    refused rather than rounded. Tied solutions minimize the sorted count vector,
    which can differ from the enumerator's selected-ID tuple tie-break.
    Each solve consumes part of one shared deterministic-work budget.
    """
    if not isfinite(deterministic_limit) or deterministic_limit <= 0:
        raise ValueError("deterministic_limit must be finite and positive")
    if isinstance(max_products, bool) or not isinstance(max_products, int) or max_products < 1:
        raise ValueError("max_products must be a positive integer")
    if required is None or not isfinite(required) or required < 0 or not unit:
        return PackageOracleResult("needs_data", detail="Unknown or invalid normalized demand")
    if required == 0:
        return PackageOracleResult("optimal", PackageResult("optimal", (), 0, 0, 0))
    candidates = sorted(
        (p for p in products if p.ingredient_id == ingredient_id and p.package_unit == unit and p.available),
        key=lambda p: p.product_id,
    )
    if not candidates or any(sum(p.product_id == c.product_id for p in products) != 1 for c in candidates):
        return PackageOracleResult("needs_data", detail="Missing or ambiguous compatible products")
    if len(candidates) > max_products:
        return PackageOracleResult("limit_exceeded", detail="Product count exceeds cap")
    if any(not isfinite(p.price_sgd) or not isfinite(p.package_quantity) for p in candidates):
        return PackageOracleResult("needs_data", detail="Nonfinite product numbers")
    quantities = [Fraction(str(p.package_quantity)) for p in candidates]
    prices = [Fraction(str(p.price_sgd)) * 100 for p in candidates]
    if any(q <= 0 for q in quantities) or any(p < 0 or p.denominator != 1 for p in prices):
        return PackageOracleResult(
            "needs_data", detail="Positive quantities and nonnegative whole-cent prices required"
        )
    demand = Fraction(str(required))
    scale = lcm(demand.denominator, *(q.denominator for q in quantities))
    if scale > 10**6:
        return PackageOracleResult("unsupported_numeric", detail="Exact quantity scale exceeds 10**6")
    units = [int(q * scale) for q in quantities]
    cents = [int(p) for p in prices]
    bounds = [ceil(demand / q) for q in quantities]
    if (
        max(
            int(demand * scale),
            sum(q * b for q, b in zip(units, bounds, strict=True)),
            sum(c * b for c, b in zip(cents, bounds, strict=True)),
            *bounds,
        )
        > 10**12
    ):
        return PackageOracleResult("unsupported_numeric", detail="Integer activity exceeds 10**12")
    # Keep the optional solver out of production imports and runtime dependencies.
    import ortools
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    variables = [model.new_int_var(0, b, p.product_id) for p, b in zip(candidates, bounds, strict=True)]
    coverage = sum(q * v for q, v in zip(units, variables, strict=True))
    checkout = sum(c * v for c, v in zip(cents, variables, strict=True))
    model.add(coverage >= int(demand * scale))
    remaining = deterministic_limit
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    for objective in (checkout, coverage, *variables):
        if remaining <= 0:
            return PackageOracleResult(
                "limit_exceeded", detail="Deterministic work cap", solver_version=ortools.__version__
            )
        model.minimize(objective)
        solver.parameters.max_deterministic_time = remaining
        status = solver.solve(model)
        remaining -= solver.response_proto.deterministic_time
        if status != cp_model.OPTIMAL:
            stopped = status in (cp_model.UNKNOWN, cp_model.FEASIBLE)
            return PackageOracleResult(
                "limit_exceeded" if stopped else "solver_error",
                detail=solver.status_name(status),
                solver_version=ortools.__version__,
            )
        model.add(objective == solver.value(objective))
    counts = [solver.value(v) for v in variables]
    supplied = sum((q * n for q, n in zip(quantities, counts, strict=True)), Fraction(0))
    cost = sum(c * n for c, n in zip(cents, counts, strict=True)) / 100
    result = PackageResult(
        "optimal",
        tuple(PackageAllocation(p.product_id, n) for p, n in zip(candidates, counts, strict=True) if n),
        cost,
        float(supplied),
        float(supplied - demand),
    )
    errors = validate_packages(ingredient_id, required, unit, result, products)
    if errors:
        return PackageOracleResult("solver_error", detail=", ".join(errors), solver_version=ortools.__version__)
    return PackageOracleResult("optimal", result, solver_version=ortools.__version__)
