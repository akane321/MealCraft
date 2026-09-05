from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.recipe import RecipeRepository
from app.schemas.recipe import RecipeCollectionResponse, RecipeDetailResponse
from app.schemas.retrieval import TutorialRecommendationResponse
from app.services.recipe import RecipeService
from app.services.tutorial import TutorialRecommendationService, create_tutorial_service

router = APIRouter(prefix="/recipes", tags=["recipes"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_recipe_service(database: DatabaseDependency) -> RecipeService:
    return RecipeService(RecipeRepository(database))


RecipeServiceDependency = Annotated[RecipeService, Depends(get_recipe_service)]


def get_tutorial_service(database: DatabaseDependency) -> TutorialRecommendationService:
    return create_tutorial_service(RecipeRepository(database))


TutorialServiceDependency = Annotated[TutorialRecommendationService, Depends(get_tutorial_service)]


@router.get("", response_model=RecipeCollectionResponse)
def list_recipes(
    service: RecipeServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    after_id: Annotated[int | None, Query(ge=0)] = None,
) -> RecipeCollectionResponse:
    return service.list_recipes(after_id=after_id, limit=limit)


@router.get("/{slug}", response_model=RecipeDetailResponse)
def get_recipe(
    service: RecipeServiceDependency,
    slug: Annotated[str, Path(min_length=1, max_length=160)],
) -> RecipeDetailResponse:
    recipe = service.get_recipe(slug)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found",
        )
    return recipe


@router.get("/{slug}/tutorial", response_model=TutorialRecommendationResponse)
def get_recipe_tutorial(
    service: TutorialServiceDependency,
    slug: Annotated[str, Path(min_length=1, max_length=160)],
    live: bool = False,
    language: Annotated[str, Query(min_length=2, max_length=20)] = "en",
) -> TutorialRecommendationResponse:
    recommendation = service.recommend(slug, live=live, language=language)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found",
        )
    return recommendation
