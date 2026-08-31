from dataclasses import dataclass
from functools import cache

from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.recommendation import RecipeRecommendationResponse


@dataclass(frozen=True)
class WeeklyCandidate:
    recommendation: RecipeRecommendationResponse

    @property
    def recipe_id(self) -> int:
        return self.recommendation.recipe.id

    @property
    def consumed_cost(self) -> float | None:
        estimate = self.recommendation.grocery_estimate
        return estimate.consumed_total_sgd if estimate is not None else None


class WeeklyPlanSelectionError(ValueError):
    pass


class WeeklyPlanSelector:
    DIVERSITY_PENALTY = 8.0

    def select(
        self,
        recommendations: list[RecipeRecommendationResponse],
        constraints: WeeklyMealPlanRequest,
    ) -> tuple[list[RecipeRecommendationResponse], list[str]]:
        if not recommendations:
            raise WeeklyPlanSelectionError("No recipes satisfy the supplied hard constraints.")

        candidates = [WeeklyCandidate(item) for item in recommendations[:20]]
        warnings: list[str] = []
        if len(candidates) == 1:
            warnings.append("Only one eligible recipe was available, so consecutive repetition could not be avoided.")

        budget_enabled = constraints.weekly_budget_sgd is not None and all(
            item.consumed_cost is not None for item in candidates
        )
        if constraints.weekly_budget_sgd is not None and not budget_enabled:
            warnings.append(
                "The weekly budget could not guide selection because some product mappings were incomplete."
            )

        weekly_budget = constraints.weekly_budget_sgd or 0.0
        used_budget = 0.0
        use_counts: dict[int, int] = {item.recipe_id: 0 for item in candidates}
        selected: list[RecipeRecommendationResponse] = []
        last_recipe_id: int | None = None
        budget_shortfall_reported = False

        for day_index in range(constraints.day_count):
            remaining_days = constraints.day_count - day_index - 1
            choices = [item for item in candidates if item.recipe_id != last_recipe_id]
            if not choices:
                choices = candidates

            choose_lowest_cost = False
            if budget_enabled:
                feasible = [
                    item
                    for item in choices
                    if used_budget
                    + (item.consumed_cost or 0.0)
                    + self._minimum_future_cost(candidates, remaining_days, item.recipe_id)
                    <= weekly_budget + 0.005
                ]
                if feasible:
                    choices = feasible
                else:
                    choose_lowest_cost = True
                    if not budget_shortfall_reported:
                        warnings.append(
                            "No seven-day combination can meet the entered weekly budget; "
                            "the least-cost valid sequence is shown."
                        )
                        budget_shortfall_reported = True

            if choose_lowest_cost:
                chosen = min(
                    choices,
                    key=lambda item: (
                        item.consumed_cost or 0.0,
                        -item.recommendation.total_score,
                        item.recipe_id,
                    ),
                )
            else:
                chosen = max(
                    choices,
                    key=lambda item: (
                        item.recommendation.total_score - use_counts[item.recipe_id] * self.DIVERSITY_PENALTY,
                        -(item.consumed_cost or 0.0),
                        -item.recipe_id,
                    ),
                )
            selected.append(chosen.recommendation)
            use_counts[chosen.recipe_id] += 1
            used_budget += chosen.consumed_cost or 0.0
            last_recipe_id = chosen.recipe_id

        return selected, warnings

    @staticmethod
    def _minimum_future_cost(
        candidates: list[WeeklyCandidate],
        slots: int,
        last_recipe_id: int,
    ) -> float:
        costs = tuple((item.recipe_id, round(item.consumed_cost or 0.0, 2)) for item in candidates)

        @cache
        def solve(remaining: int, previous_id: int) -> float:
            if remaining == 0:
                return 0.0
            choices = [(recipe_id, cost) for recipe_id, cost in costs if recipe_id != previous_id]
            if not choices:
                choices = list(costs)
            return min(cost + solve(remaining - 1, recipe_id) for recipe_id, cost in choices)

        return solve(slots, last_recipe_id)
