"""Slot-local hard constraints for validated, complete Planning V2 packets.

Eligibility is not plan feasibility: scoped nutrition and shopping still require
independent validation. This compiler does not infer missing source facts.
"""

from dataclasses import dataclass

from app.planning.input_audit import require_finite_problem
from app.schemas.planning_v2 import FinalPlanningProblem


@dataclass(frozen=True)
class CandidateEligibility:
    slot_id: str
    recipe_id: str
    rejection_codes: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return not self.rejection_codes


@dataclass(frozen=True)
class SlotCandidates:
    slot_id: str
    must_assign: bool
    eligible_recipe_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompiledConstraints:
    """Search domains and rejection evidence for the supplied candidate packet."""

    decisions: tuple[CandidateEligibility, ...]
    slots: tuple[SlotCandidates, ...]

    @property
    def blocked_slot_ids(self) -> tuple[str, ...]:
        """Required or locked slots with no locally eligible recipe.

        This proves no assignment exists within this candidate packet for these
        slots. It says nothing about recipes outside the packet. Nonempty domains
        also do not prove that aggregate nutrition or budget can be satisfied.
        """
        return tuple(slot.slot_id for slot in self.slots if slot.must_assign and not slot.eligible_recipe_ids)


def compile_search_domains(problem: FinalPlanningProblem) -> CompiledConstraints:
    """Compile once and group candidates for search, preserving every rejection."""
    decisions = compile_constraints(problem)
    candidates: dict[str, list[str]] = {slot.slot_id: [] for slot in problem.slots}
    for decision in decisions:
        if decision.eligible:
            candidates[decision.slot_id].append(decision.recipe_id)
    slots = tuple(
        SlotCandidates(
            slot.slot_id,
            slot.required or slot.locked_recipe_id is not None,
            tuple(candidates[slot.slot_id]),
        )
        for slot in sorted(problem.slots, key=lambda item: item.slot_id)
    )
    return CompiledConstraints(decisions, slots)


def compile_constraints(problem: FinalPlanningProblem) -> tuple[CandidateEligibility, ...]:
    """Return every slot/recipe pair, ordered by stable IDs, without mutation.

    Per-slot nutrition is per person, regardless of household servings. Daily
    and horizon bands cannot be applied independently to each candidate.
    The 1e-6 boundary matches the existing V2 validator's numeric tolerance.
    """
    require_finite_problem(problem)
    result: list[CandidateEligibility] = []
    for slot in sorted(problem.slots, key=lambda item: item.slot_id):
        for recipe in sorted(problem.recipes, key=lambda item: item.recipe_id):
            reasons: set[str] = set()
            if slot.meal_type not in recipe.allowed_meal_types:
                reasons.add("meal_type")
            if slot.locked_recipe_id is not None and recipe.recipe_id != slot.locked_recipe_id:
                reasons.add("locked_slot")
            if slot.max_time_minutes is not None and recipe.total_time_minutes > slot.max_time_minutes:
                reasons.add("time_limit")
            if set(recipe.allergens).intersection(problem.allergens):
                reasons.add("allergen")
            if {item.ingredient_id for item in recipe.ingredients}.intersection(problem.excluded_ingredients):
                reasons.add("excluded_ingredient")
            if not set(problem.dietary_requirements).issubset(recipe.dietary_tags):
                reasons.add("dietary_requirement")
            for band in problem.nutrition_bands:
                if not band.hard or band.scope != "per_slot":
                    continue
                actual = getattr(recipe.nutrients_per_serving, band.metric)
                if band.lower is not None and actual - band.lower < -1e-6:
                    reasons.add(f"nutrition_{band.metric}_lower")
                if band.upper is not None and band.upper - actual < -1e-6:
                    reasons.add(f"nutrition_{band.metric}_upper")
            result.append(CandidateEligibility(slot.slot_id, recipe.recipe_id, tuple(sorted(reasons))))
    return tuple(result)
