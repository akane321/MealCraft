from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent import model_client
from app.agent.rule_sentences import OpenAIRuleReader, read_rule_sentence
from app.api.routes.auth import (
    CurrentHouseholdCreatePlanCsrfDependency,
    CurrentHouseholdEditProfileCsrfDependency,
    CurrentHouseholdViewDependency,
)
from app.core.config import Settings, get_settings
from app.core.runtime_config import runtime_value
from app.data.household_reference import reference_table
from app.db.session import get_db_session
from app.planning.capability import PlanningCapabilityError
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.household import HouseholdProfileRepository, HouseholdProfileVersionConflictError
from app.repositories.meal_plan import MealPlanRepository
from app.repositories.product import ProductSnapshotRepository
from app.repositories.recipe import RecipeRepository
from app.schemas.household import (
    HouseholdProfilePlanRequest,
    HouseholdProfilePlanResponse,
    HouseholdProfileResponse,
    HouseholdProfileUpdate,
    HouseholdProfileVersionCollectionResponse,
    HouseholdProfileWrite,
    HouseholdReferenceResponse,
    RuleParseRequest,
    RuleParseResponse,
)
from app.services.household import (
    HouseholdProfileAlreadyExistsError,
    HouseholdProfileNotFoundError,
    HouseholdProfilePlanError,
    HouseholdProfileService,
)
from app.services.meal_plan import WeeklyMealPlanService
from app.services.product import create_product_search_service
from app.services.recommendation import RecipeRecommendationService

router = APIRouter(prefix="/household-profiles", tags=["household profiles"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_household_profile_service(
    database: DatabaseDependency,
    current: CurrentHouseholdViewDependency,
) -> HouseholdProfileService:
    household_id = current.active_membership.household_id
    meal_plan_repository = MealPlanRepository(database, household_id=household_id)
    recipe_repository = RecipeRepository(database, household_id=household_id)
    product_service = create_product_search_service(ProductSnapshotRepository(database))
    meal_plan_service = WeeklyMealPlanService(
        actor_user_id=current.user.id,
        repository=meal_plan_repository,
        recipe_repository=recipe_repository,
        recommendation_service=RecipeRecommendationService(
            recipe_repository,
            grocery_estimator=GroceryEstimator(product_service),
        ),
        grocery_aggregator=WeeklyGroceryAggregator(product_service),
    )
    return HouseholdProfileService(
        repository=HouseholdProfileRepository(database, household_id=household_id),
        meal_plan_repository=meal_plan_repository,
        meal_plan_service=meal_plan_service,
    )


HouseholdProfileServiceDependency = Annotated[HouseholdProfileService, Depends(get_household_profile_service)]


@router.post("", response_model=HouseholdProfileResponse, status_code=status.HTTP_201_CREATED)
def create_household_profile(
    payload: HouseholdProfileWrite,
    service: HouseholdProfileServiceDependency,
    _current: CurrentHouseholdEditProfileCsrfDependency,
) -> HouseholdProfileResponse:
    try:
        return service.create(payload)
    except HouseholdProfileAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except PlanningCapabilityError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/reference", response_model=HouseholdReferenceResponse)
def get_household_reference(_current: CurrentHouseholdViewDependency) -> HouseholdReferenceResponse:
    """HPB default portions and sodium limits, the basic seasonings and the meal shares (layer 08)."""
    return HouseholdReferenceResponse.model_validate(reference_table())


def rule_reader(settings: Settings, database: Session) -> OpenAIRuleReader | None:
    """The model reader when the agent parser is the model and a key is set (as `create_constraint_parser`);
    None reads with the rules, also when the configuration is incomplete."""
    if runtime_value("agent_parser_provider", settings, database) != "openai" or settings.openai_api_key is None:
        return None
    return OpenAIRuleReader.create(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        timeout_seconds=runtime_value("openai_timeout_seconds", settings, database),
    )


@router.post("/parse-rule", response_model=RuleParseResponse)
def parse_household_rule(
    payload: RuleParseRequest,
    database: DatabaseDependency,
    settings: Annotated[Settings, Depends(get_settings)],
    _current: CurrentHouseholdEditProfileCsrfDependency,
) -> RuleParseResponse:
    """One sentence read into draft rules for the confirmation card; nothing is stored until the profile is saved."""
    with model_client.counting():
        return read_rule_sentence(payload, rule_reader(settings, database))


@router.get("/current", response_model=HouseholdProfileResponse)
def get_current_household_profile(service: HouseholdProfileServiceDependency) -> HouseholdProfileResponse:
    try:
        return service.get_current()
    except HouseholdProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/{profile_id}", response_model=HouseholdProfileResponse)
def get_household_profile(
    profile_id: int,
    service: HouseholdProfileServiceDependency,
) -> HouseholdProfileResponse:
    try:
        return service.get(profile_id)
    except HouseholdProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.put("/{profile_id}", response_model=HouseholdProfileResponse)
def update_household_profile(
    profile_id: int,
    payload: HouseholdProfileUpdate,
    service: HouseholdProfileServiceDependency,
    _current: CurrentHouseholdEditProfileCsrfDependency,
) -> HouseholdProfileResponse:
    try:
        return service.update(profile_id, payload)
    except HouseholdProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except HouseholdProfileVersionConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except PlanningCapabilityError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/{profile_id}/versions", response_model=HouseholdProfileVersionCollectionResponse)
def list_household_profile_versions(
    profile_id: int,
    service: HouseholdProfileServiceDependency,
) -> HouseholdProfileVersionCollectionResponse:
    try:
        return service.list_versions(profile_id)
    except HouseholdProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post(
    "/{profile_id}/plans",
    response_model=HouseholdProfilePlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_plan_from_household_profile(
    profile_id: int,
    payload: HouseholdProfilePlanRequest,
    service: HouseholdProfileServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
) -> HouseholdProfilePlanResponse:
    try:
        return service.generate_plan(profile_id, payload)
    except HouseholdProfileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WeeklyPlanSelectionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post(
    "/{profile_id}/plans/{plan_id}/replan",
    response_model=HouseholdProfilePlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def replan_from_household_profile(
    profile_id: int,
    plan_id: int,
    payload: HouseholdProfilePlanRequest,
    service: HouseholdProfileServiceDependency,
    _current: CurrentHouseholdCreatePlanCsrfDependency,
) -> HouseholdProfilePlanResponse:
    try:
        return service.replan(profile_id, plan_id, payload)
    except (HouseholdProfileNotFoundError, HouseholdProfilePlanError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WeeklyPlanSelectionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
