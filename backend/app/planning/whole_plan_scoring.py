"""Versioned experimental whole-plan losses. No medical targets are generated."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite

from app.planning.final_scope_scoring import energy_proportional_sodium_benchmark, flexible_upper_loss
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


@dataclass(frozen=True)
class WholePlanPolicy:
    version: str = "whole-plan-experiment-v1"
    tolerance: float = 1e-6

    def __post_init__(self):
        if not self.version or not isfinite(self.tolerance) or self.tolerance < 0:
            raise ValueError("A version and finite nonnegative tolerance are required")


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    loss: float | None
    weight: float
    reason: str


@dataclass(frozen=True)
class WholePlanScore:
    policy_version: str
    total_loss: float
    components: tuple[ScoreComponent, ...]


def score_plan(
    problem: FinalPlanningProblem, assignments: list[PlanningAssignment], policy: WholePlanPolicy | None = None
) -> WholePlanScore:
    """Score complete assignments; validity must be checked separately first.

    Weights come from the existing problem contract. Inactive dimensions are
    removed from the weighted denominator. Zero active weight gives zero loss.
    Horizon averages follow current validator semantics (dates with chosen meals).
    """
    policy = policy or WholePlanPolicy()
    slots = {slot.slot_id: slot for slot in problem.slots}
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    selected = {}
    for assignment in assignments:
        if assignment.slot_id not in slots or assignment.recipe_id not in recipes or assignment.slot_id in selected:
            raise ValueError("Assignments require unique known slots and known recipes")
        selected[assignment.slot_id] = recipes[assignment.recipe_id]
    selected = dict(sorted(selected.items()))
    if any(
        (slot.required or slot.locked_recipe_id is not None) and slot.slot_id not in selected for slot in problem.slots
    ):
        raise ValueError("Whole-plan scoring requires every mandatory slot")
    components = []

    def add(name, observations, reason):
        weight = getattr(problem.preference_weights, name)
        value = sum(observations) / len(observations) if observations else None
        if value is not None and not isfinite(value):
            value = None
        components.append(ScoreComponent(name, value, weight, reason))

    deviations = []
    for band in problem.nutrition_bands:
        if band.hard:
            continue  # Hard validity cannot be traded for preference points.
        by_day = defaultdict(float)
        values = []
        for slot_id, recipe in sorted(selected.items()):
            value = getattr(recipe.nutrients_per_serving, band.metric)
            values.append(value)
            by_day[slots[slot_id].planned_date] += value
        if band.scope == "per_day":
            values = list(by_day.values())
        elif band.scope == "horizon_average":
            values = [sum(by_day.values()) / len(by_day)] if by_day else []
        scale = max(1.0, *(v for v in (band.lower, band.upper) if v is not None))
        for value in values:
            if not isfinite(value):
                continue
            distance = max(
                0,
                (band.lower - value) if band.lower is not None else 0,
                (value - band.upper) if band.upper is not None else 0,
            )
            deviations.append(min(1.0, max(0.0, distance - policy.tolerance) / scale))
    add(
        "nutrition",
        deviations,
        "Mean normalized deviation outside user-entered soft bands; absent observations masked.",
    )
    counts = Counter(recipe.recipe_id for recipe in selected.values())
    count = len(selected)
    add(
        "variety",
        [(count - len(counts)) / max(1, count - 1)] if count > 1 else [],
        "Repeated selections divided by n-1.",
    )
    times = [
        min(1.0, recipe.total_time_minutes / slots[slot_id].max_time_minutes)
        for slot_id, recipe in selected.items()
        if slots[slot_id].max_time_minutes
    ]
    add("time", times, "Mean cooking time relative to explicit slot limits.")
    used = {item.ingredient_id for recipe in selected.values() for item in recipe.ingredients}
    priority = {item.ingredient_id for item in problem.pantry if item.priority_use}
    add(
        "pantry",
        [len(priority - used) / len(priority)] if priority else [],
        "Fraction of declared priority ingredient IDs unused; no quantity savings claim.",
    )
    health = []
    for preference in sorted(set(problem.health_preferences)):
        if preference == "low-sodium":
            health.extend(
                flexible_upper_loss(
                    r.nutrients_per_serving.sodium_mg,
                    energy_proportional_sodium_benchmark(r.nutrients_per_serving.calories_kcal),
                )
                for r in selected.values()
            )
        else:
            metric = "sugar_g" if preference == "low-sugar" else "calories_kcal"
            catalog = [getattr(r.nutrients_per_serving, metric) for r in problem.recipes]
            if catalog and all(isfinite(v) for v in catalog) and max(catalog) > min(catalog):
                low, high = min(catalog), max(catalog)
                health.extend(
                    (getattr(r.nutrients_per_serving, metric) - low) / (high - low) for r in selected.values()
                )
    add("health", health, "Sodium uses reference curve; sugar/calories use frozen-catalog range, not medical targets.")
    active = [c for c in components if c.loss is not None and c.weight > 0]
    denominator = sum(c.weight for c in active)
    total = sum(c.loss * c.weight for c in active) / denominator if denominator else 0.0
    return WholePlanScore(policy.version, total, tuple(components))


def nutrition_lower_bound(problem, choices, remaining_slots, domains, policy):
    """Admissible contribution of soft nutrition to the whole-plan weighted loss.

    Other component losses are bounded by zero. The denominator uses all positive
    configured weights, so masking can only increase the eventual ratio. Optional
    observations use the maximum possible count and zero lower loss when skipped.
    """
    recipes = {r.recipe_id: r for r in problem.recipes}
    slots = {s.slot_id: s for s in problem.slots}
    dates = {s.planned_date for s in problem.slots}
    chosen = {s: recipes[r] for s, r in choices}
    loss_sum, observation_cap = 0.0, 0
    for band in problem.nutrition_bands:
        if band.hard:
            continue
        scale = max(1.0, *(v for v in (band.lower, band.upper) if v is not None))

        def interval_loss(low, high, band=band, scale=scale):
            if not isfinite(low) or not isfinite(high):
                return 0.0
            distance = max(
                0.0,
                band.lower - high if band.lower is not None else 0.0,
                low - band.upper if band.upper is not None else 0.0,
            )
            return min(1.0, max(0.0, distance - policy.tolerance) / scale)

        if band.scope == "per_slot":
            observation_cap += len(problem.slots)
            for recipe in chosen.values():
                value = getattr(recipe.nutrients_per_serving, band.metric)
                loss_sum += interval_loss(value, value)
            for slot in remaining_slots:
                domain = domains[slot.slot_id]
                if domain.must_assign:
                    values = [
                        getattr(recipes[r].nutrients_per_serving, band.metric) for r in domain.eligible_recipe_ids
                    ]
                    loss_sum += min((interval_loss(v, v) for v in values), default=0.0)
            continue
        groups = [dates] if band.scope == "horizon_average" else [{d} for d in sorted(dates)]
        observation_cap += len(groups)
        if band.scope == "horizon_average" and any(
            not any(s.planned_date == d and domains[s.slot_id].must_assign for s in problem.slots) for d in dates
        ):
            continue
        for group in groups:
            picked = [r for s, r in chosen.items() if slots[s].planned_date in group]
            future = [s for s in remaining_slots if s.planned_date in group]
            if not picked and not any(domains[s.slot_id].must_assign for s in future):
                continue
            low = high = sum(getattr(r.nutrients_per_serving, band.metric) for r in picked)
            for slot in future:
                domain = domains[slot.slot_id]
                values = [getattr(recipes[r].nutrients_per_serving, band.metric) for r in domain.eligible_recipe_ids]
                if not domain.must_assign:
                    values.append(0.0)
                if values:
                    low += min(values)
                    high += max(values)
            divisor = len(dates) if band.scope == "horizon_average" else 1
            loss_sum += interval_loss(low / divisor, high / divisor)
    denominator = sum(problem.preference_weights.model_dump().values())
    if not observation_cap or not denominator:
        return 0.0
    return loss_sum / observation_cap * problem.preference_weights.nutrition / denominator
