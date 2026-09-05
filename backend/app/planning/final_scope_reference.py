from __future__ import annotations

import math
from collections import defaultdict

from app.planning.final_scope_scoring import local_recipe_loss
from app.planning.final_scope_validator import FinalPlanningValidator
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    FinalPlanningSolution,
    PlanningAssignment,
    PlanningProductOption,
    PlanningRecipeCandidate,
    PlanningShoppingSelection,
    PlanningSlot,
    PlanningTrace,
)


class FinalScopeReferencePlanner:
    """Runnable final-scope scaffold; it is intentionally not the final optimizer."""

    def __init__(self, validator: FinalPlanningValidator | None = None) -> None:
        self.validator = validator or FinalPlanningValidator()

    def solve(self, problem: FinalPlanningProblem) -> FinalPlanningSolution:
        assignments = self._assign(problem)
        shopping = self._build_shopping(problem, assignments)
        validation = self.validator.validate(problem, assignments, shopping)
        if validation.status == "passed":
            status = "feasible"
        elif validation.status == "indeterminate":
            status = "needs_data"
        else:
            status = "candidate_rejected"
        return FinalPlanningSolution(
            problem_id=problem.problem_id,
            status=status,
            assignments=assignments,
            shopping=shopping,
            validation=validation,
            trace=PlanningTrace(
                algorithm="deterministic-greedy-reference",
                algorithm_version="final-scope-reference-v1",
                deterministic=True,
                warnings=[
                    "This scaffold does not perform Beam Search, bounded live-price repair, "
                    "minimal relaxation, or optimality search."
                ],
            ),
        )

    def _assign(self, problem: FinalPlanningProblem) -> list[PlanningAssignment]:
        assignments: list[PlanningAssignment] = []
        last_recipe_id: str | None = None
        use_counts: dict[str, int] = defaultdict(int)
        for slot in sorted(problem.slots, key=self._slot_key):
            if not slot.required and slot.locked_recipe_id is None:
                continue
            candidates = self._eligible(problem, slot)
            if slot.locked_recipe_id is not None:
                candidates = [item for item in candidates if item.recipe_id == slot.locked_recipe_id]
            if not candidates:
                continue
            chosen = min(
                candidates,
                key=lambda recipe: (
                    local_recipe_loss(
                        recipe,
                        max_time_minutes=slot.max_time_minutes,
                        health_preferences=problem.health_preferences,
                    )
                    + use_counts[recipe.recipe_id] * 0.10
                    + (0.35 if recipe.recipe_id == last_recipe_id else 0.0),
                    recipe.recipe_id,
                ),
            )
            assignments.append(PlanningAssignment(slot_id=slot.slot_id, recipe_id=chosen.recipe_id))
            use_counts[chosen.recipe_id] += 1
            last_recipe_id = chosen.recipe_id
        return assignments

    @staticmethod
    def _slot_key(slot: PlanningSlot) -> tuple[object, int, str]:
        meal_order = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}
        return slot.planned_date, meal_order[slot.meal_type], slot.slot_id

    @staticmethod
    def _eligible(
        problem: FinalPlanningProblem,
        slot: PlanningSlot,
    ) -> list[PlanningRecipeCandidate]:
        eligible: list[PlanningRecipeCandidate] = []
        for recipe in problem.recipes:
            ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
            if slot.meal_type not in recipe.allowed_meal_types:
                continue
            if slot.max_time_minutes is not None and recipe.total_time_minutes > slot.max_time_minutes:
                continue
            if set(recipe.allergens).intersection(problem.allergens):
                continue
            if ingredient_ids.intersection(problem.excluded_ingredients):
                continue
            if not set(problem.dietary_requirements).issubset(recipe.dietary_tags):
                continue
            eligible.append(recipe)
        return eligible

    def _build_shopping(
        self,
        problem: FinalPlanningProblem,
        assignments: list[PlanningAssignment],
    ) -> list[PlanningShoppingSelection]:
        slots = {slot.slot_id: slot for slot in problem.slots}
        recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        quantities: dict[tuple[str, str | None], float | None] = {}
        for assignment in assignments:
            slot = slots[assignment.slot_id]
            recipe = recipes[assignment.recipe_id]
            scale = slot.servings / recipe.servings
            for item in recipe.ingredients:
                key = (item.ingredient_id, item.unit)
                quantity = item.quantity * scale if item.quantity is not None else None
                if key not in quantities:
                    quantities[key] = quantity
                elif quantities[key] is None or quantity is None:
                    quantities[key] = None
                else:
                    quantities[key] += quantity

        pantry = {item.ingredient_id: item for item in problem.pantry}
        products_by_ingredient: dict[str, list[PlanningProductOption]] = defaultdict(list)
        for product in problem.products:
            if product.available:
                products_by_ingredient[product.ingredient_id].append(product)

        shopping: list[PlanningShoppingSelection] = []
        for (ingredient_id, unit), required in sorted(quantities.items()):
            pantry_item = pantry.get(ingredient_id)
            deduction = 0.0
            if (
                pantry_item is not None
                and pantry_item.quantity is not None
                and pantry_item.unit == unit
                and required is not None
            ):
                deduction = min(required, pantry_item.quantity)
            remaining = max(0.0, required - deduction) if required is not None else None
            shopping.append(
                self._choose_product(
                    ingredient_id=ingredient_id,
                    required=required,
                    unit=unit,
                    deduction=deduction,
                    remaining=remaining,
                    products=products_by_ingredient[ingredient_id],
                )
            )
        return shopping

    @staticmethod
    def _choose_product(
        *,
        ingredient_id: str,
        required: float | None,
        unit: str | None,
        deduction: float,
        remaining: float | None,
        products: list[PlanningProductOption],
    ) -> PlanningShoppingSelection:
        if remaining == 0:
            return PlanningShoppingSelection(
                ingredient_id=ingredient_id,
                required_quantity=required,
                unit=unit,
                pantry_deduction=round(deduction, 3),
                remaining_quantity=0,
                selected_product_id=None,
                packages=0,
                purchase_cost_sgd=0,
                surplus_quantity=0,
                note="Known compatible pantry quantity covers demand.",
            )
        compatible = [item for item in products if item.package_unit == unit]
        if remaining is None or not compatible:
            return PlanningShoppingSelection(
                ingredient_id=ingredient_id,
                required_quantity=required,
                unit=unit,
                pantry_deduction=round(deduction, 3),
                remaining_quantity=remaining,
                selected_product_id=None,
                packages=0,
                purchase_cost_sgd=0,
                surplus_quantity=None,
                note="No compatible product or normalized quantity is available.",
            )
        ranked: list[tuple[float, float, str, PlanningProductOption, int]] = []
        for product in compatible:
            packages = math.ceil(remaining / product.package_quantity)
            purchase_cost = round(packages * product.price_sgd, 2)
            surplus = packages * product.package_quantity - remaining
            ranked.append((purchase_cost, surplus, product.product_id, product, packages))
        purchase_cost, surplus, _, selected, packages = min(ranked)
        return PlanningShoppingSelection(
            ingredient_id=ingredient_id,
            required_quantity=round(required, 3) if required is not None else None,
            unit=unit,
            pantry_deduction=round(deduction, 3),
            remaining_quantity=round(remaining, 3),
            selected_product_id=selected.product_id,
            packages=packages,
            purchase_cost_sgd=purchase_cost,
            surplus_quantity=round(surplus, 3),
        )
