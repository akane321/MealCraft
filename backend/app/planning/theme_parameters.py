"""Gate proposed theme weights against existing Planning consumers, default off."""

from dataclasses import dataclass
from math import isfinite

from app.schemas.planning_v2 import FinalPlanningProblem, PlanningDiversityPolicy

SUPPORTED_WEIGHTS = frozenset({"diversity_penalty", "overlap_reward_weight"})
# Named in the design, but not yet defined and consumed as theme parameters.
PENDING_WEIGHTS = frozenset({"effort_rhythm_weight", "cuisine_affinity", "energy_preference"})


@dataclass(frozen=True)
class ThemeApplication:
    problem: FinalPlanningProblem
    trace: dict


def apply_theme_parameters(problem: FinalPlanningProblem, proposal: dict, *, enabled: bool = False) -> ThemeApplication:
    """Accept only supported numeric soft weights, never model-selected recipes.

    The Agent owns translation from text to a proposal. This boundary does not
    parse language, infer constraints or invent missing ingredient classifications.
    Rejected values and raw theme text are never copied into the trace.
    """
    if any(not isinstance(key, str) for key in proposal):
        raise ValueError("Theme proposal keys must be strings")
    accepted, dropped = {}, []
    for key in sorted(proposal):
        value = proposal[key]
        if not enabled:
            reason = "disabled"
        elif key in PENDING_WEIGHTS:
            reason = "consumer_contract_pending"
        elif key not in SUPPORTED_WEIGHTS:
            reason = "not_a_supported_theme_weight"
        elif type(value) not in (int, float) or not 0 <= value <= 1 or not isfinite(value):
            reason = "expected_finite_number_between_zero_and_one"
        elif problem.diversity_policy is None:
            reason = "classification_policy_missing"
        else:
            accepted[key] = float(value)
            continue
        dropped.append({"field": key, "reason": reason})
    detached = problem.model_copy(deep=True)
    if accepted:
        data = detached.diversity_policy.model_dump()
        data.update(accepted)
        detached.diversity_policy = PlanningDiversityPolicy.model_validate(data)
    return ThemeApplication(
        detached,
        {
            "policy_version": "supported-theme-weights-v1",
            "enabled": enabled,
            "applied_weights": accepted,
            "dropped": dropped,
            "requires_final_validation": True,
        },
    )
