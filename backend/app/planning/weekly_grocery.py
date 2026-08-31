from dataclasses import dataclass

from app.models.recipe import Recipe
from app.planning.grocery_estimator import UNIT_BASE, GroceryEstimator, ProductMatcher
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
    ) -> WeeklyGroceryEstimateResponse:
        ingredients = self._aggregate_ingredients(recipes, constraints.household_size)
        pantry = {item.normalized_name: item for item in constraints.available_ingredients}
        lines: list[GroceryLineEstimate] = []
        warnings: list[str] = []
        unmapped: list[str] = []
        purchase_total = 0.0
        consumed_total = 0.0
        consumed_total_known = True

        for ingredient in ingredients:
            pantry_deduction = GroceryEstimator.pantry_deduction(
                pantry.get(ingredient.name),
                ingredient.required_quantity,
                ingredient.unit,
            )
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

            search = self.product_service.search(
                ingredient.display_name,
                live=constraints.pricing_mode == "live",
                limit=8,
            )
            if search.warning and search.warning not in warnings:
                warnings.append(search.warning)
            product, match_score = self.matcher.choose(
                ingredient.name,
                ingredient.display_name,
                ingredient.unit,
                search.items,
            )
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
            consumed_value <= weekly_budget if weekly_budget is not None and consumed_value is not None else None
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
    def _aggregate_ingredients(recipes: list[Recipe], household_size: int) -> list[AggregatedIngredient]:
        aggregated: dict[str, AggregatedIngredient] = {}
        for recipe in recipes:
            scale = household_size / recipe.servings
            for item in recipe.recipe_ingredients:
                name = item.ingredient.normalized_name
                quantity = float(item.quantity) * scale if item.quantity is not None else None
                normalized_quantity, normalized_unit = WeeklyGroceryAggregator._to_base_unit(quantity, item.unit)
                current = aggregated.get(name)
                if current is None:
                    aggregated[name] = AggregatedIngredient(
                        name=name,
                        display_name=item.ingredient.display_name,
                        required_quantity=normalized_quantity,
                        unit=normalized_unit,
                    )
                    continue
                if current.required_quantity is None or normalized_quantity is None or current.unit != normalized_unit:
                    current.required_quantity = None
                    current.unit = normalized_unit if current.unit == normalized_unit else None
                else:
                    current.required_quantity += normalized_quantity
        return sorted(aggregated.values(), key=lambda item: item.name)

    @staticmethod
    def _to_base_unit(quantity: float | None, unit: str | None) -> tuple[float | None, str | None]:
        if quantity is None or unit is None:
            return quantity, unit
        unit_data = UNIT_BASE.get(unit.lower())
        if unit_data is None:
            return quantity, unit.lower()
        base_unit, multiplier = unit_data
        return quantity * multiplier, base_unit
