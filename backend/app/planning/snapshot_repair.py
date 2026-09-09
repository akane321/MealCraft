"""Planner-owned bounded snapshot repair. Providers are injected, never scraped here."""

from dataclasses import dataclass
from typing import Protocol

from app.planning.beam_planner import BeamPlanner
from app.schemas.planning_v2 import FinalPlanningProblem, FinalPlanningSolution, PlanningProductOption
from app.schemas.retrieval import RetrievalTrace


@dataclass(frozen=True)
class IngredientDemand:
    ingredient_id: str
    quantity: float
    unit: str


@dataclass(frozen=True)
class ProductSnapshot:
    version: str
    products: tuple[PlanningProductOption, ...]
    trace: RetrievalTrace


class SnapshotProvider(Protocol):
    def retrieve(self, demands: tuple[IngredientDemand, ...]) -> ProductSnapshot: ...


class RetrievalUnavailable(Exception):
    """Provider reports a known external-service failure."""


@dataclass(frozen=True)
class RepairAttempt:
    snapshot_version: str
    planning_status: str
    demands: tuple[IngredientDemand, ...]
    retrieval: RetrievalTrace | None = None
    products: tuple[PlanningProductOption, ...] = ()


@dataclass(frozen=True)
class RepairResult:
    solution: FinalPlanningSolution
    attempts: tuple[RepairAttempt, ...]
    stop_reason: str


def solve_with_repair(
    problem: FinalPlanningProblem,
    provider: SnapshotProvider,
    *,
    max_rounds: int = 2,
    planner: BeamPlanner | None = None,
) -> RepairResult:
    if max_rounds < 0:
        raise ValueError("max_rounds must be nonnegative")
    engine = planner or BeamPlanner()
    current = problem.model_copy(deep=True)
    attempts = []
    trace = None
    seen = {current.product_snapshot_version}
    for round_index in range(max_rounds + 1):
        solution = engine.solve(current)
        demands = tuple(
            IngredientDemand(line.ingredient_id, line.remaining_quantity, line.unit)
            for line in solution.shopping
            if line.remaining_quantity is not None and line.remaining_quantity > 0 and line.unit is not None
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
            return RepairResult(solution, tuple(attempts), "validated")
        if round_index == max_rounds:
            return RepairResult(solution, tuple(attempts), "repair_limit")
        if not demands or any(line.remaining_quantity is None or line.unit is None for line in solution.shopping):
            return RepairResult(solution, tuple(attempts), "no_normalized_demand")
        try:
            snapshot = provider.retrieve(demands)
        except RetrievalUnavailable:
            return RepairResult(solution, tuple(attempts), "provider_unavailable")
        if not snapshot.version or snapshot.version in seen:
            return RepairResult(solution, tuple(attempts), "snapshot_not_new")
        if snapshot.trace.status != "success":
            attempts.append(RepairAttempt(snapshot.version, "needs_data", demands, snapshot.trace))
            return RepairResult(solution, tuple(attempts), "provider_degraded")
        validate_product_snapshot(snapshot)
        seen.add(snapshot.version)
        # Keep every user constraint, recipe and pantry fact unchanged.
        current = current.model_copy(
            update={
                "products": [p.model_copy(deep=True) for p in snapshot.products],
                "product_snapshot_version": snapshot.version,
            }
        )
        trace = snapshot.trace.model_copy(deep=True)
    raise AssertionError("Unreachable repair state")


def validate_product_snapshot(snapshot: ProductSnapshot) -> None:
    """Check source labels, observation time and packet size for grocery evidence."""
    if snapshot.trace.requested_source != "fairprice":
        raise ValueError("Grocery repair requires FairPrice evidence")
    if snapshot.trace.fetched_at.utcoffset() is None:
        raise ValueError("Snapshot observation time requires a timezone")
    if snapshot.trace.provider_used == "fixture" and snapshot.trace.mode != "fixture":
        raise ValueError("Fixture evidence must not claim live or cache provenance")
    if snapshot.trace.candidate_count != len(snapshot.products):
        raise ValueError("Snapshot candidate count does not match the returned packet")
