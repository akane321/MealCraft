"""Reorder-only feedback adapter for the offline one-dish reference path."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.planning.constraint_compiler import compile_search_domains
from app.planning.developer_experiments import digest
from app.planning.diversity import diversity_loss, permits_extension
from app.planning.feedback_ranking import FeedbackEvent, rank_candidates
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss, meal_affinity_loss
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.meal_composition import require_one_dish_slots
from app.planning.nutrition_scope import nutrition_guard_loss
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


class FeedbackPlanDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1)
    source: Literal["synthetic", "developer"]
    problem: FinalPlanningProblem
    events: list[FeedbackEvent]
    scope_id: str = Field(min_length=1)
    decision_at: AwareDatetime


def plan_with_feedback(problem, events, *, scope_id, decision_at, enabled=False):
    """Reorder compiler-eligible recipes; the final validator still decides acceptance.

    Scope is supplied by a future authenticated caller, not authorized here.
    Uses experimental cooked-share ranking, not a trained personalized model.
    The decision time applies to the whole planning request.
    """
    if type(enabled) is not bool or not isinstance(scope_id, str) or not scope_id.strip():
        raise ValueError("Ranking requires a boolean switch and a nonempty scope")
    rank_candidates([], events, scope_id=scope_id, decision_at=decision_at, enabled=enabled)
    packet = problem.model_copy(deep=True)
    require_one_dish_slots(packet)
    domains = {d.slot_id: d for d in compile_search_domains(packet).slots}
    recipes = {r.recipe_id: r for r in packet.recipes}
    assignments, ranking = [], []
    reference = FinalScopeReferencePlanner()
    for slot in sorted(packet.slots, key=reference._slot_key):
        domain = domains[slot.slot_id]
        if not domain.must_assign:
            continue
        previous = [a.recipe_id for a in assignments]
        candidates = [r for r in domain.eligible_recipe_ids if permits_extension(packet, previous, r)]

        def score(recipe_id, slot=slot, previous=previous):
            recipe = recipes[recipe_id]
            return (
                local_recipe_loss(
                    recipe, max_time_minutes=slot.max_time_minutes, health_preferences=packet.health_preferences
                )
                + meal_affinity_loss(recipe, slot.meal_type)
                + nutrition_guard_loss(packet, recipe)
                + diversity_loss(packet, previous, recipe_id),
                recipe_id,
            )

        eligible = sorted(candidates, key=score)
        order = rank_candidates(eligible, events, scope_id=scope_id, decision_at=decision_at, enabled=enabled)
        ranking.append({"slot_id": slot.slot_id, "eligible": eligible, **order})
        if order["order"]:
            assignments.append(PlanningAssignment(slot_id=slot.slot_id, recipe_id=order["order"][0]))
    shopping = reference._build_shopping(packet, assignments)
    audit = FinalPlanningValidator().validate(packet, assignments, shopping)
    return {
        "input_sha256": digest(packet.model_dump(mode="json")),
        "feedback_sha256": digest([e.model_dump(mode="json") for e in events]),
        "scope_id": scope_id,
        "decision_at": decision_at.isoformat(),
        "enabled": enabled,
        "status": {"passed": "feasible", "failed": "candidate_rejected", "indeterminate": "needs_data"}[audit.status],
        "assignments": [a.model_dump(mode="json") for a in assignments],
        "shopping": [s.model_dump(mode="json") for s in shopping],
        "audit": audit.model_dump(mode="json"),
        "ranking": ranking,
        "algorithm_version": "greedy-feedback-developer-v1",
        "persistable": False,
    }
