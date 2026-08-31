from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.product import GroceryLineEstimate, PricingMode
from app.schemas.recipe import RecipeListItemResponse, RecipeNutritionResponse
from app.schemas.recommendation import RecipeRecommendationRequest


class WeeklyMealPlanRequest(RecipeRecommendationRequest):
    start_date: date = Field(default_factory=date.today)
    day_count: int = Field(default=7, ge=7, le=7)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)


class WeeklyPlanDayResponse(BaseModel):
    day_index: int = Field(ge=1, le=7)
    planned_date: date
    recipe: RecipeListItemResponse
    recommendation_score: float
    nutrition_per_person: RecipeNutritionResponse
    consumed_cost_sgd: float
    purchase_cost_sgd: float


class WeeklyNutritionSummaryResponse(BaseModel):
    calories_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    sodium_mg: float
    sugar_g: float


class WeeklyGroceryEstimateResponse(BaseModel):
    pricing_mode: PricingMode
    complete: bool
    purchase_total_sgd: float
    consumed_total_sgd: float | None
    weekly_budget_sgd: float | None
    within_weekly_budget: bool | None
    items: list[GroceryLineEstimate]
    unmapped_ingredients: list[str]
    warnings: list[str]


class WeeklyMealPlanResponse(BaseModel):
    id: int
    start_date: date
    end_date: date
    day_count: int
    household_size: int
    days: list[WeeklyPlanDayResponse]
    nutrition_summary_per_person: WeeklyNutritionSummaryResponse
    grocery_estimate: WeeklyGroceryEstimateResponse
    warnings: list[str]
    created_at: datetime


class WeeklyMealPlanListItem(BaseModel):
    id: int
    start_date: date
    end_date: date
    household_size: int
    purchase_total_sgd: float
    consumed_total_sgd: float | None
    within_weekly_budget: bool | None
    created_at: datetime


class WeeklyMealPlanCollectionResponse(BaseModel):
    items: list[WeeklyMealPlanListItem]
