from datetime import date, datetime
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.planning_nutrition import ProductNutritionTarget
from app.schemas.planning_v2 import MealComposition
from app.schemas.product import GroceryLineEstimate, PricingMode
from app.schemas.recipe import RecipeListItemResponse, RecipeNutritionResponse
from app.schemas.recommendation import NutritionTargets, RecipeRecommendationRequest

MealPlanEntryStatus = Literal["planned", "completed", "skipped"]
# CHANGE_SHAPE adds, drops or recomposes a meal over some days (ADR-0046 section 2).
MealPlanEventType = Literal["REPLACE_MEAL", "CANCEL_MEAL", "LOCK_MEAL", "ITEM_UNAVAILABLE", "CHANGE_SHAPE"]
MealPlanEventStatus = Literal["previewed", "applied"]


PlannedMeal = Literal["breakfast", "lunch", "dinner"]
MEAL_ORDER: tuple[PlannedMeal, ...] = ("breakfast", "lunch", "dinner")


def _role(role_id: str, *courses: str, required: bool = True) -> dict:
    return {"role_id": role_id, "courses": list(courses), "required": required}


# The presets of ADR-0046 section 1; the first of each meal is its default.
MEAL_PRESETS: dict[PlannedMeal, dict[str, list[dict]]] = {
    "breakfast": {"one dish": [_role("main", "breakfast", "baked_good")]},
    "lunch": {
        "one dish": [_role("main", "main", "salad", "soup")],
        "main and side": [_role("main", "main"), _role("vegetable", "side", "salad")],
    },
    "dinner": {
        # The vegetable is optional: always filled when one fits (an empty optional role costs more
        # than any dish), but a diet or catalog without one still gets a week rather than an error.
        "main and vegetable": [_role("main", "main"), _role("vegetable", "side", "salad", required=False)],
        "one main": [_role("main", "main")],
        "main, vegetable and soup": [
            _role("main", "main"),
            _role("vegetable", "side", "salad"),
            _role("soup", "soup"),
        ],
    },
}


class MealPlanShape(BaseModel):
    """Which meals of each day are planned, and the dish roles of each (ADR-0046)."""

    meals: dict[PlannedMeal, MealComposition] = Field(min_length=1)

    def ordered(self) -> list[tuple[PlannedMeal, list]]:
        return [(meal, self.meals[meal]) for meal in MEAL_ORDER if meal in self.meals]


def default_plan_shape() -> MealPlanShape:
    """Dinner only, one main and one vegetable: the household default (owner, 2026-09-26)."""
    return MealPlanShape.model_validate({"meals": {"dinner": MEAL_PRESETS["dinner"]["main and vegetable"]}})


def week_shape(constraints: dict) -> MealPlanShape:
    """The shape a saved week was planned with; an older week is its dinner composition, or one dish."""
    if constraints.get("plan_shape"):
        return MealPlanShape.model_validate(constraints["plan_shape"])
    roles = constraints.get("meal_composition") or [_role("main", "main")]
    return MealPlanShape.model_validate({"meals": {"dinner": roles}})


class WeeklyMealPlanRequest(RecipeRecommendationRequest):
    nutrition_constraints: list[ProductNutritionTarget] = Field(default_factory=list, max_length=12)
    nutrition_guard_band: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    planner_strategy: Literal["beam", "greedy-baseline"] = "beam"
    start_date: date = Field(default_factory=date.today)
    day_count: int = Field(default=7, ge=7, le=7)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    # Dish roles of every dinner (ADR-0036); None is one dish, the MVP.
    meal_composition: MealComposition | None = None
    # Which meals of each day are planned and each one's dish roles (ADR-0046); replaces meal_composition.
    plan_shape: MealPlanShape | None = None

    @model_validator(mode="after")
    def one_way_to_say_the_shape(self) -> "WeeklyMealPlanRequest":
        if self.plan_shape is not None and self.meal_composition is not None:
            raise ValueError("Give the plan shape or a dinner composition, not both")
        return self

    @model_validator(mode="after")
    def finite_pantry_quantities(self) -> "WeeklyMealPlanRequest":
        if any(p.quantity is not None and not isfinite(p.quantity) for p in self.available_ingredients):
            raise ValueError("Pantry quantities must be finite")
        return self


class WeeklyPlanDayResponse(BaseModel):
    entry_id: int
    day_index: int = Field(ge=1, le=7)
    planned_date: date
    meal_type: str = "dinner"
    role_id: str = "main"
    portion_share: float = 1.0
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
    household_profile_id: int | None
    household_profile_version: int | None
    replaces_plan_id: int | None
    start_date: date
    end_date: date
    day_count: int
    household_size: int
    days: list[WeeklyPlanDayResponse]
    nutrition_summary_per_person: WeeklyNutritionSummaryResponse
    grocery_estimate: WeeklyGroceryEstimateResponse
    warnings: list[str]
    created_at: datetime
    # The meals and dishes this week plans, including changes made in the conversation (ADR-0046).
    plan_shape: MealPlanShape | None = None


class WeeklyMealPlanListItem(BaseModel):
    id: int
    revision: int
    household_profile_id: int | None
    household_profile_version: int | None
    replaces_plan_id: int | None
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
    # Which meal and dish position this is, and its share of the meal (ADR-0046).
    meal_type: str = "dinner"
    role_id: str = "main"
    portion_share: float = 1.0


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
    day_index: int | None = None
    meal_type: str = "dinner"
    role_id: str = "main"
    portion_share: float = 1.0
    recipe_id: int
    recipe_slug: str
    recipe_title: str
    status: MealPlanEntryStatus
    is_locked: bool
    recommendation_score: float


class MealPlanShapeChangeRequest(BaseModel):
    """Plan one meal type with new dishes, or not at all, on some days of a saved week (ADR-0046)."""

    meal_type: PlannedMeal
    # None drops the meal on those days.
    roles: MealComposition | None = None
    # None is every day still ahead; otherwise one meal's exception on the named days.
    day_indexes: list[int] | None = Field(default=None, min_length=1, max_length=7)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("day_indexes")
    @classmethod
    def valid_days(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(day < 1 or day > 7 for day in value):
            raise ValueError("day indexes run from 1 to 7")
        return sorted(set(value)) if value is not None else None


class MealPlanShapeChange(BaseModel):
    meal_type: PlannedMeal
    # "week": the meal type changes for the rest of the week; "meal": an exception on named days.
    scope: Literal["week", "meal"]
    day_indexes: list[int]
    roles: MealComposition | None
    removed: list["MealPlanEntrySnapshot"]
    added: list["MealPlanEntrySnapshot"]
    # The week's shape after the change, for a week-scope change.
    plan_shape: MealPlanShape | None = None


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
    # None for a shape change, which moves several dishes (see shape_change).
    before_entry: MealPlanEntrySnapshot | None
    after_entry: MealPlanEntrySnapshot | None
    shape_change: MealPlanShapeChange | None = None
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
