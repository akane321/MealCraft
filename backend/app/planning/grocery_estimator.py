import math
from difflib import SequenceMatcher

from app.models.recipe import Recipe
from app.schemas.product import GroceryEstimateResponse, GroceryLineEstimate, ProductResponse
from app.schemas.recommendation import AvailableIngredientInput, RecipeRecommendationRequest
from app.services.product import ProductSearchService

UNIT_BASE: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "tbsp": ("ml", 15.0),
    "tsp": ("ml", 5.0),
    "whole": ("whole", 1.0),
    "pc": ("whole", 1.0),
    "pcs": ("whole", 1.0),
}


def convert_quantity(quantity: float, from_unit: str | None, to_unit: str | None) -> float | None:
    if from_unit is None or to_unit is None:
        return None
    source = UNIT_BASE.get(from_unit.lower())
    target = UNIT_BASE.get(to_unit.lower())
    if source is None or target is None or source[0] != target[0]:
        return None
    return quantity * source[1] / target[1]


class ProductMatcher:
    def choose(
        self,
        ingredient_name: str,
        ingredient_display_name: str,
        unit: str | None,
        products: list[ProductResponse],
    ) -> tuple[ProductResponse | None, float | None]:
        ingredient_text = self._normalize(f"{ingredient_name} {ingredient_display_name}")
        ingredient_tokens = set(ingredient_text.split())
        ranked: list[tuple[float, float, ProductResponse]] = []

        for product in products:
            if not product.in_stock:
                continue
            product_text = self._normalize(product.name)
            product_tokens = set(product_text.split())
            overlap = len(ingredient_tokens.intersection(product_tokens)) / max(1, len(ingredient_tokens))
            sequence = SequenceMatcher(None, ingredient_text, product_text).ratio()
            compatibility = (
                0.15
                if product.package_unit is not None
                and unit is not None
                and convert_quantity(1.0, unit, product.package_unit) is not None
                else 0.0
            )
            score = min(1.0, overlap * 0.65 + sequence * 0.35 + compatibility)
            unit_price = (
                product.price_sgd / product.package_size
                if product.package_size is not None and product.package_size > 0
                else product.price_sgd
            )
            ranked.append((score, -unit_price, product))

        if not ranked:
            return None, None
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2].external_id))
        score, _, product = ranked[0]
        return (product, round(score, 3)) if score >= 0.30 else (None, None)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


class GroceryEstimator:
    def __init__(self, product_service: ProductSearchService, matcher: ProductMatcher | None = None) -> None:
        self.product_service = product_service
        self.matcher = matcher or ProductMatcher()

    def estimate(
        self,
        recipe: Recipe,
        constraints: RecipeRecommendationRequest,
    ) -> GroceryEstimateResponse:
        household_scale = constraints.household_size / recipe.servings
        pantry = {item.normalized_name: item for item in constraints.available_ingredients}
        lines: list[GroceryLineEstimate] = []
        unmapped: list[str] = []
        warnings: list[str] = []
        purchase_total = 0.0
        consumed_total = 0.0
        consumed_total_known = True

        for recipe_item in recipe.recipe_ingredients:
            ingredient = recipe_item.ingredient
            required = float(recipe_item.quantity) * household_scale if recipe_item.quantity is not None else None
            pantry_item = pantry.get(ingredient.normalized_name)
            pantry_deduction = self.pantry_deduction(pantry_item, required, recipe_item.unit)
            remaining = max(0.0, required - pantry_deduction) if required is not None else None

            if remaining == 0:
                lines.append(
                    GroceryLineEstimate(
                        ingredient_name=ingredient.normalized_name,
                        ingredient_display_name=ingredient.display_name,
                        required_quantity=required,
                        unit=recipe_item.unit,
                        pantry_deduction=round(pantry_deduction, 3),
                        remaining_quantity=0.0,
                        product=None,
                        match_score=None,
                        packages_required=0,
                        purchase_cost_sgd=0.0,
                        consumed_cost_sgd=0.0,
                        excess_quantity=0.0,
                        note="Known pantry quantity covers this ingredient.",
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
                ingredient.normalized_name,
                ingredient.display_name,
                recipe_item.unit,
                search.items,
            )
            if product is None:
                unmapped.append(ingredient.normalized_name)
                consumed_total_known = False
                lines.append(
                    GroceryLineEstimate(
                        ingredient_name=ingredient.normalized_name,
                        ingredient_display_name=ingredient.display_name,
                        required_quantity=required,
                        unit=recipe_item.unit,
                        pantry_deduction=round(pantry_deduction, 3),
                        remaining_quantity=remaining,
                        product=None,
                        match_score=None,
                        packages_required=0,
                        purchase_cost_sgd=0.0,
                        consumed_cost_sgd=None,
                        excess_quantity=None,
                        note="No sufficiently relevant product match was found.",
                    )
                )
                continue

            line = self.price_line(
                ingredient.normalized_name,
                ingredient.display_name,
                required,
                recipe_item.unit,
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
        budget = constraints.budget_per_meal_sgd
        within_budget = consumed_value <= budget if budget is not None and consumed_value is not None else None
        return GroceryEstimateResponse(
            pricing_mode=constraints.pricing_mode,
            complete=not unmapped and consumed_total_known,
            purchase_total_sgd=round(purchase_total, 2),
            consumed_total_sgd=consumed_value,
            budget_per_meal_sgd=budget,
            within_budget=within_budget,
            items=lines,
            unmapped_ingredients=sorted(unmapped),
            warnings=warnings,
        )

    @staticmethod
    def pantry_deduction(
        pantry_item: AvailableIngredientInput | None,
        required: float | None,
        required_unit: str | None,
    ) -> float:
        if pantry_item is None or pantry_item.quantity is None or required is None:
            return 0.0
        converted = convert_quantity(pantry_item.quantity, pantry_item.unit, required_unit)
        return min(required, converted) if converted is not None else 0.0

    @staticmethod
    def price_line(
        ingredient_name: str,
        ingredient_display_name: str,
        required: float | None,
        unit: str | None,
        pantry_deduction: float,
        remaining: float | None,
        product: ProductResponse,
        match_score: float | None,
    ) -> GroceryLineEstimate:
        converted_remaining = convert_quantity(remaining, unit, product.package_unit) if remaining is not None else None
        if converted_remaining is not None and product.package_size:
            packages = max(1, math.ceil(converted_remaining / product.package_size))
            purchase_cost = packages * product.price_sgd
            consumed_cost = product.price_sgd * converted_remaining / product.package_size
            excess = packages * product.package_size - converted_remaining
            note = None
        else:
            packages = 1
            purchase_cost = product.price_sgd
            consumed_cost = None
            excess = None
            note = "One package is shown because recipe and product units are not directly convertible."

        return GroceryLineEstimate(
            ingredient_name=ingredient_name,
            ingredient_display_name=ingredient_display_name,
            required_quantity=required,
            unit=unit,
            pantry_deduction=round(pantry_deduction, 3),
            remaining_quantity=remaining,
            product=product,
            match_score=match_score,
            packages_required=packages,
            purchase_cost_sgd=round(purchase_cost, 2),
            consumed_cost_sgd=round(consumed_cost, 2) if consumed_cost is not None else None,
            excess_quantity=round(excess, 3) if excess is not None else None,
            note=note,
        )
