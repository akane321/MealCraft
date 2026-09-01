from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.meal_plan import MealPlanRepository
from app.repositories.product import ProductSnapshotRepository
from app.repositories.recipe import RecipeRepository
from app.schemas.meal_plan import (
    MealPlanEntryStatusUpdate,
    MealPlanReplanConfirmationResponse,
    MealPlanReplanEventCollectionResponse,
    MealPlanReplanEventResponse,
    MealPlanReplanPreviewRequest,
    WeeklyMealPlanCollectionResponse,
    WeeklyMealPlanRequest,
    WeeklyMealPlanResponse,
    WeeklyNutritionDashboardResponse,
)
from app.services.meal_plan import WeeklyMealPlanService
from app.services.product import create_product_search_service
from app.services.recommendation import RecipeRecommendationService
from app.services.replanning import (
    MealPlanReplanConflictError,
    MealPlanReplanningService,
    MealPlanReplanNotFoundError,
    MealPlanReplanValidationError,
)

router = APIRouter(prefix="/plans", tags=["meal plans"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_meal_plan_service(database: DatabaseDependency) -> WeeklyMealPlanService:
    recipe_repository = RecipeRepository(database)
    product_service = create_product_search_service(ProductSnapshotRepository(database))
    recommendation_service = RecipeRecommendationService(
        recipe_repository,
        grocery_estimator=GroceryEstimator(product_service),
    )
    return WeeklyMealPlanService(
        repository=MealPlanRepository(database),
        recipe_repository=recipe_repository,
        recommendation_service=recommendation_service,
        grocery_aggregator=WeeklyGroceryAggregator(product_service),
    )


MealPlanServiceDependency = Annotated[WeeklyMealPlanService, Depends(get_meal_plan_service)]


def get_replanning_service(database: DatabaseDependency) -> MealPlanReplanningService:
    recipe_repository = RecipeRepository(database)
    product_service = create_product_search_service(ProductSnapshotRepository(database))
    recommendation_service = RecipeRecommendationService(
        recipe_repository,
        grocery_estimator=GroceryEstimator(product_service),
    )
    return MealPlanReplanningService(
        repository=MealPlanRepository(database),
        recipe_repository=recipe_repository,
        recommendation_service=recommendation_service,
        grocery_aggregator=WeeklyGroceryAggregator(product_service),
    )


ReplanningServiceDependency = Annotated[MealPlanReplanningService, Depends(get_replanning_service)]


@router.post("/generate", response_model=WeeklyMealPlanResponse, status_code=status.HTTP_201_CREATED)
def generate_weekly_plan(
    constraints: WeeklyMealPlanRequest,
    service: MealPlanServiceDependency,
) -> WeeklyMealPlanResponse:
    try:
        return service.generate(constraints)
    except WeeklyPlanSelectionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("", response_model=WeeklyMealPlanCollectionResponse)
def list_weekly_plans(
    service: MealPlanServiceDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> WeeklyMealPlanCollectionResponse:
    return service.list_recent(limit=limit)


@router.post(
    "/{plan_id}/replan/preview",
    response_model=MealPlanReplanEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def preview_meal_plan_change(
    plan_id: int,
    request: MealPlanReplanPreviewRequest,
    service: ReplanningServiceDependency,
) -> MealPlanReplanEventResponse:
    try:
        return service.preview(plan_id=plan_id, request=request)
    except MealPlanReplanNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.post(
    "/{plan_id}/replan/{event_id}/confirm",
    response_model=MealPlanReplanConfirmationResponse,
)
def confirm_meal_plan_change(
    plan_id: int,
    event_id: int,
    service: ReplanningServiceDependency,
) -> MealPlanReplanConfirmationResponse:
    try:
        return service.confirm(plan_id=plan_id, event_id=event_id)
    except MealPlanReplanNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except MealPlanReplanConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/{plan_id}/events", response_model=MealPlanReplanEventCollectionResponse)
def list_meal_plan_events(
    plan_id: int,
    service: ReplanningServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MealPlanReplanEventCollectionResponse:
    try:
        return service.list_events(plan_id=plan_id, limit=limit)
    except MealPlanReplanNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/{plan_id}", response_model=WeeklyMealPlanResponse)
def get_weekly_plan(plan_id: int, service: MealPlanServiceDependency) -> WeeklyMealPlanResponse:
    plan = service.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal plan not found")
    return plan


@router.patch("/{plan_id}/entries/{entry_id}", response_model=WeeklyMealPlanResponse)
def update_meal_status(
    plan_id: int,
    entry_id: int,
    update: MealPlanEntryStatusUpdate,
    service: MealPlanServiceDependency,
) -> WeeklyMealPlanResponse:
    plan = service.update_entry_status(
        plan_id=plan_id,
        entry_id=entry_id,
        status=update.status,
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal-plan entry not found")
    return plan


@router.get("/{plan_id}/dashboard", response_model=WeeklyNutritionDashboardResponse)
def get_nutrition_dashboard(
    plan_id: int,
    service: MealPlanServiceDependency,
) -> WeeklyNutritionDashboardResponse:
    dashboard = service.dashboard(plan_id)
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal plan not found")
    return dashboard
