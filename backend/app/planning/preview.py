"""Read-only mixed-planning preview for normalized packets, without persistence."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from fractions import Fraction

from app.planning.beam_planner import BeamLimits
from app.planning.input_audit import InputIssue, audit_problem, require_finite_problem
from app.planning.mixed_beam import MixedBeamResult, solve_mixed_beam
from app.planning.mixed_shopping import validate_mixed_shopping
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class PlanningPreview:
    preview_version: str
    input_sha256: str
    limits: BeamLimits
    max_package_combinations: int
    solution: MixedBeamResult
    input_issues: tuple[InputIssue, ...]
    validation_issues: tuple[str, ...] | None

    @property
    def validated(self) -> bool:
        return self.solution.status == "feasible" and self.validation_issues == ()

    def to_json(self) -> str:
        return json.dumps(
            {**asdict(self), "validated": self.validated}, sort_keys=True, separators=(",", ":"), allow_nan=False
        )


def preview_plan(
    problem: FinalPlanningProblem,
    *,
    limits: BeamLimits | None = None,
    max_package_combinations: int = 100000,
) -> PlanningPreview:
    """Preview a detached packet; never map legacy budgets or infer target scopes.

    The digest identifies normalized input, including list order. It is not an
    authorization token, storage revision, or proof of provenance. Search limits
    are recorded separately; callers must keep the packet for later replay.
    """
    effective_limits = limits or BeamLimits()
    for value in (effective_limits.width, effective_limits.max_expansions, max_package_combinations):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("Preview search limits must be positive integers")
    require_finite_problem(problem)
    packet = FinalPlanningProblem.model_validate(problem.model_dump())
    issues = audit_problem(packet)
    if any(issue.code in ("missing_version", "fractional_cent_price") for issue in issues):
        raise ValueError("Preview requires nonempty versions and whole-cent product prices")
    if packet.purchase_budget_sgd is not None and (Fraction(str(packet.purchase_budget_sgd)) * 100).denominator != 1:
        raise ValueError("Preview budget must use whole cents")
    encoded = json.dumps(packet.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    solution = solve_mixed_beam(packet, limits=effective_limits, max_package_combinations=max_package_combinations)
    validation = None
    if solution.status == "feasible":
        if solution.shopping is None:
            validation = ("missing_shopping",)
        else:
            validation = validate_mixed_shopping(
                packet,
                [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in solution.choices],
                solution.shopping,
            )
        if validation:
            solution = replace(solution, status="candidate_rejected")
    return PlanningPreview(
        "planning-preview-v1", digest, effective_limits, max_package_combinations, solution, issues, validation
    )
