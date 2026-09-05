from __future__ import annotations

from app.schemas.planning_v2 import PlanningRecipeCandidate

SODIUM_REFERENCE_MG = 2000.0
ENERGY_REFERENCE_KCAL = 2000.0
SODIUM_RELAXATION_MULTIPLIER = 2.0


def energy_proportional_sodium_benchmark(calories_kcal: float) -> float:
    """Return a general dietary reference for preference scoring, not a prescription."""
    return SODIUM_REFERENCE_MG * calories_kcal / ENERGY_REFERENCE_KCAL


def flexible_upper_loss(actual: float, benchmark: float, multiplier: float = 2.0) -> float:
    if benchmark <= 0:
        return 0.0 if actual <= 0 else 1.0
    if actual <= benchmark:
        return 0.0
    upper = benchmark * multiplier
    if upper <= benchmark:
        return 1.0
    return min(1.0, (actual - benchmark) / (upper - benchmark))


def local_recipe_loss(
    recipe: PlanningRecipeCandidate,
    *,
    max_time_minutes: int | None,
    health_preferences: list[str],
) -> float:
    """A transparent local score for the scaffold, not the final weekly objective."""
    losses: list[float] = []
    if max_time_minutes:
        losses.append(min(1.0, recipe.total_time_minutes / max_time_minutes))
    if "low-sodium" in health_preferences:
        benchmark = energy_proportional_sodium_benchmark(recipe.nutrients_per_serving.calories_kcal)
        losses.append(
            flexible_upper_loss(
                recipe.nutrients_per_serving.sodium_mg,
                benchmark,
                SODIUM_RELAXATION_MULTIPLIER,
            )
        )
    return sum(losses) / len(losses) if losses else 0.0
