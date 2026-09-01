from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.product import GroceryLineEstimate, PricingMode
from app.schemas.recipe import RecipeListItemResponse, RecipeNutritionResponse
from app.schemas.recommendation import NutritionTargets, RecipeRecommendationRequest

MealPlanEntryStatus = Literal["planned", "completed", "skipped"]
MealPlanEventType = Literal["REPLACE_MEAL", "CANCEL_MEAL", "LOCK_MEAL", "ITEM_UNAVAILABLE"]
MealPlanEventStatus = Literal["previewed", "applied"]


class WeeklyMealPlanRequest(RecipeRecommendationRequest):
    start_date: date = Field(default_factory=date.today)
    day_count: int = Field(default=7, ge=7, le=7)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)


class WeeklyPlanDayResponse(BaseModel):
    entry_id: int
    day_index: int = Field(ge=1, le=7)
    planned_date: date
    recipe: RecipeListItemResponse
    recommendation_score: float
    nutrition_per_person: RecipeNutritionResponse
    consumed_cost_sgd: float
    purchase_cost_sgd: float
    status: MealPlanEntryStatus
    is_locked: bool
    consumed_at: datetime | None


class MealPlanEntryStatusUpdate(BaseModel):
    status: MealPlanEntryStatus


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
    revision: int
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
    revision: int
    start_date: date
    end_date: date
    household_size: int
    purchase_total_sgd: float
    consumed_total_sgd: float | None
    within_weekly_budget: bool | None
    created_at: datetime


class WeeklyMealPlanCollectionResponse(BaseModel):
    items: list[WeeklyMealPlanListItem]


class MealPlanStatusCounts(BaseModel):
    planned: int
    completed: int
    skipped: int


class NutritionDashboardDayResponse(BaseModel):
    entry_id: int
    day_index: int = Field(ge=1, le=7)
    planned_date: date
    recipe: RecipeListItemResponse
    status: MealPlanEntryStatus
    is_locked: bool
    consumed_at: datetime | None
    nutrition_per_person: RecipeNutritionResponse


class WeeklyNutritionDashboardResponse(BaseModel):
    plan_id: int
    revision: int
    start_date: date
    end_date: date
    household_size: int
    completion_rate: float
    status_counts: MealPlanStatusCounts
    nutrition_targets: NutritionTargets
    planned_nutrition_per_person: WeeklyNutritionSummaryResponse
    completed_nutrition_per_person: WeeklyNutritionSummaryResponse
    days: list[NutritionDashboardDayResponse]


class MealPlanReplanPreviewRequest(BaseModel):
    event_type: MealPlanEventType
    entry_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)
    unavailable_ingredient: str | None = Field(default=None, max_length=160)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("unavailable_ingredient")
    @classmethod
    def normalize_unavailable_ingredient(cls, value: str | None) -> str | None:
        return value.strip().lower().replace(" ", "_") if value and value.strip() else None

    @model_validator(mode="after")
    def require_unavailable_ingredient(self) -> "MealPlanReplanPreviewRequest":
        if self.event_type == "ITEM_UNAVAILABLE" and self.unavailable_ingredient is None:
            raise ValueError("unavailable_ingredient is required for ITEM_UNAVAILABLE")
        if self.event_type != "ITEM_UNAVAILABLE" and self.unavailable_ingredient is not None:
            raise ValueError("unavailable_ingredient is only valid for ITEM_UNAVAILABLE")
        return self


class MealPlanEntrySnapshot(BaseModel):
    entry_id: int
    recipe_id: int
    recipe_slug: str
    recipe_title: str
    status: MealPlanEntryStatus
    is_locked: bool
    recommendation_score: float


class MealPlanNutritionDelta(BaseModel):
    calories_kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    sodium_mg: float
    sugar_g: float


class MealPlanGroceryDeltaLine(BaseModel):
    ingredient_name: str
    ingredient_display_name: str
    change: Literal["added", "removed", "updated"]
    before_required_quantity: float | None
    after_required_quantity: float | None
    unit: str | None
    before_packages_required: int
    after_packages_required: int
    purchase_cost_delta_sgd: float


class MealPlanReplanEventResponse(BaseModel):
    id: int
    plan_id: int
    base_revision: int
    applied_revision: int | None
    event_type: MealPlanEventType
    status: MealPlanEventStatus
    reason: str | None
    unavailable_ingredient: str | None
    before_entry: MealPlanEntrySnapshot
    after_entry: MealPlanEntrySnapshot
    nutrition_delta: MealPlanNutritionDelta
    grocery_delta: list[MealPlanGroceryDeltaLine]
    purchase_total_delta_sgd: float
    created_at: datetime
    applied_at: datetime | None


class MealPlanReplanEventCollectionResponse(BaseModel):
    items: list[MealPlanReplanEventResponse]


class MealPlanReplanConfirmationResponse(BaseModel):
    event: MealPlanReplanEventResponse
    plan: WeeklyMealPlanResponse
