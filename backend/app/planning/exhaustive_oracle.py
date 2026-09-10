"""Exhaustive recipe-assignment oracle for small developer packets.

The shopping policy is fixed to the existing reference builder. This does not
optimize combinations of different package products and is not a production API.
"""

from dataclasses import dataclass
from itertools import product
from math import prod
from typing import Literal

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.input_audit import require_finite_problem
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class OracleResult:
    status: Literal["optimal_for_fixed_shopping_policy", "no_valid_assignment", "needs_data", "limit_exceeded"]
    total_combinations: int
    checked_combinations: int
    feasible_combinations: int
    unknown_combinations: int
    best_choices: tuple[tuple[str, str], ...]
    best_loss: float | None


def exhaustive_assignments(
    problem: FinalPlanningProblem, *, max_combinations: int = 10000, scoring_policy: WholePlanPolicy | None = None
) -> OracleResult:
    """Enumerate raw recipe candidates without beam filtering, pruning or dominance.

    Refuse oversized searches before starting, so a truncated run cannot be
    mistaken for exhaustive evidence. Every completed assignment is validated.
    """
    require_finite_problem(problem)
    if max_combinations < 1:
        raise ValueError("max_combinations must be positive")
    slots = sorted(problem.slots, key=FinalScopeReferencePlanner._slot_key)
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    domains = [
        tuple(sorted(recipes)) + ((None,) if not slot.required and slot.locked_recipe_id is None else ())
        for slot in slots
    ]
    total = prod(len(domain) for domain in domains)
    if total > max_combinations:
        return OracleResult("limit_exceeded", total, 0, 0, 0, (), None)
    builder = FinalScopeReferencePlanner()
    validator = FinalPlanningValidator()
    feasible = unknown = checked = 0
    best = None
    for combination in product(*domains):
        choices = tuple(
            (slot.slot_id, recipe) for slot, recipe in zip(slots, combination, strict=True) if recipe is not None
        )
        assignments = [PlanningAssignment(slot_id=slot, recipe_id=recipe) for slot, recipe in choices]
        shopping = builder._build_shopping(problem, assignments)
        report = validator.validate(problem, assignments, shopping)
        checked += 1
        if report.status == "indeterminate":
            unknown += 1
        if report.status != "passed":
            continue
        feasible += 1
        loss = 0.0
        previous = []
        for slot, recipe_id in zip(slots, combination, strict=True):
            if recipe_id is None:
                continue
            loss += local_recipe_loss(
                recipes[recipe_id],
                max_time_minutes=slot.max_time_minutes,
                health_preferences=problem.health_preferences,
            )
            loss += 0.1 * previous.count(recipe_id)
            loss += 0.35 if previous and previous[-1] == recipe_id else 0.0
            previous.append(recipe_id)
        if scoring_policy:
            loss = score_plan(problem, assignments, scoring_policy).total_loss
        key = (loss, choices)
        if best is None or key < best:
            best = key
    status = "needs_data" if unknown else "optimal_for_fixed_shopping_policy" if best else "no_valid_assignment"
    return OracleResult(status, total, checked, feasible, unknown, best[1] if best else (), best[0] if best else None)
