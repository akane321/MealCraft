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
