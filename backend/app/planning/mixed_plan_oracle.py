"""Small hybrid oracle: raw assignment enumeration plus exact mixed shopping.

CP-SAT optionally solves each package subproblem. Recipe selection is exhaustive,
not a joint CP-SAT formulation. Results certify only this frozen bounded packet.
"""

from dataclasses import dataclass
from itertools import product
from math import prod

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss
from app.planning.input_audit import require_finite_problem
from app.planning.mixed_shopping import MixedShoppingResult, build_mixed_shopping
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class MixedPlanOracleResult:
    status: str
    total_combinations: int
    checked_combinations: int = 0
    unresolved_combinations: int = 0
    best_choices: tuple[tuple[str, str], ...] = ()
    best_loss: float | None = None
    shopping: MixedShoppingResult | None = None
    package_solver: str = "enumeration"


def exhaustive_mixed_plan(
    problem: FinalPlanningProblem,
    *,
    max_assignments: int = 10000,
    max_package_combinations: int = 100000,
    use_cp_sat: bool = False,
    scoring_policy: WholePlanPolicy | None = None,
) -> MixedPlanOracleResult:
    require_finite_problem(problem)
    if isinstance(max_assignments, bool) or not isinstance(max_assignments, int) or max_assignments < 1:
        raise ValueError("max_assignments must be a positive integer")
    slots = sorted(problem.slots, key=FinalScopeReferencePlanner._slot_key)
    recipes = {r.recipe_id: r for r in problem.recipes}
    domains = [
        tuple(sorted(recipes)) + ((None,) if not s.required and s.locked_recipe_id is None else ()) for s in slots
    ]
    total = prod(len(d) for d in domains)
    solver = "cp-sat" if use_cp_sat else "enumeration"
    if total > max_assignments:
        return MixedPlanOracleResult("limit_exceeded", total, package_solver=solver)
    checked = unresolved = 0
    best = None
    best_shopping = None
    for choices in product(*domains):
        assignments = [
            PlanningAssignment(slot_id=s.slot_id, recipe_id=r)
            for s, r in zip(slots, choices, strict=True)
            if r is not None
        ]
        shopping = build_mixed_shopping(
            problem, assignments, max_combinations=max_package_combinations, use_cp_sat=use_cp_sat
        )
        checked += 1
        if shopping.status not in ("feasible", "candidate_rejected"):
            unresolved += 1
            continue
        if shopping.status != "feasible":
            continue
        loss = 0.0
        previous = []
        for slot, recipe_id in zip(slots, choices, strict=True):
            if recipe_id is None:
                continue
            loss += local_recipe_loss(
                recipes[recipe_id],
                max_time_minutes=slot.max_time_minutes,
                health_preferences=problem.health_preferences,
            )
            loss += 0.1 * previous.count(recipe_id) + (0.35 if previous and previous[-1] == recipe_id else 0)
            previous.append(recipe_id)
        if scoring_policy:
            loss = score_plan(problem, assignments, scoring_policy).total_loss
        key = (loss, tuple((a.slot_id, a.recipe_id) for a in assignments))
        if best is None or key < best:
            best, best_shopping = key, shopping
    status = "incomplete_evidence" if unresolved else "optimal_for_frozen_packet" if best else "no_valid_assignment"
    return MixedPlanOracleResult(
        status, total, checked, unresolved, best[1] if best else (), best[0] if best else None, best_shopping, solver
    )
