"""Project an explicitly mapped product observation into planning arithmetic."""

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from app.schemas.planning_v2 import PlanningProductOption
from app.schemas.product import ProductResponse


@dataclass(frozen=True)
class ProductInputResult:
    option: PlanningProductOption | None
    observation: ProductResponse
    issues: tuple[str, ...]


def product_input(product: ProductResponse, *, ingredient_id: str, required_unit: str) -> ProductInputResult:
    """Consume an upstream mapping, without inferring or certifying its accuracy.

    Unit equality is exact. The returned observation is a detached copy, retaining
    provenance alongside the arithmetic projection. RetrievalTrace and snapshot
    version remain the caller's responsibility; this is not a live provider.
    """
    if not ingredient_id.strip() or not required_unit.strip():
        raise ValueError("Canonical ingredient ID and required unit must be nonempty")
    source = product.model_copy(deep=True)
    issues = []
    if not source.external_id.strip():
        issues.append("missing_product_id")
    if source.package_size is None:
        issues.append("unknown_package_quantity")
    elif not isfinite(source.package_size) or source.package_size <= 0:
        issues.append("invalid_package_quantity")
    if not source.package_unit:
        issues.append("unknown_package_unit")
    elif source.package_unit != required_unit:
        issues.append("incompatible_package_unit")
    if not isfinite(source.price_sgd) or source.price_sgd < 0:
        issues.append("invalid_price")
    elif (Fraction(str(source.price_sgd)) * 100).denominator != 1:
        issues.append("fractional_cent_price")
    if source.fetched_at.utcoffset() is None:
        issues.append("observation_timezone_missing")
    if not source.product_url.strip():
        issues.append("observation_url_missing")
    if issues:
        return ProductInputResult(None, source, tuple(sorted(issues)))
    option = PlanningProductOption(
        ingredient_id=ingredient_id,
        product_id=source.external_id,
        package_quantity=source.package_size,
        package_unit=source.package_unit,
        price_sgd=source.price_sgd,
        available=source.in_stock,
    )
    return ProductInputResult(option, source, ())
