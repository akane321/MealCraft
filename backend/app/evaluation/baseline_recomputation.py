"""Recompute baseline claims from mapped ingredients and frozen project facts.

Baseline systems supply ingredient names and gram quantities.  This module
scores only the rows that the mapping layer accepted, and never treats missing
nutrition, allergen, or product facts as zero or safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.evaluation.baseline_mapping import CoverageResult
from app.planning.package_optimizer import PackageAllocation, optimize_packages
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

NUTRIENT_FIELDS = tuple(PlanningNutrients.model_fields)
PricingStatus = Literal["complete", "needs_data", "limit_exceeded"]


@dataclass(frozen=True)
class IngredientEvaluationFacts:
    """Reviewed facts for one canonical ingredient in the frozen data version.

    ``None`` means unknown.  An empty allergen tuple is a reviewed assertion
    that the ingredient contains none of the checked allergens.
    """

    allergens: tuple[str, ...] | None
    nutrition_per_100g: PlanningNutrients | None


@dataclass(frozen=True)
class IngredientPriceResult:
    ingredient_id: str
    required_grams: float
    status: Literal["optimal", "needs_data", "limit_exceeded"]
    allocations: tuple[PackageAllocation, ...] = ()
    purchase_cost_sgd: float | None = None
    supplied_grams: float | None = None
    surplus_grams: float | None = None


@dataclass(frozen=True)
class BaselineRecomputation:
    nutrition: PlanningNutrients
    nutrition_complete: bool
    nutrition_unknown_ingredients: tuple[str, ...]
    allergens: tuple[str, ...]
    allergens_complete: bool
    allergen_unknown_ingredients: tuple[str, ...]
    pricing_status: PricingStatus
    purchase_total_sgd: float | None
    price_results: tuple[IngredientPriceResult, ...]


def recompute_ingredient_baseline(
    coverage: CoverageResult,
    *,
    ingredient_facts: dict[str, IngredientEvaluationFacts],
    frozen_products: list[PlanningProductOption],
    not_purchased: frozenset[str] = frozenset(),
    max_package_combinations: int = 100000,
) -> BaselineRecomputation:
    """Recompute nutrition, allergens, and whole-package frozen pricing.

    Demand is consolidated by canonical ingredient before package selection,
    matching the product rule that the Shopping List is derived from the final
    plan rather than priced dish by dish.
    """
    demand = _matched_demand(coverage)
    nutrient_totals = {field: Decimal(0) for field in NUTRIENT_FIELDS}
    allergens: set[str] = set()
    nutrition_unknown: list[str] = []
    allergen_unknown: list[str] = []

    for ingredient_id, grams in demand.items():
        facts = ingredient_facts.get(ingredient_id)
        if facts is None or facts.allergens is None:
            allergen_unknown.append(ingredient_id)
        else:
            allergens.update(facts.allergens)

        if facts is None or facts.nutrition_per_100g is None:
            nutrition_unknown.append(ingredient_id)
            continue
        scale = Decimal(str(grams)) / Decimal(100)
        for field in NUTRIENT_FIELDS:
            nutrient_totals[field] += Decimal(str(getattr(facts.nutrition_per_100g, field))) * scale

    price_results = tuple(
        _price_ingredient(
            ingredient_id,
            grams,
            frozen_products=frozen_products,
            not_purchased=not_purchased,
            max_package_combinations=max_package_combinations,
        )
        for ingredient_id, grams in demand.items()
    )
    pricing_status = _pricing_status(price_results)
    purchase_total = (
        round(sum(item.purchase_cost_sgd or 0 for item in price_results), 2) if pricing_status == "complete" else None
    )

    return BaselineRecomputation(
        nutrition=PlanningNutrients(**{field: float(value) for field, value in nutrient_totals.items()}),
        nutrition_complete=not nutrition_unknown,
        nutrition_unknown_ingredients=tuple(nutrition_unknown),
        allergens=tuple(sorted(allergens)),
        allergens_complete=not allergen_unknown,
        allergen_unknown_ingredients=tuple(allergen_unknown),
        pricing_status=pricing_status,
        purchase_total_sgd=purchase_total,
        price_results=price_results,
    )


def _matched_demand(coverage: CoverageResult) -> dict[str, float]:
    demand: dict[str, Decimal] = {}
    for mapping in coverage.mappings:
        if mapping.status != "matched" or mapping.ingredient_id is None:
            continue
        demand[mapping.ingredient_id] = demand.get(mapping.ingredient_id, Decimal(0)) + Decimal(str(mapping.quantity_g))
    return {ingredient_id: float(grams) for ingredient_id, grams in sorted(demand.items())}


def _price_ingredient(
    ingredient_id: str,
    required_grams: float,
    *,
    frozen_products: list[PlanningProductOption],
    not_purchased: frozenset[str],
    max_package_combinations: int,
) -> IngredientPriceResult:
    if ingredient_id in not_purchased:
        return IngredientPriceResult(
            ingredient_id=ingredient_id,
            required_grams=required_grams,
            status="optimal",
            purchase_cost_sgd=0.0,
            supplied_grams=required_grams,
            surplus_grams=0.0,
        )
    result = optimize_packages(
        ingredient_id,
        required_grams,
        "g",
        frozen_products,
        max_combinations=max_package_combinations,
    )
    return IngredientPriceResult(
        ingredient_id=ingredient_id,
        required_grams=required_grams,
        status=result.status,
        allocations=result.allocations,
        purchase_cost_sgd=result.purchase_cost_sgd,
        supplied_grams=result.supplied_quantity,
        surplus_grams=result.surplus_quantity,
    )


def _pricing_status(results: tuple[IngredientPriceResult, ...]) -> PricingStatus:
    if any(item.status == "limit_exceeded" for item in results):
        return "limit_exceeded"
    if any(item.status == "needs_data" for item in results):
        return "needs_data"
    return "complete"
