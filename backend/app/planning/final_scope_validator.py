from __future__ import annotations

from collections import defaultdict
from math import isfinite

from app.planning.dietary_tags import expand_tags
from app.planning.input_audit import nonfinite_issues
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
        # Selected product numbers retain the existing product_numeric checks.
        # Other malformed numbers must not reach arithmetic or JSON report values.
        numeric_issues = nonfinite_issues(problem.model_dump(exclude={"products"})) + nonfinite_issues(
            {"shopping": [line.model_dump() for line in shopping]}
        )
        if numeric_issues:
            checks = [self._failed("input_numeric", issue.detail, issue.path) for issue in numeric_issues]
            checks.append(
                PlanningConstraintCheck(
                    code="purchase_total",
                    status="indeterminate",
                    detail="Total was not computed because numeric input is invalid.",
                )
            )
            if problem.purchase_budget_sgd is not None:
                checks.append(
                    PlanningConstraintCheck(
                        code="purchase_budget",
                        status="indeterminate",
                        hard=problem.budget_is_hard,
                        detail="Budget was not evaluated because numeric input is invalid.",
                    )
                )
            return PlanningValidationReport(
                status="failed",
                hard_failure_count=len(numeric_issues),
                indeterminate_count=len(checks) - len(numeric_issues),
                checks=checks,
                purchase_total_sgd=0,
                catalog_version=problem.catalog_version,
                product_snapshot_version=problem.product_snapshot_version,
                policy_version=problem.policy_version,
            )
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
            if slot.locked_recipe_id is not None and assignment is None:
                checks.append(self._failed("locked_slot", "Locked slot must retain its assigned recipe.", slot.slot_id))
                continue
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

        assignment_checks_passed = not checks
        checks.extend(self._nutrition_checks(problem, assigned_by_slot))
        checks.extend(self._shopping_checks(problem, shopping))
        demand_checks = self._demand_checks(problem, assigned_by_slot, shopping)
        checks.extend(demand_checks)
        product_checks, purchase_total, cost_complete = self._product_checks(problem, shopping)
        checks.extend(product_checks)
        cost_complete = cost_complete and not demand_checks and assignment_checks_passed
        if problem.purchase_budget_sgd is not None:
            # ADR-0021: compare in whole cents with no tolerance in either
            # direction. Money is discrete, and a tolerance on it only creates a
            # band where two components disagree about the same plan. The
            # previous half-cent allowance agreed with this on every cent-valued
            # input; it differed only for sub-cent prices, which the input audit
            # now reports as a data problem rather than rounding into compliance.
            budget_cents = round(problem.purchase_budget_sgd * 100)
            total_cents = round(purchase_total * 100)
            margin = round((budget_cents - total_cents) / 100, 2)
            status: CheckStatus = "passed" if total_cents <= budget_cents else "failed"
            if not cost_complete:
                status = "indeterminate"
            checks.append(
                PlanningConstraintCheck(
                    code="purchase_budget",
                    status=status,
                    hard=problem.budget_is_hard,
                    actual=purchase_total,
                    limit=problem.purchase_budget_sgd,
                    margin=margin if cost_complete else None,
                    detail="Budget requires valid assignments and complete demand and product costs.",
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
        missing_diets = sorted(set(problem.dietary_requirements).difference(expand_tags(recipe.dietary_tags)))
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
        if not isfinite(actual):
            return PlanningConstraintCheck(
                code=f"nutrition_{band.metric}_{band.scope}",
                status="indeterminate",
                hard=band.hard,
                scope_id=scope_id,
                detail="Nutrition aggregation exceeded finite arithmetic; no margin was computed.",
            )
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
    def _demand_checks(
        problem: FinalPlanningProblem,
        assignments: dict[str, PlanningAssignment],
        shopping: list[PlanningShoppingSelection],
    ) -> list[PlanningConstraintCheck]:
        """Rebuild demand from assignments; never reuse the planner's shopping builder."""
        checks: list[PlanningConstraintCheck] = []
        recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        amounts: dict[tuple[str, str | None], list[float | None]] = defaultdict(list)
        for slot in problem.slots:
            assignment = assignments.get(slot.slot_id)
            recipe = recipes.get(assignment.recipe_id) if assignment else None
            if recipe is None:
                continue  # Assignment validation reports invalid or missing recipes.
            for item in recipe.ingredients:
                amounts[item.ingredient_id, item.unit].append(
                    None if item.quantity is None else item.quantity / recipe.servings * slot.servings
                )
        lines: dict[tuple[str, str | None], list[PlanningShoppingSelection]] = defaultdict(list)
        for line in shopping:
            lines[line.ingredient_id, line.unit].append(line)
        pantry = defaultdict(list)
        for item in problem.pantry:
            pantry[item.ingredient_id].append(item)

        def issue(code: str, ingredient: str, detail: str, unknown: bool = False) -> None:
            checks.append(
                PlanningConstraintCheck(
                    code=code,
                    status="indeterminate" if unknown else "failed",
                    scope_id=ingredient,
                    detail=detail,
                )
            )

        def matches(actual: float | None, expected: float) -> bool:
            # Existing shopping output rounds quantities to three decimal places.
            return actual is not None and isfinite(actual) and abs(actual - expected) <= 0.000500001

        for key in sorted(set(amounts) | set(lines), key=lambda value: (value[0], value[1] or "")):
            ingredient, unit = key
            rows = lines.get(key, [])
            if key not in amounts:
                issue("unexpected_shopping_line", ingredient, "Shopping line has no assigned recipe demand.")
                continue
            if len(rows) != 1:
                issue(
                    "shopping_line_count", ingredient, "Each ingredient/unit demand requires exactly one shopping line."
                )
                continue
            line = rows[0]
            values = amounts[key]
            if unit is None or any(value is None or not isfinite(value) for value in values):
                issue("demand_unknown", ingredient, "Recipe demand cannot be determined from source quantities.", True)
                continue
            required = sum(value for value in values if value is not None)
            stocks = pantry[ingredient]
            if len(stocks) > 1:
                issue(
                    "pantry_identity", ingredient, "Repeated pantry IDs require an explicit aggregation policy.", True
                )
                continue
            deduction = 0.0
            if stocks and stocks[0].unit == unit and stocks[0].quantity is not None:
                if not isfinite(stocks[0].quantity):
                    issue("pantry_quantity", ingredient, "Pantry quantity must be finite.", True)
                    continue
                deduction = min(required, stocks[0].quantity)
            remaining = required - deduction
            for code, actual, expected in (
                ("required_quantity", line.required_quantity, required),
                ("pantry_deduction", line.pantry_deduction, deduction),
                ("remaining_quantity", line.remaining_quantity, remaining),
            ):
                if not matches(actual, expected):
                    issue(code, ingredient, f"Submitted quantity {actual} differs from recomputed quantity {expected}.")
            products = [product for product in problem.products if product.product_id == line.selected_product_id]
            if len(products) == 1 and products[0].package_unit == unit:
                coverage = products[0].package_quantity * line.packages
                if not isfinite(coverage) or coverage + 1e-9 < remaining:
                    issue("demand_coverage", ingredient, "Packages do not cover independently recomputed demand.")
                if not matches(line.surplus_quantity, coverage - remaining):
                    issue(
                        "surplus_quantity", ingredient, "Surplus differs from package coverage minus remaining demand."
                    )
            elif line.selected_product_id is None and remaining == 0:
                if not matches(line.surplus_quantity, 0):
                    issue("surplus_quantity", ingredient, "A fully pantry-covered demand has zero purchase surplus.")
        return checks

    @staticmethod
    def _product_checks(
        problem: FinalPlanningProblem,
        shopping: list[PlanningShoppingSelection],
    ) -> tuple[list[PlanningConstraintCheck], float, bool]:
        """Check selected products without trusting submitted checkout amounts."""
        checks: list[PlanningConstraintCheck] = []
        products = defaultdict(list)
        for product in problem.products:
            products[product.product_id].append(product)
        total = 0.0
        complete = True
        for line in shopping:

            def reject(code: str, detail: str, scope_id: str = line.ingredient_id) -> None:
                checks.append(FinalPlanningValidator._failed(code, detail, scope_id))

            if line.selected_product_id is None:
                if line.packages != 0 or line.purchase_cost_sgd != 0:
                    reject("product_selection", "A purchase requires an identified product.")
                    complete = False
                if line.remaining_quantity is None or line.remaining_quantity > 0:
                    complete = False
                continue
            matches = products[line.selected_product_id]
            if len(matches) != 1:
                reject("product_identity", "Selected product must identify exactly one snapshot record.")
                complete = False
                continue
            product = matches[0]
            if not isfinite(product.price_sgd) or not isfinite(product.package_quantity):
                reject("product_numeric", "Snapshot price and package quantity must be finite.")
                complete = False
                continue
            expected = round(product.price_sgd * line.packages, 2)
            if not isfinite(expected) or not isfinite(total + expected):
                reject("purchase_numeric", "Package cost or running total exceeded finite arithmetic.")
                complete = False
                continue
            total += expected
            if not isfinite(line.purchase_cost_sgd) or abs(line.purchase_cost_sgd - expected) > 0.005:
                checks.append(
                    PlanningConstraintCheck(
                        code="purchase_cost",
                        status="failed",
                        scope_id=line.ingredient_id,
                        actual=line.purchase_cost_sgd,
                        limit=expected,
                        detail="Submitted cost differs from snapshot price multiplied by packages.",
                    )
                )
            if not product.available:
                reject("product_available", "Selected product is unavailable in the snapshot.")
            if product.ingredient_id != line.ingredient_id:
                reject("product_ingredient", "Selected product belongs to a different ingredient.")
            if product.package_unit != line.unit:
                reject("product_unit", "Package and demand units are incompatible.")
            elif line.remaining_quantity is not None:
                coverage = product.package_quantity * line.packages
                if coverage + 0.0005 < line.remaining_quantity:
                    reject("package_coverage", "Purchased packages do not cover the stated remaining demand.")
        return checks, round(total, 2), complete

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
