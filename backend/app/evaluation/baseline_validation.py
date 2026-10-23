"""Hand a baseline's plan to the product's independent validator (02-baselines.md section 3.1 item 4).

A baseline names dishes, not catalog recipes, so each dish becomes a one-off recipe candidate built from its
mapped lines and the frozen facts, inside the episode's own planning problem (`multidish_runner.build_problem`
on the gold constraints, the same problem every arm is judged against). `FinalPlanningValidator` then checks
it exactly as it checks MealCraft: allergens, exclusions, time, roles, repetition, shopping and budget.

What the validator cannot see is added as its own check, never guessed:

- `allergen_unknown`: a dish with a line whose allergen status is unknown, in a household with allergens
  (ADR-0069 section 3: unknown is unsafe);
- `dish_coverage`: a dish under the 90% gram threshold (ADR-0074 section 2);
- `unmapped_lines`: lines the validator never saw, so exclusions and the budget cannot be confirmed; a budget
  the validator passed becomes indeterminate;
- `dietary_requirement`: a baseline dish carries no dietary tags, so a failed diet check means "not shown",
  and is indeterminate.

The two bases (ADR-0074 section 2) read the one report:

- strict: the plan passes only when every check passed;
- coverage-adjusted: the plan passes when no hard check failed; the indeterminate checks are listed apart.

Not modelled: nutrition bands (no episode of the multi-dish protocol states one, so a dish whose nutrition is
unknown is given zeros only where no band could read them; `validate_baseline_plan` refuses a problem with bands).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.evaluation.baseline_mapping import DishCoverage, PlanCoverage
from app.evaluation.baseline_recomputation import (
    NUTRIENT_FIELDS,
    IngredientEvaluationFacts,
    dish_nutrition_per_serving,
    line_allergens,
)
from app.evaluation.baseline_verification import DEFAULT_COVERAGE_THRESHOLD, dish_verifiable
from app.evaluation.multidish_runner import build_problem, gold_constraints
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningConstraintCheck,
    PlanningProductOption,
    PlanningRecipeCandidate,
    PlanningSlot,
    PlanningValidationReport,
)


@dataclass(frozen=True)
class BaselineValidation:
    report: PlanningValidationReport
    strict_passed: bool
    adjusted_passed: bool
    # Checks the coverage-adjusted basis set aside: their codes, with the scope they were raised for.
    unverified: tuple[tuple[str, str | None], ...]


def episode_problem(episode: dict, products: list[PlanningProductOption]) -> FinalPlanningProblem:
    """The episode's gold problem, priced on the whole frozen snapshot: a baseline never saw the episode's pool."""
    return build_problem(episode, gold_constraints(episode)).model_copy(update={"products": products})


def _candidate(
    recipe_id: str, dish: DishCoverage, slot: PlanningSlot | None, facts: Mapping[str, IngredientEvaluationFacts]
) -> tuple[PlanningRecipeCandidate | None, bool]:
    """(the dish as a recipe the validator reads, or None when no line mapped; whether its allergens are known)."""
    allergens: set[str] = set()
    complete = True
    for mapping in dish.mappings:
        found, known = line_allergens(mapping, facts)
        allergens |= found
        complete = complete and known
    lines = [item for item in dish.mappings if item.mapped]
    if not lines:
        return None, complete
    role = next((r for r in (slot.composition or []) if r.role_id == dish.role_id), None) if slot else None
    nutrition = dish_nutrition_per_serving(dish, facts) or dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    candidate = PlanningRecipeCandidate.model_validate(
        {
            "recipe_id": recipe_id,
            "title": dish.name[:240],
            "servings": min(24, max(1, round(dish.servings))),
            "allowed_meal_types": ["breakfast", "lunch", "dinner", "snack"],
            "total_time_minutes": min(720, dish.cooking_time_minutes),
            # The role the baseline says the dish fills decides its course: the claim is checked elsewhere.
            "course": role.courses[0] if role and role.courses else "main",
            "meal_role": role.meal_roles[0] if role and role.meal_roles else None,
            "allergens": sorted(allergens),
            "ingredients": [{"ingredient_id": m.ingredient_id, "quantity": m.quantity_g, "unit": "g"} for m in lines],
            "nutrients_per_serving": nutrition,
        }
    )
    return candidate, complete


def _check(code: str, detail: str, scope_id: str | None, status: str = "indeterminate") -> PlanningConstraintCheck:
    return PlanningConstraintCheck(code=code, status=status, scope_id=scope_id, detail=detail)


def validate_baseline_plan(
    episode: dict,
    coverage: PlanCoverage,
    *,
    ingredient_facts: Mapping[str, IngredientEvaluationFacts],
    frozen_products: list[PlanningProductOption],
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> BaselineValidation:
    problem = episode_problem(episode, frozen_products)
    if problem.nutrition_bands:
        raise ValueError("baseline validation does not model nutrition bands yet")
    slots = {slot.slot_id: slot for slot in problem.slots}
    recipes: list[PlanningRecipeCandidate] = []
    assignments: list[PlanningAssignment] = []
    extra: list[PlanningConstraintCheck] = []
    for index, dish in enumerate(coverage.dishes):
        scope = f"{dish.slot_id}:{dish.role_id or 'dish'}:{index}"
        candidate, allergens_known = _candidate(
            f"baseline-dish-{index}", dish, slots.get(dish.slot_id), ingredient_facts
        )
        if not allergens_known and problem.allergens:
            extra.append(_check("allergen_unknown", f"{dish.name}: a line's allergen status is unknown.", scope))
        if not dish_verifiable(dish, threshold):
            extra.append(_check("dish_coverage", f"{dish.name}: {dish.coverage:.0%} of its grams map.", scope))
        if any(not item.mapped for item in dish.mappings):
            extra.append(_check("unmapped_lines", f"{dish.name}: unmapped lines were not validated.", scope))
        if candidate is None:
            extra.append(_check("dish_unreadable", f"{dish.name}: no line mapped.", scope, "failed"))
            continue
        recipes.append(candidate)
        assignments.append(
            PlanningAssignment(slot_id=dish.slot_id, recipe_id=candidate.recipe_id, role_id=dish.role_id)
        )

    if not recipes:
        report = PlanningValidationReport(
            status="failed",
            hard_failure_count=1,
            indeterminate_count=0,
            checks=[*extra, _check("empty_plan", "No dish could be validated.", None, "failed")],
            purchase_total_sgd=0,
            catalog_version=problem.catalog_version,
            product_snapshot_version=problem.product_snapshot_version,
            policy_version=problem.policy_version,
        )
        return BaselineValidation(report, False, False, ())

    problem = problem.model_copy(update={"recipes": recipes})
    planner = FinalScopeReferencePlanner()
    shopping = planner._build_shopping(problem, [item for item in assignments if item.slot_id in slots])
    report = planner.validator.validate(problem, assignments, shopping)
    has_unmapped = any(check.code == "unmapped_lines" for check in extra)
    checks = []
    for check in report.checks:
        if check.code == "dietary_requirement" and check.status == "failed":
            check = check.model_copy(update={"status": "indeterminate", "detail": f"{check.detail} (dish has no tags)"})
        if check.code == "purchase_budget" and check.status == "passed" and has_unmapped:
            check = check.model_copy(update={"status": "indeterminate", "margin": None})
        checks.append(check)
    checks.extend(extra)
    hard_failures = sum(check.status == "failed" and check.hard for check in checks)
    indeterminate = sum(check.status == "indeterminate" for check in checks)
    status = "failed" if hard_failures else "indeterminate" if indeterminate else "passed"
    report = report.model_copy(
        update={
            "status": status,
            "checks": checks,
            "hard_failure_count": hard_failures,
            "indeterminate_count": indeterminate,
        }
    )
    unverified = tuple((check.code, check.scope_id) for check in checks if check.status == "indeterminate")
    return BaselineValidation(report, status == "passed", hard_failures == 0, unverified)
