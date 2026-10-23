"""Like, Dislike and "Never again" on a dish, for the whole household (ADR-0087)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import CurrentHouseholdCheckInCsrfDependency, CurrentHouseholdViewDependency
from app.db.session import get_db_session
from app.models.recipe import Recipe
from app.repositories.recipe_feedback import RecipeFeedbackRepository
from app.schemas.catalog_tags import FeedbackKind
from app.schemas.recipe_feedback import (
    RecipeFeedbackCollectionResponse,
    RecipeFeedbackItem,
    RecipeFeedbackResponse,
    RecipeFeedbackUpdate,
)
from app.schemas.recommendation import NEVER_AGAIN_LIMIT

router = APIRouter(prefix="/feedback/recipes", tags=["feedback"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def _repository(database: Session, current) -> RecipeFeedbackRepository:
    return RecipeFeedbackRepository(database, household_id=current.active_membership.household_id)


@router.get("", response_model=RecipeFeedbackCollectionResponse)
def list_recipe_feedback(
    database: DatabaseDependency,
    current: CurrentHouseholdViewDependency,
    kind: FeedbackKind | None = None,
) -> RecipeFeedbackCollectionResponse:
    """The household's dishes in their current state, latest first; `kind=never_again` is the profile's list."""
    return RecipeFeedbackCollectionResponse(
        items=[
            RecipeFeedbackItem(
                recipe_id=recipe.id, slug=recipe.slug, title=recipe.title, kind=row.kind, created_at=row.created_at
            )
            for recipe, row in _repository(database, current).listed(kind)
        ]
    )


@router.put("/{recipe_id}", response_model=RecipeFeedbackResponse)
def set_recipe_feedback(
    recipe_id: int,
    update: RecipeFeedbackUpdate,
    database: DatabaseDependency,
    current: CurrentHouseholdCheckInCsrfDependency,
) -> RecipeFeedbackResponse:
    """Any member who checks meals in may press any of the three; pressing the current state again changes nothing."""
    if database.get(Recipe, recipe_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    repository = _repository(database, current)
    states = repository.states()
    if (
        update.kind == "never_again"
        and states.get(recipe_id) != "never_again"
        and sum(kind == "never_again" for kind in states.values()) >= NEVER_AGAIN_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"At most {NEVER_AGAIN_LIMIT} dishes can be marked Never again.",
        )
    repository.set(recipe_id, update.kind)
    return RecipeFeedbackResponse(recipe_id=recipe_id, kind=update.kind)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_recipe_feedback(
    recipe_id: int,
    database: DatabaseDependency,
    current: CurrentHouseholdCheckInCsrfDependency,
) -> Response:
    """Undo: the dish has no feedback afterwards. Repeating it is safe."""
    _repository(database, current).clear(recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
