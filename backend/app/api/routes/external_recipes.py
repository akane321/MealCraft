import hashlib
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import CurrentHouseholdCreatePlanCsrfDependency
from app.core.config import Settings, get_settings
from app.core.paths import repository_root
from app.core.runtime_config import runtime_value
from app.data.external_ingredient_mapping import ReviewedIngredientMapper
from app.data.external_source_policies import AcquisitionMethod
from app.db.session import get_db_session
from app.models.platform import OperationRun
from app.models.recipe import Ingredient
from app.planning.recipe_similarity import RecipeSimilarity
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.repositories.household import HouseholdProfileRepository
from app.repositories.recipe import RecipeRepository
from app.schemas.recommendation import RecipeRecommendationRequest
from app.services.external_recipe_intake import (
    ExternalRecipeDraft,
    ExternalRecipeReview,
    compute_nutrition_per_serving,
    map_ingredient_lines,
    persist_admitted_recipe,
    review_external_recipe,
)
from app.services.external_recipe_search import OpenAIRecipeSearchExtractor, RecipeSearchError

router = APIRouter(prefix="/external-recipes", tags=["external recipe intake"])


class ExternalRecipeIntakeRequest(BaseModel):
    draft: ExternalRecipeDraft
    requires_halal: bool


class ExternalRecipeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    requires_halal: bool


class ExternalRecipeSuggestion(BaseModel):
    slug: str
    title: str


class ExternalRecipeIntakeResponse(BaseModel):
    review: ExternalRecipeReview
    admitted: bool
    recipe_slug: str | None = None
    created: bool | None = None
    suggestions: list[ExternalRecipeSuggestion] = Field(default_factory=list)


@router.post("/intake", response_model=ExternalRecipeIntakeResponse)
def intake_external_recipe(
    payload: ExternalRecipeIntakeRequest,
    database: Annotated[Session, Depends(get_db_session)],
    current: CurrentHouseholdCreatePlanCsrfDependency,
) -> ExternalRecipeIntakeResponse:
    """Review a structured, sourced recipe against the caller's household before private admission."""
    started = time.perf_counter()
    return _review_and_persist(
        payload.draft,
        requires_halal=payload.requires_halal,
        database=database,
        current=current,
        provider_mode="structured_intake",
        acquisition_method="user_supplied",
        started=started,
    )


@router.post("/search-and-intake", response_model=ExternalRecipeIntakeResponse)
def search_and_intake_external_recipe(
    payload: ExternalRecipeSearchRequest,
    database: Annotated[Session, Depends(get_db_session)],
    current: CurrentHouseholdCreatePlanCsrfDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExternalRecipeIntakeResponse:
    """Search for a cited candidate, extract it, then run the same deterministic admission review."""
    started = time.perf_counter()
    stages = []
    live_provider = runtime_value("agent_parser_provider", settings, database) == "openai"
    if not live_provider or settings.openai_api_key is None:
        suggestions = _similar_household_recipes(
            database,
            household_id=current.active_membership.household_id,
            version=_current_profile_version(database, current.active_membership.household_id),
            target=payload.query,
            requires_halal=payload.requires_halal,
        )
        failure = "api_key_missing" if settings.openai_api_key is None else "agent_parser_provider_not_openai"
        stages.append(_stage("search_and_extract", started, "failed", error=failure))
        _record_intake_run(
            database,
            current,
            "web_search",
            stages,
            status="failed",
            error=failure,
            started=started,
            input_digest=hashlib.sha256(" ".join(payload.query.split()).casefold().encode()).hexdigest(),
        )
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": failure,
                "message": "无法联网搜索菜谱：服务尚未配置搜索密钥。",
                "suggestions": [item.model_dump() for item in suggestions],
            },
        )
    search_started = time.perf_counter()
    try:
        draft = OpenAIRecipeSearchExtractor(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=runtime_value("openai_timeout_seconds", settings, database),
        ).search_and_extract(payload.query)
    except RecipeSearchError as error:
        suggestions = _similar_household_recipes(
            database,
            household_id=current.active_membership.household_id,
            version=_current_profile_version(database, current.active_membership.household_id),
            target=payload.query,
            requires_halal=payload.requires_halal,
        )
        stages.append(_stage("search_and_extract", search_started, "failed", error="unusable_search_result"))
        _record_intake_run(
            database,
            current,
            "web_search",
            stages,
            status="failed",
            error="search_rejected",
            started=started,
            input_digest=hashlib.sha256(" ".join(payload.query.split()).casefold().encode()).hexdigest(),
        )
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "unusable_search_result",
                "message": f"搜索结果无法可靠提取为菜谱：{error}",
                "suggestions": [item.model_dump() for item in suggestions],
            },
        ) from error
    except (APIError, TimeoutError, ConnectionError) as error:
        suggestions = _similar_household_recipes(
            database,
            household_id=current.active_membership.household_id,
            version=_current_profile_version(database, current.active_membership.household_id),
            target=payload.query,
            requires_halal=payload.requires_halal,
        )
        stages.append(_stage("search_and_extract", search_started, "failed", error="provider_unavailable"))
        _record_intake_run(
            database,
            current,
            "web_search",
            stages,
            status="failed",
            error="provider_unavailable",
            started=started,
            input_digest=hashlib.sha256(" ".join(payload.query.split()).casefold().encode()).hexdigest(),
        )
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "reason": "provider_unavailable",
                "message": "联网搜索暂时不可用。",
                "suggestions": [item.model_dump() for item in suggestions],
            },
        ) from error
    return _review_and_persist(
        draft,
        requires_halal=payload.requires_halal,
        database=database,
        current=current,
        provider_mode="web_search",
        acquisition_method="web_search",
        started=started,
        stages=[_stage("search_and_extract", search_started, "succeeded", source_url=str(draft.source_url))],
        input_digest=hashlib.sha256(" ".join(payload.query.split()).casefold().encode()).hexdigest(),
    )


def _review_and_persist(
    draft: ExternalRecipeDraft,
    *,
    requires_halal: bool,
    database: Session,
    current,
    provider_mode: str,
    acquisition_method: AcquisitionMethod,
    started: float,
    stages: list[dict] | None = None,
    input_digest: str | None = None,
) -> ExternalRecipeIntakeResponse:
    stages = list(stages or [])
    household_id = current.active_membership.household_id
    root = repository_root()
    mapper = ReviewedIngredientMapper.from_csv_files(
        root / "data-engineering/config/ingredient_aliases.csv",
        root / "data-engineering/config/ingredient_aliases_v2_additions.csv",
    )
    catalog_ingredients = {row.normalized_name: row for row in database.scalars(select(Ingredient))}
    mapping_started = time.perf_counter()
    mapped = map_ingredient_lines(draft, mapper=mapper, catalog_ingredients=catalog_ingredients)
    mapped = mapped.model_copy(update={"nutrition_per_serving": compute_nutrition_per_serving(mapped)})
    stages.append(
        _stage(
            "ingredient_mapping",
            mapping_started,
            "succeeded",
            ingredient_count=len(mapped.ingredients),
            mapped_count=sum(line.canonical_id is not None for line in mapped.ingredients),
        )
    )
    profiles = HouseholdProfileRepository(database, household_id=household_id)
    profile = profiles.get_current()
    version = HouseholdProfileRepository.current_version(profile) if profile else None
    review_started = time.perf_counter()
    review = review_external_recipe(
        mapped,
        household_allergens=(
            [*version.allergens, *(item for member in version.members for item in member.get("allergens", []))]
            if version
            else []
        ),
        excluded_ingredients=list(version.excluded_ingredients) if version else [],
        requires_halal=requires_halal,
        household_dietary_preferences=list(version.dietary_preferences) if version else [],
    )
    stages.append(
        _stage(
            "household_admission_review",
            review_started,
            "succeeded" if review.eligible_for_household else "blocked",
            mapping_coverage=review.mapping_coverage,
            quality_score=review.quality_score,
            safety_conflicts=review.safety_conflicts,
            missing_fields=review.missing_fields,
        )
    )
    if not review.eligible_for_household:
        suggestions = _similar_household_recipes(
            database,
            household_id=household_id,
            version=version,
            target=" ".join(
                [mapped.title or "", mapped.cuisine or "", *(line.source_name for line in mapped.ingredients)]
            ),
            requires_halal=requires_halal,
        )
        stages.append(_stage("private_persistence", time.perf_counter(), "skipped", reason="review_blocked"))
        _record_intake_run(
            database,
            current,
            provider_mode,
            stages,
            status="succeeded",
            source_url=str(mapped.source_url),
            title=mapped.title,
            admitted=False,
            input_digest=input_digest,
            started=started,
        )
        database.commit()
        return ExternalRecipeIntakeResponse(review=review, admitted=False, suggestions=suggestions)
    persist_started = time.perf_counter()
    recipe, created = persist_admitted_recipe(
        database,
        mapped,
        review,
        household_id=household_id,
        acquisition_method=acquisition_method,
    )
    stages.append(_stage("private_persistence", persist_started, "succeeded", recipe_slug=recipe.slug, created=created))
    _record_intake_run(
        database,
        current,
        provider_mode,
        stages,
        status="succeeded",
        source_url=str(mapped.source_url),
        title=mapped.title,
        admitted=True,
        recipe_slug=recipe.slug,
        input_digest=input_digest,
        started=started,
    )
    database.commit()
    return ExternalRecipeIntakeResponse(
        review=review,
        admitted=True,
        recipe_slug=recipe.slug,
        created=created,
    )


def _current_profile_version(database: Session, household_id: int):
    profile = HouseholdProfileRepository(database, household_id=household_id).get_current()
    return HouseholdProfileRepository.current_version(profile) if profile else None


def _similar_household_recipes(database: Session, *, household_id: int, version, target: str, requires_halal: bool):
    """Offer only visible recipes that pass the same deterministic household recommendation filters."""
    repository = RecipeRepository(database, household_id=household_id)
    recipes = repository.list_for_recommendation()
    if not recipes:
        return []
    constraints = RecipeRecommendationRequest(
        household_size=version.planning_household_size if version else 2,
        max_cooking_time_minutes=version.max_cooking_time_minutes if version else 240,
        allergens=(
            [*version.allergens, *(item for member in version.members for item in member.get("allergens", []))]
            if version
            else []
        ),
        excluded_ingredients=list(version.excluded_ingredients) if version else [],
        dietary_preferences=list(version.dietary_preferences) if version else [],
        requires_halal=requires_halal,
        health_preferences=list(version.health_preferences) if version else [],
        max_sodium_mg_per_meal=(
            float(version.max_sodium_mg_per_meal) if version and version.max_sodium_mg_per_meal is not None else None
        ),
    )
    ranked, _excluded = RecipeRecommendationEngine().recommend(recipes, constraints)
    if not ranked:
        return []
    recommendation_by_id = {item.recipe.id: item for item in ranked}
    eligible = [recipe for recipe in recipes if recipe.id in recommendation_by_id]
    similarity = RecipeSimilarity(embed=None).scores(target, eligible)
    ordered = sorted(
        (recipe for recipe in eligible if similarity.get(recipe.id, 0) > 0),
        key=lambda recipe: (
            -similarity[recipe.id],
            -recommendation_by_id[recipe.id].total_score,
            recipe.id,
        ),
    )
    return [ExternalRecipeSuggestion(slug=recipe.slug, title=recipe.title) for recipe in ordered[:3]]


def _stage(name: str, started: float, status_value: str, **details) -> dict:
    return {
        "stage": name,
        "status": status_value,
        "duration_ms": round(max(0.0, time.perf_counter() - started) * 1000),
        **details,
    }


def _record_intake_run(
    database: Session,
    current,
    provider_mode: str,
    stages: list[dict],
    *,
    status: str,
    error: str | None = None,
    source_url: str | None = None,
    title: str | None = None,
    admitted: bool | None = None,
    recipe_slug: str | None = None,
    input_digest: str | None = None,
    started: float | None = None,
) -> None:
    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=max(0.0, time.perf_counter() - started)) if started is not None else now
    data = {
        "stages": stages,
        "source_url": source_url,
        "title": title,
        "admitted": admitted,
        "recipe_slug": recipe_slug,
    }
    if error:
        data["failure_stage"] = stages[-1]["stage"] if stages else "initialization"
    database.add(
        OperationRun(
            trace_id=f"external-intake-{uuid4().hex}",
            run_type="external_recipe_intake",
            status=status,
            household_id=current.active_membership.household_id,
            triggered_by_user_id=current.user.id,
            input_digest=input_digest,
            provider_mode=provider_mode,
            created_at=now,
            started_at=started_at,
            finished_at=now,
            error_code=error,
            artifact_references=[{"kind": "external_recipe_intake", "data": data}],
            warnings=[],
        )
    )
