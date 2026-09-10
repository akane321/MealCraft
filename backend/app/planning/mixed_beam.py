"""Offline beam completion with mixed packages; public V2 output is unchanged."""

from dataclasses import dataclass

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.mixed_shopping import MixedShoppingResult, build_mixed_shopping
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class MixedBeamResult:
    status: str
    choices: tuple[tuple[str, str], ...] = ()
    loss: float | None = None
    shopping: MixedShoppingResult | None = None
    expansions: int = 0
    beam_pruned: bool = False
    expansion_limit_reached: bool = False
    unresolved_candidates: int = 0
    catalog_version: str = ""
    product_snapshot_version: str = ""
    policy_version: str = ""
    repair_choices: tuple[tuple[str, str], ...] = ()


def solve_mixed_beam(
    problem: FinalPlanningProblem,
    *,
    limits: BeamLimits | None = None,
    scoring_policy: WholePlanPolicy | None = None,
    max_package_combinations: int = 100000,
) -> MixedBeamResult:
    search = BeamPlanner(limits, scoring_policy).search_candidates(problem)
    best = None
    best_shopping = None
    unresolved = 0
    repair = None
    for state in search.states:
        assignments = [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in state.choices]
        shopping = build_mixed_shopping(problem, assignments, max_combinations=max_package_combinations)
        if shopping.status not in ("feasible", "candidate_rejected"):
            unresolved += 1
        if shopping.status != "feasible":
            if shopping.issues and all(
                issue == "purchase_budget" or issue.startswith("package_needs_data:") for issue in shopping.issues
            ):
                key = (state.loss, state.choices)
                if repair is None or key < repair:
                    repair = key
            continue
        loss = score_plan(problem, assignments, scoring_policy).total_loss if scoring_policy else state.loss
        key = (loss, state.choices)
        if best is None or key < best:
            best, best_shopping = key, shopping
    status = "feasible" if best else "needs_data" if unresolved else "candidate_rejected"
    return MixedBeamResult(
        status,
        best[1] if best else (),
        best[0] if best else None,
        best_shopping,
        search.expansions,
        search.pruned,
        search.exhausted,
        unresolved,
        problem.catalog_version,
        problem.product_snapshot_version,
        problem.policy_version,
        repair[1] if repair and best is None else (),
    )
