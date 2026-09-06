"""Transparent baseline selectors used by the evaluation workbench."""

from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.recommendation import RecipeRecommendationResponse


def greedy_repeat_selector(
    recommendations: list[RecipeRecommendationResponse],
    constraints: WeeklyMealPlanRequest,
) -> tuple[list[RecipeRecommendationResponse], list[str]]:
    """Repeat the top-ranked eligible recipe for every day.

    This deliberately weak baseline applies the same upstream hard filters as
    MealCraft, but has no weekly-budget look-ahead and no diversity policy.
    """
    if not recommendations:
        return [], ["No recipes satisfy the supplied hard constraints."]
    return [recommendations[0] for _ in range(constraints.day_count)], []


def strong_rule_only_selector(
    recommendations: list[RecipeRecommendationResponse],
    constraints: WeeklyMealPlanRequest,
) -> tuple[list[RecipeRecommendationResponse], list[str]]:
    """Apply a credible fixed rule without Agent or learned orchestration.

    Candidates have already passed the same deterministic hard filters. This
    selector prefers lower ingredient-use cost, then shorter cooking time, then
    the existing transparent recommendation score, while avoiding adjacent
    repetition whenever an alternative exists.
    """
    if not recommendations:
        return [], ["No recipes satisfy the supplied hard constraints."]

    def priority(item: RecipeRecommendationResponse) -> tuple[float, int, float, int]:
        estimate = item.grocery_estimate
        consumed_cost = estimate.consumed_total_sgd if estimate is not None else None
        return (
            consumed_cost if consumed_cost is not None else float("inf"),
            item.recipe.total_time_minutes,
            -item.total_score,
            item.recipe.id,
        )

    ordered = sorted(recommendations[:20], key=priority)
    selected: list[RecipeRecommendationResponse] = []
    previous_id: int | None = None
    for _ in range(constraints.day_count):
        candidates = [item for item in ordered if item.recipe.id != previous_id]
        chosen = (candidates or ordered)[0]
        selected.append(chosen)
        previous_id = chosen.recipe.id

    warnings: list[str] = []
    if len(ordered) == 1:
        warnings.append("Only one eligible recipe was available, so consecutive repetition could not be avoided.")
    return selected, warnings
