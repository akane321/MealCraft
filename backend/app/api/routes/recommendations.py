from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.recipe import RecipeRepository
from app.schemas.recommendation import (
    RecipeRecommendationCollectionResponse,
    RecipeRecommendationRequest,
)
from app.services.recommendation import RecipeRecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_recommendation_service(database: DatabaseDependency) -> RecipeRecommendationService:
    return RecipeRecommendationService(RecipeRepository(database))


RecommendationServiceDependency = Annotated[
    RecipeRecommendationService,
    Depends(get_recommendation_service),
]


@router.post("/recipes", response_model=RecipeRecommendationCollectionResponse)
def recommend_recipes(
    constraints: RecipeRecommendationRequest,
    service: RecommendationServiceDependency,
) -> RecipeRecommendationCollectionResponse:
    return service.recommend(constraints)
