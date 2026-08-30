from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.repositories.recipe import RecipeRepository
from app.schemas.recommendation import (
    RecipeRecommendationCollectionResponse,
    RecipeRecommendationRequest,
)


class RecipeRecommendationService:
    def __init__(
        self,
        repository: RecipeRepository,
        engine: RecipeRecommendationEngine | None = None,
    ) -> None:
        self.repository = repository
        self.engine = engine or RecipeRecommendationEngine()

    def recommend(self, constraints: RecipeRecommendationRequest) -> RecipeRecommendationCollectionResponse:
        recipes = self.repository.list_for_recommendation()
        recommendations, excluded = self.engine.recommend(recipes, constraints)
        warnings: list[str] = []

        if constraints.budget_per_meal_sgd is not None:
            warnings.append("Budget was recorded but is not scored until live FairPrice product pricing is connected.")

        return RecipeRecommendationCollectionResponse(
            recommendations=recommendations,
            excluded=excluded,
            warnings=warnings,
        )
