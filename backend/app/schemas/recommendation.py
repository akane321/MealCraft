from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.product import GroceryEstimateResponse, PricingMode
from app.schemas.recipe import RecipeListItemResponse

DietaryPreference = Literal["vegetarian", "vegan", "gluten-free", "dairy-free"]
HealthPreference = Literal["low-sodium", "low-sugar", "lower-calorie"]


class NutritionTargets(BaseModel):
    calories_kcal: float | None = Field(default=None, ge=100, le=2500)
    protein_g: float | None = Field(default=None, ge=0, le=300)
    carbohydrate_g: float | None = Field(default=None, ge=0, le=500)
    fat_g: float | None = Field(default=None, ge=0, le=200)


class AvailableIngredientInput(BaseModel):
    normalized_name: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=40)

    @field_validator("normalized_name")
    @classmethod
    def normalize_ingredient_name(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        return value.strip().lower() if value and value.strip() else None

    @model_validator(mode="after")
    def require_unit_for_known_quantity(self) -> "AvailableIngredientInput":
        if self.quantity is not None and self.unit is None:
            raise ValueError("unit is required when quantity is provided")
        return self


class RecipeRecommendationRequest(BaseModel):
    household_size: int = Field(default=2, ge=1, le=12)
    max_cooking_time_minutes: int = Field(default=60, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    allergens: list[str] = Field(default_factory=list, max_length=20)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=4)
    health_preferences: list[HealthPreference] = Field(default_factory=list, max_length=3)
    nutrition_targets: NutritionTargets = Field(default_factory=NutritionTargets)
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] = Field(default_factory=list, max_length=100)
    pricing_mode: PricingMode = "fixture"

    @field_validator("allergens")
    @classmethod
    def normalize_allergens(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @field_validator("excluded_ingredients")
    @classmethod
    def normalize_excluded_ingredients(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower().replace(" ", "_") for value in values if value.strip()})


class RecommendationScoreBreakdown(BaseModel):
    nutrition: float | None
    pantry: float | None
    time: float


class RecipeRecommendationResponse(BaseModel):
    recipe: RecipeListItemResponse
    total_score: float
    score_breakdown: RecommendationScoreBreakdown
    reasons: list[str]
    grocery_estimate: GroceryEstimateResponse | None = None


class ExcludedRecipeResponse(BaseModel):
    id: int
    slug: str
    title: str
    reasons: list[str]


class RecipeRecommendationCollectionResponse(BaseModel):
    recommendations: list[RecipeRecommendationResponse]
    excluded: list[ExcludedRecipeResponse]
    warnings: list[str]
