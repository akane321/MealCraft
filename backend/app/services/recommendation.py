from app.planning.grocery_estimator import GroceryEstimator
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.repositories.recipe import RecipeRepository
from app.schemas.recommendation import (
    ExcludedRecipeResponse,
    RecipeRecommendationCollectionResponse,
    RecipeRecommendationRequest,
)


class RecipeRecommendationService:
    def __init__(
        self,
        repository: RecipeRepository,
        grocery_estimator: GroceryEstimator,
        engine: RecipeRecommendationEngine | None = None,
    ) -> None:
        self.repository = repository
        self.grocery_estimator = grocery_estimator
        self.engine = engine or RecipeRecommendationEngine()

    def recommend(self, constraints: RecipeRecommendationRequest) -> RecipeRecommendationCollectionResponse:
        recipes = self.repository.list_for_recommendation()
        recommendations, excluded = self.engine.recommend(recipes, constraints)
        warnings: list[str] = []
        recipes_by_id = {recipe.id: recipe for recipe in recipes}
        enriched = []

        for recommendation in recommendations:
            recipe = recipes_by_id[recommendation.recipe.id]
            estimate = self.grocery_estimator.estimate(recipe, constraints)
            for warning in estimate.warnings:
                if warning not in warnings:
                    warnings.append(warning)

            budget = constraints.budget_per_meal_sgd
            if budget is not None and estimate.within_budget is False:
                excluded.append(
                    ExcludedRecipeResponse(
                        id=recipe.id,
                        slug=recipe.slug,
                        title=recipe.title,
                        reasons=[
                            f"Estimated ingredient-use cost S${estimate.consumed_total_sgd:.2f} "
                            f"is above the S${budget:.2f} meal budget."
                        ],
                    )
                )
                continue

            reasons = list(recommendation.reasons)
            if estimate.consumed_total_sgd is not None:
                reasons.append(
                    f"Estimated ingredient-use cost is S${estimate.consumed_total_sgd:.2f}; "
                    f"buying the required packages costs S${estimate.purchase_total_sgd:.2f}."
                )
            enriched.append(
                recommendation.model_copy(
                    update={
                        "reasons": reasons,
                        "grocery_estimate": estimate,
                    }
                )
            )

        if constraints.pricing_mode == "fixture":
            warnings.append(
                "Stable fixture prices are shown for reproducible planning; select live pricing to query FairPrice."
            )
        if constraints.budget_per_meal_sgd is not None and any(
            item.grocery_estimate is not None and not item.grocery_estimate.complete for item in enriched
        ):
            warnings.append("Budget could not be enforced for recipes with incomplete product mappings.")

        excluded.sort(key=lambda item: item.id)

        return RecipeRecommendationCollectionResponse(
            recommendations=enriched,
            excluded=excluded,
            warnings=warnings,
        )
