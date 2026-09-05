from __future__ import annotations

from collections import defaultdict

from app.schemas.planning_v2 import (
    CheckStatus,
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningConstraintCheck,
    PlanningNutritionBand,
    PlanningShoppingSelection,
    PlanningValidationReport,
)


class FinalPlanningValidator:
    """Recompute final-scope invariants without trusting planner scores."""

    def validate(
        self,
        problem: FinalPlanningProblem,
        assignments: list[PlanningAssignment],
        shopping: list[PlanningShoppingSelection],
    ) -> PlanningValidationReport:
        checks: list[PlanningConstraintCheck] = []
        slots = {slot.slot_id: slot for slot in problem.slots}
        recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        assigned_by_slot: dict[str, PlanningAssignment] = {}

        for assignment in assignments:
            if assignment.slot_id not in slots:
                checks.append(
                    self._failed(
                        "unknown_slot",
                        f"Slot {assignment.slot_id} is not in the frozen planning problem.",
                        assignment.slot_id,
                    )
                )
                continue
            if assignment.slot_id in assigned_by_slot:
                checks.append(
                    self._failed(
                        "duplicate_assignment",
                        f"Slot {assignment.slot_id} has more than one assignment.",
                        assignment.slot_id,
                    )
                )
            assigned_by_slot[assignment.slot_id] = assignment

        for slot in problem.slots:
            assignment = assigned_by_slot.get(slot.slot_id)
            if slot.required and assignment is None:
                checks.append(self._failed("required_slot", "Required slot is empty.", slot.slot_id))
                continue
            if assignment is None:
                continue
            recipe = recipes.get(assignment.recipe_id)
            if recipe is None:
                checks.append(
                    self._failed(
                        "unknown_recipe",
                        f"Recipe {assignment.recipe_id} is not in the frozen candidate set.",
                        slot.slot_id,
                    )
                )
                continue
            checks.extend(self._slot_checks(problem, slot.slot_id, assignment.recipe_id))

        checks.extend(self._nutrition_checks(problem, assigned_by_slot))
        checks.extend(self._shopping_checks(problem, shopping))
        purchase_total = round(sum(line.purchase_cost_sgd for line in shopping), 2)
        if problem.purchase_budget_sgd is not None:
            margin = round(problem.purchase_budget_sgd - purchase_total, 2)
            status: CheckStatus = "passed" if margin >= -0.005 else "failed"
            checks.append(
                PlanningConstraintCheck(
                    code="purchase_budget",
                    status=status,
                    hard=problem.budget_is_hard,
                    actual=purchase_total,
                    limit=problem.purchase_budget_sgd,
                    margin=margin,
                    detail="Purchase budget is checked against package checkout cost.",
                )
            )

        hard_failures = sum(check.status == "failed" and check.hard for check in checks)
        indeterminate = sum(check.status == "indeterminate" for check in checks)
        overall: CheckStatus
        if hard_failures:
            overall = "failed"
        elif indeterminate:
            overall = "indeterminate"
        else:
            overall = "passed"
        return PlanningValidationReport(
            status=overall,
            hard_failure_count=hard_failures,
            indeterminate_count=indeterminate,
            checks=checks,
            purchase_total_sgd=purchase_total,
            catalog_version=problem.catalog_version,
            product_snapshot_version=problem.product_snapshot_version,
            policy_version=problem.policy_version,
        )

    def _slot_checks(
        self,
        problem: FinalPlanningProblem,
        slot_id: str,
        recipe_id: str,
    ) -> list[PlanningConstraintCheck]:
        slot = next(item for item in problem.slots if item.slot_id == slot_id)
        recipe = next(item for item in problem.recipes if item.recipe_id == recipe_id)
        checks: list[PlanningConstraintCheck] = []
        if slot.locked_recipe_id is not None and slot.locked_recipe_id != recipe_id:
            checks.append(self._failed("locked_slot", "Locked assignment was changed.", slot_id))
        if slot.meal_type not in recipe.allowed_meal_types:
            checks.append(self._failed("meal_type", "Recipe is not eligible for this meal type.", slot_id))
        if slot.max_time_minutes is not None and recipe.total_time_minutes > slot.max_time_minutes:
            checks.append(
                PlanningConstraintCheck(
                    code="time_limit",
                    status="failed",
                    scope_id=slot_id,
                    actual=recipe.total_time_minutes,
                    limit=slot.max_time_minutes,
                    margin=float(slot.max_time_minutes - recipe.total_time_minutes),
                    detail="Recipe exceeds the explicit slot time limit.",
                )
            )
        allergen_hits = sorted(set(recipe.allergens).intersection(problem.allergens))
        if allergen_hits:
            checks.append(
                self._failed(
                    "allergen",
                    f"Recipe contains prohibited allergens: {', '.join(allergen_hits)}.",
                    slot_id,
                )
            )
        ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
        excluded_hits = sorted(ingredient_ids.intersection(problem.excluded_ingredients))
        if excluded_hits:
            checks.append(
                self._failed(
                    "excluded_ingredient",
                    f"Recipe contains excluded ingredients: {', '.join(excluded_hits)}.",
                    slot_id,
                )
            )
        missing_diets = sorted(set(problem.dietary_requirements).difference(recipe.dietary_tags))
        if missing_diets:
            checks.append(
                self._failed(
                    "dietary_requirement",
                    f"Recipe does not satisfy: {', '.join(missing_diets)}.",
                    slot_id,
                )
            )
        return checks

    def _nutrition_checks(
        self,
        problem: FinalPlanningProblem,
        assigned_by_slot: dict[str, PlanningAssignment],
    ) -> list[PlanningConstraintCheck]:
        recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        slots = {slot.slot_id: slot for slot in problem.slots}
        values_by_day: dict[object, list[object]] = defaultdict(list)
        values_by_slot: dict[str, object] = {}
        for slot_id, assignment in assigned_by_slot.items():
            recipe = recipes.get(assignment.recipe_id)
            slot = slots.get(slot_id)
            if recipe is None or slot is None:
                continue
            values_by_slot[slot_id] = recipe.nutrients_per_serving
            values_by_day[slot.planned_date].append(recipe.nutrients_per_serving)

        checks: list[PlanningConstraintCheck] = []
        for band in problem.nutrition_bands:
            observations = self._nutrition_observations(band, values_by_slot, values_by_day)
            for scope_id, actual in observations:
                checks.append(self._band_check(band, scope_id, actual))
        return checks

    @staticmethod
    def _nutrition_observations(
        band: PlanningNutritionBand,
        values_by_slot: dict[str, object],
        values_by_day: dict[object, list[object]],
    ) -> list[tuple[str, float]]:
        if band.scope == "per_slot":
            return [
                (slot_id, float(getattr(values, band.metric))) for slot_id, values in sorted(values_by_slot.items())
            ]
        daily = [
            (str(day), sum(float(getattr(values, band.metric)) for values in rows))
            for day, rows in sorted(values_by_day.items(), key=lambda item: item[0])
        ]
        if band.scope == "per_day":
            return daily
        average = sum(value for _, value in daily) / len(daily) if daily else 0.0
        return [("horizon_average", average)]

    @staticmethod
    def _band_check(
        band: PlanningNutritionBand,
        scope_id: str,
        actual: float,
    ) -> PlanningConstraintCheck:
        lower_margin = actual - band.lower if band.lower is not None else None
        upper_margin = band.upper - actual if band.upper is not None else None
        margins = [value for value in (lower_margin, upper_margin) if value is not None]
        margin = min(margins) if margins else None
        status: CheckStatus = "passed" if margin is None or margin >= -1e-6 else "failed"
        return PlanningConstraintCheck(
            code=f"nutrition_{band.metric}_{band.scope}",
            status=status,
            hard=band.hard,
            scope_id=scope_id,
            actual=round(actual, 3),
            limit=f"[{band.lower}, {band.upper}]",
            margin=round(margin, 3) if margin is not None else None,
            detail="Nutrition is recomputed from selected canonical recipes per person.",
        )

    @staticmethod
    def _shopping_checks(
        problem: FinalPlanningProblem,
        shopping: list[PlanningShoppingSelection],
    ) -> list[PlanningConstraintCheck]:
        checks: list[PlanningConstraintCheck] = []
        for line in shopping:
            if line.remaining_quantity is None:
                checks.append(
                    PlanningConstraintCheck(
                        code="shopping_quantity",
                        status="indeterminate",
                        scope_id=line.ingredient_id,
                        detail="Required quantity or unit could not be normalized.",
                    )
                )
            elif line.remaining_quantity > 0 and line.selected_product_id is None:
                checks.append(
                    PlanningConstraintCheck(
                        code="product_mapping",
                        status="indeterminate",
                        scope_id=line.ingredient_id,
                        detail="No compatible available product was selected.",
                    )
                )
            elif line.remaining_quantity > 0 and line.packages <= 0:
                checks.append(
                    FinalPlanningValidator._failed(
                        "package_coverage",
                        "Positive shopping demand has no purchased package.",
                        line.ingredient_id,
                    )
                )
        if not shopping and any(slot.required for slot in problem.slots):
            checks.append(
                PlanningConstraintCheck(
                    code="shopping_list",
                    status="indeterminate",
                    detail="No Shopping List was supplied for a non-empty plan.",
                )
            )
        return checks

    @staticmethod
    def _failed(
        code: str,
        detail: str,
        scope_id: str | None = None,
        *,
        hard: bool = True,
    ) -> PlanningConstraintCheck:
        return PlanningConstraintCheck(
            code=code,
            status="failed",
            hard=hard,
            scope_id=scope_id,
            detail=detail,
        )
