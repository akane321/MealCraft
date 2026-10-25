from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import CurrentHouseholdCreatePlanCsrfDependency
from app.core.config import Settings, get_settings
from app.core.runtime_config import runtime_value
from app.data.ingredient_hierarchy import expand_exclusions
from app.db.session import get_db_session
from app.models.recipe import Ingredient
from app.repositories.household import HouseholdProfileRepository
from app.services.ingredient_substitutions import (
    OpenAISubstituteGenerator,
    SafeSubstitute,
    filter_safe_substitutes,
    reviewed_ingredient_mapper,
)

router = APIRouter(prefix="/ingredient-substitutions", tags=["ingredient substitutions"])


class SubstituteReviewRequest(BaseModel):
    source_ingredient: str = Field(min_length=1, max_length=160)
    candidates: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=1, max_length=12)
    requires_halal: bool


class SubstituteSuggestionRequest(BaseModel):
    source_ingredient: str = Field(min_length=1, max_length=160)
    use_context: str | None = Field(default=None, max_length=500)
    requires_halal: bool


class SubstituteReviewResponse(BaseModel):
    safe_candidates: list[SafeSubstitute]


@router.post("/review", response_model=SubstituteReviewResponse)
def review_substitute_candidates(
    payload: SubstituteReviewRequest,
    database: Annotated[Session, Depends(get_db_session)],
    current: CurrentHouseholdCreatePlanCsrfDependency,
) -> SubstituteReviewResponse:
    """Filter proposed substitutions through the active household's hard safety constraints."""
    return _filter_for_household(
        payload.source_ingredient,
        payload.candidates,
        requires_halal=payload.requires_halal,
        database=database,
        current=current,
    )


@router.post("/suggest", response_model=SubstituteReviewResponse)
def suggest_safe_substitutes(
    payload: SubstituteSuggestionRequest,
    database: Annotated[Session, Depends(get_db_session)],
    current: CurrentHouseholdCreatePlanCsrfDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SubstituteReviewResponse:
    """Generate possible ingredient swaps, then expose only catalog-verified safe options."""
    if runtime_value("agent_parser_provider", settings, database) != "openai" or settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingredient substitution suggestions require an OpenAI API key",
        )
    try:
        candidates = OpenAISubstituteGenerator(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=runtime_value("openai_timeout_seconds", settings, database),
        ).suggest(payload.source_ingredient, use_context=payload.use_context)
    except (APIError, ValueError, TimeoutError, ConnectionError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingredient substitution suggestions are temporarily unavailable",
        ) from error
    return _filter_for_household(
        payload.source_ingredient,
        candidates,
        requires_halal=payload.requires_halal,
        database=database,
        current=current,
    )


def _filter_for_household(
    source_ingredient: str,
    candidate_names: list[str],
    *,
    requires_halal: bool,
    database: Session,
    current,
) -> SubstituteReviewResponse:
    household_id = current.active_membership.household_id
    profiles = HouseholdProfileRepository(database, household_id=household_id)
    profile = profiles.get_current()
    version = HouseholdProfileRepository.current_version(profile) if profile else None
    # With no named eater, an ingredient suggestion must not bypass any member's diet.
    # Ingredient records do not certify these diets yet, so do not label a suggestion safe.
    if version and version.dietary_preferences:
        return SubstituteReviewResponse(safe_candidates=[])
    allergens = list(version.allergens) if version else []
    if version:
        allergens.extend(item for member in version.members for item in member.get("allergens", []))
    excluded = list(version.excluded_ingredients) if version else []

    mapper = reviewed_ingredient_mapper()
    source_match = mapper.resolve(source_ingredient)
    if source_match.canonical_id is None:
        return SubstituteReviewResponse(safe_candidates=[])

    matches = {mapper.resolve(name).canonical_id for name in candidate_names}
    matches.discard(source_match.canonical_id)
    matches.discard(None)
    catalog = list(database.scalars(select(Ingredient).where(Ingredient.normalized_name.in_(matches))))
    expanded_exclusions = expand_exclusions([*excluded, source_match.canonical_id])
    safe = filter_safe_substitutes(
        catalog,
        household_allergens=allergens,
        excluded_ingredients=expanded_exclusions,
        requires_halal=requires_halal,
    )
    return SubstituteReviewResponse(safe_candidates=safe)
