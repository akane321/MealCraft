"""Offline mixed-package shopping contract, kept separate from the public V2 API."""

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.package_optimizer import PackageResult, optimize_packages
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class MixedShoppingLine:
    ingredient_id: str
    unit: str
    required_quantity: float
    pantry_deduction: float
    remaining_quantity: float
    purchase: PackageResult


@dataclass(frozen=True)
class MixedShoppingResult:
    status: str
    lines: tuple[MixedShoppingLine, ...] = ()
    purchase_total_sgd: float | None = None
    issues: tuple[str, ...] = ()
    contract_version: str = "offline-mixed-shopping-v1"


def assignment_issues(problem: FinalPlanningProblem, assignments: list[PlanningAssignment]) -> tuple[str, ...]:
    """Reuse canonical slot/nutrition checks, independently of shopping policy."""
    validator = FinalPlanningValidator()
    slots = {s.slot_id: s for s in problem.slots}
    recipes = {r.recipe_id: r for r in problem.recipes}
    selected = {}
    issues = set()
    for a in assignments:
        if a.slot_id not in slots or a.recipe_id not in recipes:
            issues.add("unknown_assignment")
            continue
        if a.slot_id in selected:
            issues.add("duplicate_assignment")
        selected[a.slot_id] = a
        issues.update(c.code for c in validator._slot_checks(problem, a.slot_id, a.recipe_id) if c.hard)
    for s in problem.slots:
        if (s.required or s.locked_recipe_id is not None) and s.slot_id not in selected:
            issues.add("missing_assignment")
    issues.update(c.code for c in validator._nutrition_checks(problem, selected) if c.hard and c.status != "passed")
    return tuple(sorted(issues))


@dataclass(frozen=True)
class NormalizedDemand:
    ingredient_id: str
    unit: str
    required_quantity: float
    pantry_deduction: float
    remaining_quantity: float


def derive_mixed_demands(problem: FinalPlanningProblem, assignments: list[PlanningAssignment]):
    """Derive complete quantities before requesting or selecting any products."""
    issues = assignment_issues(problem, assignments)
    if issues:
        return (), issues
    recipes = {r.recipe_id: r for r in problem.recipes}
    slots = {s.slot_id: s for s in problem.slots}
    amounts = defaultdict(Fraction)
    for a in assignments:
        recipe, slot = recipes[a.recipe_id], slots[a.slot_id]
        for item in recipe.ingredients:
            if item.quantity is None or not isfinite(item.quantity) or item.quantity <= 0 or not item.unit:
                return (), ("demand_unknown",)
            amounts[item.ingredient_id, item.unit] += Fraction(str(item.quantity)) * slot.servings / recipe.servings
    demands = []
    for (ingredient, unit), required in sorted(amounts.items()):
        stocks = [p for p in problem.pantry if p.ingredient_id == ingredient]
        if len(stocks) > 1:
            return (), ("pantry_identity",)
        deduction = Fraction(0)
        if stocks and stocks[0].unit == unit and stocks[0].quantity is not None:
            if not isfinite(stocks[0].quantity) or stocks[0].quantity < 0:
                return (), ("pantry_quantity",)
            deduction = min(required, Fraction(str(stocks[0].quantity)))
        remaining = required - deduction
        # The offline contract serializes floats. Refuse lossy demand conversion
        # rather than purchase against a rounded value (e.g. a third of a gram).
        try:
            values = tuple(float(v) for v in (required, deduction, remaining))
        except OverflowError:
            return (), ("quantity_not_representable",)
        if any(
            not isfinite(v) or Fraction(str(v)) != exact
            for v, exact in zip(values, (required, deduction, remaining), strict=True)
        ):
            return (), ("quantity_not_representable",)
        demands.append(NormalizedDemand(ingredient, unit, *values))
    return tuple(demands), ()


def build_mixed_shopping(
    problem: FinalPlanningProblem,
    assignments: list[PlanningAssignment],
    *,
    max_combinations: int = 100000,
    use_cp_sat: bool = False,
) -> MixedShoppingResult:
    issues = assignment_issues(problem, assignments)
    if issues:
        return MixedShoppingResult("candidate_rejected", issues=issues)
    demands, issues = derive_mixed_demands(problem, assignments)
    if issues:
        return MixedShoppingResult("needs_data", issues=issues)
    lines = []
    for demand in demands:
        ingredient, unit = demand.ingredient_id, demand.unit
        values = (demand.required_quantity, demand.pantry_deduction, demand.remaining_quantity)
        if use_cp_sat:
            from app.planning.package_cp_sat import solve_packages_cp_sat

            oracle = solve_packages_cp_sat(ingredient, values[2], unit, problem.products)
            if oracle.status != "optimal":
                return MixedShoppingResult(oracle.status, issues=(oracle.detail,))
            purchase = oracle.result
        else:
            purchase = optimize_packages(
                ingredient, values[2], unit, problem.products, max_combinations=max_combinations
            )
        if purchase.status != "optimal":
            return MixedShoppingResult(purchase.status, issues=(f"package_{purchase.status}:{ingredient}",))
        lines.append(MixedShoppingLine(ingredient, unit, *values, purchase))
    total = sum((Fraction(str(line.purchase.purchase_cost_sgd)) for line in lines), Fraction(0))
    try:
        total_float = float(total)
    except OverflowError:
        return MixedShoppingResult("needs_data", issues=("cost_not_representable",))
    if not isfinite(total_float):
        return MixedShoppingResult("needs_data", issues=("cost_not_representable",))
    result = MixedShoppingResult("feasible", tuple(lines), total_float)
    errors = validate_mixed_shopping(problem, assignments, result)
    return MixedShoppingResult("candidate_rejected", tuple(lines), total_float, errors) if errors else result


def validate_mixed_shopping(
    problem: FinalPlanningProblem,
    assignments: list[PlanningAssignment],
    result: MixedShoppingResult,
) -> tuple[str, ...]:
    """Recompute demand and pantry once from source; validate every package identity.

    Does not call the builder or trust its quantities, total, or status.
    """
    errors = set(assignment_issues(problem, assignments))
    if errors:
        return tuple(sorted(errors))
    expected = defaultdict(Fraction)
    for slot in problem.slots:
        selected = next((a for a in assignments if a.slot_id == slot.slot_id), None)
        if selected is None:
            continue
        recipe = next(r for r in problem.recipes if r.recipe_id == selected.recipe_id)
        for item in recipe.ingredients:
            if item.quantity is None or not isfinite(item.quantity) or item.quantity <= 0 or not item.unit:
                return ("demand_unknown",)
            expected[item.ingredient_id, item.unit] += Fraction(str(item.quantity)) / recipe.servings * slot.servings
    submitted = defaultdict(list)
    for line in result.lines:
        submitted[line.ingredient_id, line.unit].append(line)
    if set(submitted) != set(expected) or any(len(rows) != 1 for rows in submitted.values()):
        return ("shopping_line_identity",)
    total = Fraction(0)
    for (ingredient, unit), required in expected.items():
        line = submitted[ingredient, unit][0]
        pantry = [p for p in problem.pantry if p.ingredient_id == ingredient]
        if len(pantry) > 1:
            errors.add("pantry_identity")
            continue
        deduction = Fraction(0)
        if pantry and pantry[0].quantity is not None and pantry[0].unit == unit:
            if not isfinite(pantry[0].quantity) or pantry[0].quantity < 0:
                errors.add("pantry_quantity")
                continue
            deduction = min(required, Fraction(str(pantry[0].quantity)))
        for name, actual, correct in (
            ("required_quantity", line.required_quantity, required),
            ("pantry_deduction", line.pantry_deduction, deduction),
            ("remaining_quantity", line.remaining_quantity, required - deduction),
        ):
            if not isfinite(actual) or Fraction(str(actual)) != correct:
                errors.add(name)
        # Validate against recomputed demand only after checking exact serialization.
        remaining = required - deduction
        if not isfinite(line.remaining_quantity) or Fraction(str(line.remaining_quantity)) != remaining:
            continue
        errors.update(validate_packages(ingredient, line.remaining_quantity, unit, line.purchase, problem.products))
        for allocation in line.purchase.allocations:
            matches = [p for p in problem.products if p.product_id == allocation.product_id]
            if len(matches) == 1 and isfinite(matches[0].price_sgd) and isinstance(allocation.packages, int):
                total += Fraction(str(matches[0].price_sgd)) * allocation.packages
    if (
        result.purchase_total_sgd is None
        or not isfinite(result.purchase_total_sgd)
        or (Fraction(str(result.purchase_total_sgd)) != total)
    ):
        errors.add("purchase_total")
    if problem.budget_is_hard and problem.purchase_budget_sgd is not None:
        if not isfinite(problem.purchase_budget_sgd) or total > Fraction(str(problem.purchase_budget_sgd)):
            errors.add("purchase_budget")
    return tuple(sorted(errors))
