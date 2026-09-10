"""Bounded snapshot refresh that retains mixed-package planning on every round."""

from dataclasses import dataclass

from app.planning.beam_planner import BeamLimits
from app.planning.mixed_beam import MixedBeamResult, solve_mixed_beam
from app.planning.mixed_shopping import derive_mixed_demands
from app.planning.snapshot_repair import (
    IngredientDemand,
    RepairAttempt,
    RetrievalUnavailable,
    SnapshotProvider,
    validate_product_snapshot,
)
from app.planning.whole_plan_scoring import WholePlanPolicy
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class MixedRepairResult:
    solution: MixedBeamResult
    attempts: tuple[RepairAttempt, ...]
    stop_reason: str


def solve_mixed_with_repair(
    problem: FinalPlanningProblem,
    provider: SnapshotProvider,
    *,
    max_rounds: int = 2,
    limits: BeamLimits | None = None,
    scoring_policy: WholePlanPolicy | None = None,
    max_package_combinations: int = 100000,
) -> MixedRepairResult:
    """Refresh a full snapshot only for product evidence or budget failures.

    A feasible frozen plan needs no refresh. The caller owns freshness policy and
    provider transport timeouts. User constraints and pantry facts never change.
    """
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 0:
        raise ValueError("max_rounds must be a nonnegative integer")
    current = problem.model_copy(deep=True)
    attempts = []
    seen = {current.product_snapshot_version}
    trace = None
    for round_index in range(max_rounds + 1):
        solution = solve_mixed_beam(
            current, limits=limits, scoring_policy=scoring_policy, max_package_combinations=max_package_combinations
        )
        choices = solution.choices if solution.status == "feasible" else solution.repair_choices
        quantities, issues = derive_mixed_demands(
            current, [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in choices]
        )
        demands = tuple(
            IngredientDemand(d.ingredient_id, d.remaining_quantity, d.unit)
            for d in quantities
            if d.remaining_quantity > 0
        )
        attempts.append(
            RepairAttempt(
                current.product_snapshot_version,
                solution.status,
                demands,
                trace,
                tuple(p.model_copy(deep=True) for p in current.products),
            )
        )
        if solution.status == "feasible":
            return MixedRepairResult(solution, tuple(attempts), "validated")
        if round_index == max_rounds:
            return MixedRepairResult(solution, tuple(attempts), "repair_limit")
        if not choices or issues or not demands:
            return MixedRepairResult(solution, tuple(attempts), "no_repairable_demand")
        try:
            snapshot = provider.retrieve(demands)
        except RetrievalUnavailable:
            return MixedRepairResult(solution, tuple(attempts), "provider_unavailable")
        if not snapshot.version or snapshot.version in seen:
            return MixedRepairResult(solution, tuple(attempts), "snapshot_not_new")
        if snapshot.trace.status != "success":
            attempts.append(
                RepairAttempt(
                    snapshot.version,
                    "needs_data",
                    demands,
                    snapshot.trace.model_copy(deep=True),
                    tuple(p.model_copy(deep=True) for p in snapshot.products),
                )
            )
            return MixedRepairResult(solution, tuple(attempts), "provider_degraded")
        validate_product_snapshot(snapshot)
        seen.add(snapshot.version)
        current = current.model_copy(
            update={
                "products": [p.model_copy(deep=True) for p in snapshot.products],
                "product_snapshot_version": snapshot.version,
            }
        )
        trace = snapshot.trace.model_copy(deep=True)
    raise AssertionError("Unreachable repair state")
