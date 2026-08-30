from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.recipe import RecipeRepository
from app.schemas.recipe import RecipeCollectionResponse, RecipeDetailResponse
from app.services.recipe import RecipeService

router = APIRouter(prefix="/recipes", tags=["recipes"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_recipe_service(database: DatabaseDependency) -> RecipeService:
    return RecipeService(RecipeRepository(database))


RecipeServiceDependency = Annotated[RecipeService, Depends(get_recipe_service)]


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
