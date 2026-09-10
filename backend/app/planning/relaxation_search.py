"""Evaluate caller-declared non-safety relaxations without changing the request."""

from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Literal

from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.schemas.planning_v2 import FinalPlanningProblem


@dataclass(frozen=True)
class RelaxationChange:
    change_id: str
    field: Literal["time_limit", "purchase_budget"]
    value: float
    cost: float
    slot_id: str | None = None


@dataclass(frozen=True)
class RelaxationResult:
    status: str
    changes: tuple[RelaxationChange, ...]
    total_cost: float | None
    witness: tuple[tuple[str, str], ...]
    evaluated_sets: int
    shopping_policy: str = "reference-single-product"


def propose_relaxations(
    problem: FinalPlanningProblem,
    options: tuple[RelaxationChange, ...],
    *,
    max_options: int = 8,
    max_combinations: int = 10000,
    mixed_packages: bool = False,
    max_package_combinations: int = 100000,
) -> RelaxationResult:
    """Find minimum declared cost within supplied options and fixed shopping policy.

    The caller supplies permitted changes and costs. No defaults, allergy changes,
    dietary changes or automatic application are supported. Incomplete enumeration
    cannot certify minimality. Conflicting changes to one field are not combined.
    """
    for limit in (max_options, max_combinations, max_package_combinations):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Search limits must be positive integers")
    policy = "offline-mixed-shopping-v1" if mixed_packages else "reference-single-product"
    if len(options) > max_options:
        return RelaxationResult("limit_exceeded", (), None, (), 0, policy)
    if len({option.change_id for option in options}) != len(options):
        raise ValueError("Change IDs must be unique")
    slots = {s.slot_id: s for s in problem.slots}
    for option in options:
        if not isfinite(option.cost) or option.cost < 0 or not isfinite(option.value):
            raise ValueError("Finite nonnegative costs and finite values are required")
        if option.field == "time_limit":
            slot = slots.get(option.slot_id)
            if slot is None or slot.max_time_minutes is None or option.value <= slot.max_time_minutes:
                raise ValueError("Time relaxation must increase an existing slot limit")
            if int(option.value) != option.value:
                raise ValueError("Time limit must be an integer")
            if option.value > 360:
                raise ValueError("Time limit exceeds the schema range")
        elif option.field == "purchase_budget":
            if (
                option.slot_id is not None
                or problem.purchase_budget_sgd is None
                or option.value <= problem.purchase_budget_sgd
            ):
                raise ValueError("Budget relaxation must increase an existing budget")
        else:
            raise ValueError("Only declared time and purchase-budget relaxations are supported")
    ordered = sorted(options, key=lambda option: option.change_id)
    sets = []
    for size in range(len(ordered) + 1):
        for subset in combinations(ordered, size):
            keys = [(option.field, option.slot_id) for option in subset]
            if len(set(keys)) == len(keys):
                sets.append(subset)
    sets.sort(key=lambda subset: (sum(o.cost for o in subset), tuple(o.change_id for o in subset)))
    evaluated = 0
    unknown = False
    for subset in sets:
        data = problem.model_dump()
        for option in subset:
            if option.field == "purchase_budget":
                data["purchase_budget_sgd"] = option.value
            else:
                for slot in data["slots"]:
                    if slot["slot_id"] == option.slot_id:
                        slot["max_time_minutes"] = int(option.value)
        candidate = FinalPlanningProblem.model_validate(data)
        result = (
            exhaustive_mixed_plan(
                candidate, max_assignments=max_combinations, max_package_combinations=max_package_combinations
            )
            if mixed_packages
            else exhaustive_assignments(candidate, max_combinations=max_combinations)
        )
        evaluated += 1
        if result.status in ("needs_data", "limit_exceeded", "incomplete_evidence"):
            unknown = True
        if result.best_loss is not None:
            status = "minimal_in_declared_options" if not unknown else "candidate_without_minimality_proof"
            return RelaxationResult(status, subset, sum(o.cost for o in subset), result.best_choices, evaluated, policy)
    return RelaxationResult(
        "incomplete_evidence" if unknown else "no_solution_in_declared_options", (), None, (), evaluated, policy
    )
