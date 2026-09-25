from dataclasses import dataclass

from app.data.units import UNIT_BASE
from app.models.recipe import Recipe
from app.planning import alternatives
from app.planning.grocery_estimator import (
    GroceryEstimator,
    ProductMatcher,
    choose_product,
    convert_quantity,
    not_purchased,
    not_purchased_line,
)
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse, WeeklyMealPlanRequest
from app.schemas.product import GroceryLineEstimate
from app.services.product import ProductSearchService


@dataclass
class AggregatedIngredient:
    name: str
    display_name: str
    required_quantity: float | None
    unit: str | None


class WeeklyGroceryAggregator:
    def __init__(self, product_service: ProductSearchService, matcher: ProductMatcher | None = None) -> None:
        self.product_service = product_service
        self.matcher = matcher or ProductMatcher()

    def estimate(
        self,
        recipes: list[Recipe],
        constraints: WeeklyMealPlanRequest,
        *,
        shares: list[float] | None = None,
    ) -> WeeklyGroceryEstimateResponse:
        """`shares` gives each recipe's portion share of its meal (ADR-0036); absent, every dish is a whole meal."""
        ingredients = self._aggregate_ingredients(recipes, constraints, shares)
        # A copy that each deduction draws down, so an ingredient needed on two
        # lines (whole carrots and grams of carrot) cannot use the same pantry twice.
        pantry = {item.normalized_name: item.model_copy() for item in constraints.available_ingredients}
        lines: list[GroceryLineEstimate] = []
        warnings: list[str] = []
        unmapped: list[str] = []
        purchase_total = 0.0
        consumed_total = 0.0
        consumed_total_known = True

        for ingredient in ingredients:
            pantry_item = pantry.get(ingredient.name)
            pantry_deduction = GroceryEstimator.pantry_deduction(
                pantry_item,
                ingredient.required_quantity,
                ingredient.unit,
            )
            if pantry_deduction and pantry_item is not None and pantry_item.quantity is not None:
                used = convert_quantity(pantry_deduction, ingredient.unit, pantry_item.unit) or 0.0
                pantry_item.quantity = max(0.0, pantry_item.quantity - used)
            remaining = (
                max(0.0, ingredient.required_quantity - pantry_deduction)
                if ingredient.required_quantity is not None
                else None
            )
            if remaining == 0:
                lines.append(
                    GroceryLineEstimate(
                        ingredient_name=ingredient.name,
                        ingredient_display_name=ingredient.display_name,
                        required_quantity=ingredient.required_quantity,
                        unit=ingredient.unit,
                        pantry_deduction=round(pantry_deduction, 3),
                        remaining_quantity=0,
                        product=None,
                        match_score=None,
                        packages_required=0,
                        purchase_cost_sgd=0,
                        consumed_cost_sgd=0,
                        excess_quantity=0,
                        note="Known pantry quantity covers the full weekly requirement.",
                    )
                )
                continue

            if not_purchased(ingredient.name):
                lines.append(
                    not_purchased_line(
                        ingredient.name, ingredient.display_name, ingredient.required_quantity, ingredient.unit
                    )
                )
                continue
            choice = choose_product(
                self.product_service,
                self.matcher,
                ingredient.name,
                ingredient.display_name,
                ingredient.unit,
                live=constraints.pricing_mode == "live",
                quantity=remaining,
            )
            warnings.extend(warning for warning in choice.warnings if warning not in warnings)
            product, match_score = choice.product, choice.match_score
            if product is None:
                unmapped.append(ingredient.name)
                consumed_total_known = False
                lines.append(
                    GroceryLineEstimate(
                        ingredient_name=ingredient.name,
                        ingredient_display_name=ingredient.display_name,
                        required_quantity=ingredient.required_quantity,
                        unit=ingredient.unit,
                        pantry_deduction=round(pantry_deduction, 3),
                        remaining_quantity=remaining,
                        product=None,
                        match_score=None,
                        packages_required=0,
                        purchase_cost_sgd=0,
                        consumed_cost_sgd=None,
                        excess_quantity=None,
                        note="No sufficiently relevant product match was found.",
                    )
                )
                continue

            line = GroceryEstimator.price_line(
                ingredient.name,
                ingredient.display_name,
                ingredient.required_quantity,
                ingredient.unit,
                pantry_deduction,
                remaining,
                product,
                match_score,
                choice.evidence,
            )
            purchase_total += line.purchase_cost_sgd
            if line.consumed_cost_sgd is None:
                consumed_total_known = False
            else:
                consumed_total += line.consumed_cost_sgd
            lines.append(line)

        consumed_value = round(consumed_total, 2) if consumed_total_known else None
        weekly_budget = constraints.weekly_budget_sgd
        within_budget = (
            round(consumed_value * 100) <= round(weekly_budget * 100)
            if weekly_budget is not None and consumed_value is not None
            else None
        )
        return WeeklyGroceryEstimateResponse(
            pricing_mode=constraints.pricing_mode,
            complete=not unmapped and consumed_total_known,
            purchase_total_sgd=round(purchase_total, 2),
            consumed_total_sgd=consumed_value,
            weekly_budget_sgd=weekly_budget,
            within_weekly_budget=within_budget,
            items=lines,
            unmapped_ingredients=sorted(unmapped),
            warnings=warnings,
        )

    @staticmethod
    def _aggregate_ingredients(
        recipes: list[Recipe], constraints, shares: list[float] | None = None
    ) -> list[AggregatedIngredient]:
        household_size = constraints.household_size
        # Keyed by ingredient and unit: lines whose units cannot be added (one whole
        # carrot and 64 g of carrot) stay separate lines rather than one unknown amount.
        aggregated: dict[tuple[str, str | None], AggregatedIngredient] = {}
        for index, recipe in enumerate(recipes):
            share = shares[index] if shares is not None else 1
            scale = household_size / recipe.servings if share == 1 else household_size * share / recipe.servings
            for item in alternatives.lines(recipe, constraints):
                name = item.ingredient.normalized_name
                quantity = float(item.quantity) * scale if item.quantity is not None else None
                normalized_quantity, normalized_unit = WeeklyGroceryAggregator._to_base_unit(quantity, item.unit)
                key = (name, normalized_unit)
                current = aggregated.get(key)
                if current is None:
                    aggregated[key] = AggregatedIngredient(
                        name=name,
                        display_name=item.ingredient.display_name,
                        required_quantity=normalized_quantity,
                        unit=normalized_unit,
                    )
                    continue
                if current.required_quantity is None or normalized_quantity is None:
                    current.required_quantity = None
                else:
                    current.required_quantity += normalized_quantity
        return sorted(aggregated.values(), key=lambda item: (item.name, item.unit or ""))

    @staticmethod
    def _to_base_unit(quantity: float | None, unit: str | None) -> tuple[float | None, str | None]:
        if quantity is None or unit is None:
            return quantity, unit
        unit_data = UNIT_BASE.get(unit.lower())
        if unit_data is None:
            return quantity, unit.lower()
        base_unit, multiplier = unit_data
        return quantity * multiplier, base_unit
