from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.meal_plan import WeeklyMealPlanResponse
from app.schemas.product import PricingMode
from app.schemas.recommendation import (
    AvailableIngredientInput,
    DietaryPreference,
    HealthPreference,
    NutritionTargets,
)


def _normalize_terms(values: list[str], *, ingredient_ids: bool = False) -> list[str]:
    normalized = {
        value.strip().lower().replace(" ", "_") if ingredient_ids else value.strip().lower()
        for value in values
        if value.strip()
    }
    return sorted(normalized)


class HouseholdMemberInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    servings_per_meal: int = Field(default=1, ge=1, le=3)
    allergens: list[str] = Field(default_factory=list, max_length=20)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=4)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("allergens")
    @classmethod
    def normalize_allergens(cls, values: list[str]) -> list[str]:
        return _normalize_terms(values)

    @field_validator("excluded_ingredients")
    @classmethod
    def normalize_excluded_ingredients(cls, values: list[str]) -> list[str]:
        return _normalize_terms(values, ingredient_ids=True)


class HouseholdProfileWrite(BaseModel):
    name: str = Field(default="My household", min_length=1, max_length=120)
    members: list[HouseholdMemberInput] = Field(min_length=1, max_length=12)
    max_cooking_time_minutes: int = Field(default=60, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    health_preferences: list[HealthPreference] = Field(default_factory=list, max_length=3)
    nutrition_targets: NutritionTargets = Field(default_factory=NutritionTargets)
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] = Field(default_factory=list, max_length=100)
    pricing_mode: PricingMode = "fixture"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def validate_total_servings(self) -> "HouseholdProfileWrite":
        if sum(member.servings_per_meal for member in self.members) > 12:
            raise ValueError("total servings_per_meal must not exceed 12")
        return self


class HouseholdProfileUpdate(HouseholdProfileWrite):
    expected_version: int = Field(ge=1)


class HouseholdProfileVersionResponse(BaseModel):
    version: int
    members: list[HouseholdMemberInput]
    planning_household_size: int
    max_cooking_time_minutes: int
    budget_per_meal_sgd: float | None
    weekly_budget_sgd: float | None
    allergens: list[str]
    excluded_ingredients: list[str]
    dietary_preferences: list[DietaryPreference]
    health_preferences: list[HealthPreference]
    nutrition_targets: NutritionTargets
    max_sodium_mg_per_meal: float | None
    available_ingredients: list[AvailableIngredientInput]
    pricing_mode: PricingMode
    created_at: datetime


class HouseholdProfileResponse(BaseModel):
    id: int
    name: str
    current_version: int
    current: HouseholdProfileVersionResponse
    latest_plan_id: int | None
    created_at: datetime
    updated_at: datetime


class HouseholdProfileVersionCollectionResponse(BaseModel):
    items: list[HouseholdProfileVersionResponse]


class HouseholdPlanningOverrides(BaseModel):
    max_cooking_time_minutes: int | None = Field(default=None, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    health_preferences: list[HealthPreference] | None = Field(default=None, max_length=3)
    nutrition_targets: NutritionTargets | None = None
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] | None = Field(default=None, max_length=100)
    pricing_mode: PricingMode | None = None


class HouseholdProfilePlanRequest(BaseModel):
    start_date: date = Field(default_factory=date.today)
    profile_version: int | None = Field(default=None, ge=1)
    overrides: HouseholdPlanningOverrides = Field(default_factory=HouseholdPlanningOverrides)


class ProfileConstraintChange(BaseModel):
    field: str
    before: Any
    after: Any


class HouseholdProfilePlanResponse(BaseModel):
    profile_id: int
    profile_version: int
    replaces_plan_id: int | None
    constraint_changes: list[ProfileConstraintChange]
    plan: WeeklyMealPlanResponse
