"""Recompute baseline claims from mapped ingredients and frozen project facts.

Baseline systems supply ingredient names and gram quantities. Every line is carried into the result, mapped or
not, and nothing missing is ever read as zero or safe (ADR-0069 section 3):

- an unmapped line makes nutrition incomplete, the allergen status unknown and the price `needs_data`;
- a line whose mapping is uncertain (flagged or unmapped) is scanned for allergen keywords, and an allergen
  found that way is added to what the catalog says;
- a line whose allergen status is still unknown makes the plan's allergens incomplete, which every consumer
  treats as unsafe.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping, PlanCoverage
from app.planning.package_optimizer import PackageAllocation, optimize_packages
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

NUTRIENT_FIELDS = tuple(PlanningNutrients.model_fields)
PricingStatus = Literal["complete", "needs_data", "limit_exceeded"]

# Words that reveal an allergen of the runtime vocabulary (`data/ingredients/allergen-vocabulary.json`).
# Latin words match whole (with a plural s); Chinese words match anywhere in the line.
ALLERGEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dairy": ("milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "ghee", "whey", "casein", "paneer",
              "牛奶", "奶", "芝士", "奶酪", "黄油", "奶油", "酸奶"),
    "egg": ("egg", "mayonnaise", "mayo", "meringue", "蛋"),
    "fish": ("fish", "salmon", "tuna", "cod", "anchovy", "anchovies", "sardine", "mackerel", "tilapia",
             "snapper", "bonito", "鱼"),
    "gluten": ("wheat", "flour", "bread", "breadcrumb", "pasta", "noodle", "barley", "rye", "seitan",
               "couscous", "panko", "soy sauce", "面", "麦", "酱油"),
    "peanut": ("peanut", "groundnut", "花生"),
    "sesame": ("sesame", "tahini", "芝麻", "麻油"),
    "shellfish": ("shrimp", "prawn", "crab", "lobster", "crayfish", "scallop", "clam", "mussel", "oyster",
                  "squid", "octopus", "cuttlefish", "虾", "蟹", "贝", "蚝", "蛎", "鱿鱼", "章鱼", "蛤"),
    "soy": ("soy", "soya", "tofu", "edamame", "miso", "tempeh", "豆腐", "酱油", "大豆", "黄豆", "味噌", "豆浆", "腐竹"),
    "tree_nut": ("almond", "cashew", "walnut", "pecan", "hazelnut", "pistachio", "macadamia", "pine nut",
                 "杏仁", "腰果", "核桃", "榛子", "开心果", "松子"),
}
# Removed before the scan: common foods whose name holds an allergen word they do not carry.
# ponytail: a short list; extend it from the review list, never by guessing an allergen away.
NOT_ALLERGEN_PHRASES = (
    "coconut milk", "coconut cream", "almond milk", "oat milk", "rice milk", "soy milk", "peanut butter",
    "almond butter", "cashew butter", "cocoa butter", "butternut", "apple butter", "oyster mushroom",
    "rice noodle", "rice flour", "rice vermicelli", "glass noodle", "cream of tartar",
)


def allergen_keywords(text: str) -> frozenset[str]:
    lowered = text.casefold()
    for phrase in NOT_ALLERGEN_PHRASES:
        lowered = re.sub(rf"\b{phrase}(e?s)?\b", " ", lowered)
    found = set()
    for allergen, words in ALLERGEN_KEYWORDS.items():
        for word in words:
            pattern = re.escape(word) if not word.isascii() else rf"\b{re.escape(word)}(e?s)?\b"
            if re.search(pattern, lowered):
                found.add(allergen)
                break
    return frozenset(found)


@dataclass(frozen=True)
class IngredientEvaluationFacts:
    """Reviewed facts for one canonical ingredient in the frozen data version.

    ``None`` means unknown.  An empty allergen tuple is a reviewed assertion
    that the ingredient contains none of the checked allergens.
    """

    allergens: tuple[str, ...] | None
    nutrition_per_100g: PlanningNutrients | None


def line_allergens(
    mapping: IngredientMapping, facts: Mapping[str, IngredientEvaluationFacts]
) -> tuple[frozenset[str], bool]:
    """(allergens the line carries, whether that list is complete). An uncertain line adds its keywords."""
    found = allergen_keywords(mapping.original_name) if mapping.needs_review or not mapping.mapped else frozenset()
    if mapping.ingredient_id is None:
        return found, False
    known = facts.get(mapping.ingredient_id)
    if known is None or known.allergens is None:
        return found, False
    return found | frozenset(known.allergens), True


def dish_nutrition_per_serving(
    dish: DishCoverage, facts: Mapping[str, IngredientEvaluationFacts]
) -> dict[str, float] | None:
    """Per serving, or None when any line is unmapped or has no nutrition (never a partial sum)."""
    totals = {field: Decimal(0) for field in NUTRIENT_FIELDS}
    for mapping in dish.mappings:
        known = facts.get(mapping.ingredient_id) if mapping.ingredient_id else None
        if known is None or known.nutrition_per_100g is None:
            return None
        scale = Decimal(str(mapping.quantity_g)) / Decimal(100)
        for field in NUTRIENT_FIELDS:
            totals[field] += Decimal(str(getattr(known.nutrition_per_100g, field))) * scale
    servings = Decimal(str(dish.servings))
    return {field: float(value / servings) for field, value in totals.items()}


@dataclass(frozen=True)
class IngredientPriceResult:
    ingredient_id: str
    required_grams: float
    status: Literal["optimal", "needs_data", "limit_exceeded"]
    allocations: tuple[PackageAllocation, ...] = ()
    purchase_cost_sgd: float | None = None
    supplied_grams: float | None = None
    surplus_grams: float | None = None
    not_purchased: bool = False


@dataclass(frozen=True)
class BaselineRecomputation:
    nutrition: PlanningNutrients
    nutrition_complete: bool
    nutrition_unknown_ingredients: tuple[str, ...]
    unmapped_lines: tuple[str, ...]
    unmapped_grams: float
    allergens: tuple[str, ...]
    allergens_complete: bool
    allergen_unknown_lines: tuple[str, ...]
    pricing_status: PricingStatus
    purchase_total_sgd: float | None
    price_results: tuple[IngredientPriceResult, ...]


def recompute_ingredient_baseline(
    coverage: PlanCoverage,
    *,
    ingredient_facts: Mapping[str, IngredientEvaluationFacts],
    frozen_products: list[PlanningProductOption],
    not_purchased: frozenset[str] = frozenset(),
    max_package_combinations: int = 100000,
) -> BaselineRecomputation:
    """Recompute nutrition, allergens, and whole-package frozen pricing.

    Demand is consolidated by canonical ingredient before package selection,
    matching the product rule that the Shopping List is derived from the final
    plan rather than priced dish by dish.
    """
    mappings = coverage.mappings
    unmapped = [item for item in mappings if not item.mapped]
    demand = _mapped_demand(mappings)
    nutrient_totals = {field: Decimal(0) for field in NUTRIENT_FIELDS}
    nutrition_unknown: list[str] = []
    for ingredient_id, grams in demand.items():
        facts = ingredient_facts.get(ingredient_id)
        if facts is None or facts.nutrition_per_100g is None:
            nutrition_unknown.append(ingredient_id)
            continue
        scale = Decimal(str(grams)) / Decimal(100)
        for field in NUTRIENT_FIELDS:
            nutrient_totals[field] += Decimal(str(getattr(facts.nutrition_per_100g, field))) * scale

    allergens: set[str] = set()
    allergen_unknown: list[str] = []
    for mapping in mappings:
        found, complete = line_allergens(mapping, ingredient_facts)
        allergens |= found
        if not complete:
            allergen_unknown.append(mapping.original_name)

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
    pricing_status = _pricing_status(price_results, has_unmapped=bool(unmapped))
    purchase_total = (
        round(sum(item.purchase_cost_sgd or 0 for item in price_results), 2) if pricing_status == "complete" else None
    )

    return BaselineRecomputation(
        nutrition=PlanningNutrients(**{field: float(value) for field, value in nutrient_totals.items()}),
        nutrition_complete=not nutrition_unknown and not unmapped,
        nutrition_unknown_ingredients=tuple(nutrition_unknown),
        unmapped_lines=tuple(item.original_name for item in unmapped),
        unmapped_grams=sum(item.quantity_g for item in unmapped),
        allergens=tuple(sorted(allergens)),
        allergens_complete=not allergen_unknown,
        allergen_unknown_lines=tuple(allergen_unknown),
        pricing_status=pricing_status,
        purchase_total_sgd=purchase_total,
        price_results=price_results,
    )


def _mapped_demand(mappings: tuple[IngredientMapping, ...]) -> dict[str, float]:
    demand: dict[str, Decimal] = {}
    for mapping in mappings:
        if mapping.ingredient_id is None:
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
            not_purchased=True,
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


def _pricing_status(results: tuple[IngredientPriceResult, ...], *, has_unmapped: bool) -> PricingStatus:
    if any(item.status == "limit_exceeded" for item in results):
        return "limit_exceeded"
    if has_unmapped or any(item.status == "needs_data" for item in results):
        return "needs_data"
    return "complete"
