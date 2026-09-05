from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "snack"]
NutrientMetric = Literal[
    "calories_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "sodium_mg",
    "sugar_g",
]
NutritionScope = Literal["per_slot", "per_day", "horizon_average"]
CheckStatus = Literal["passed", "failed", "indeterminate"]
PlanningStatus = Literal[
    "feasible",
    "candidate_rejected",
    "infeasible",
    "needs_clarification",
    "needs_data",
]


class PlanningNutrients(BaseModel):
    calories_kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    sodium_mg: float = Field(ge=0)
    sugar_g: float = Field(ge=0)


class PlanningSlot(BaseModel):
    slot_id: str = Field(min_length=1, max_length=80)
    planned_date: date
    meal_type: MealType
    servings: int = Field(ge=1, le=24)
    max_time_minutes: int | None = Field(default=None, ge=5, le=360)
    required: bool = True
    locked_recipe_id: str | None = Field(default=None, max_length=120)


class PlanningIngredientRequirement(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def require_unit_for_known_quantity(self) -> "PlanningIngredientRequirement":
        if self.quantity is not None and self.unit is None:
            raise ValueError("unit is required when ingredient quantity is known")
        return self


class PlanningRecipeCandidate(BaseModel):
    recipe_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    servings: int = Field(ge=1, le=24)
    allowed_meal_types: list[MealType] = Field(min_length=1)
    total_time_minutes: int = Field(ge=0, le=720)
    dietary_tags: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    ingredients: list[PlanningIngredientRequirement] = Field(min_length=1)
    nutrients_per_serving: PlanningNutrients
    cuisine: str | None = Field(default=None, max_length=120)


class PlanningPantryItem(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    priority_use: bool = False

    @model_validator(mode="after")
    def require_unit_for_known_quantity(self) -> "PlanningPantryItem":
        if self.quantity is not None and self.unit is None:
            raise ValueError("unit is required when pantry quantity is known")
        return self


class PlanningProductOption(BaseModel):
    ingredient_id: str = Field(min_length=1, max_length=160)
    product_id: str = Field(min_length=1, max_length=160)
    package_quantity: float = Field(gt=0)
    package_unit: str = Field(min_length=1, max_length=40)
    price_sgd: float = Field(ge=0)
    available: bool = True


class PlanningNutritionBand(BaseModel):
    metric: NutrientMetric
    scope: NutritionScope
    lower: float | None = Field(default=None, ge=0)
    upper: float | None = Field(default=None, ge=0)
    hard: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "PlanningNutritionBand":
        if self.lower is None and self.upper is None:
            raise ValueError("at least one nutrition bound is required")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("nutrition lower bound cannot exceed upper bound")
        return self


class PlanningPreferenceWeights(BaseModel):
    nutrition: float = Field(default=0.35, ge=0, le=1)
    variety: float = Field(default=0.25, ge=0, le=1)
    time: float = Field(default=0.15, ge=0, le=1)
    pantry: float = Field(default=0.15, ge=0, le=1)
    health: float = Field(default=0.10, ge=0, le=1)


class FinalPlanningProblem(BaseModel):
    problem_id: str = Field(min_length=1, max_length=120)
    slots: list[PlanningSlot] = Field(min_length=1, max_length=84)
    recipes: list[PlanningRecipeCandidate] = Field(min_length=1)
    pantry: list[PlanningPantryItem] = Field(default_factory=list)
    products: list[PlanningProductOption] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)
    dietary_requirements: list[str] = Field(default_factory=list)
    health_preferences: list[Literal["low-sodium", "low-sugar", "lower-calorie"]] = Field(default_factory=list)
    nutrition_bands: list[PlanningNutritionBand] = Field(default_factory=list)
    purchase_budget_sgd: float | None = Field(default=None, gt=0)
    budget_is_hard: bool = True
    preference_weights: PlanningPreferenceWeights = Field(default_factory=PlanningPreferenceWeights)
    catalog_version: str
    product_snapshot_version: str
    policy_version: str

    @model_validator(mode="after")
    def validate_identity_and_locks(self) -> "FinalPlanningProblem":
        slot_ids = [slot.slot_id for slot in self.slots]
        recipe_ids = [recipe.recipe_id for recipe in self.recipes]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("planning slot IDs must be unique")
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("planning recipe IDs must be unique")
        known_recipes = set(recipe_ids)
        unknown_locks = sorted(
            {
                slot.locked_recipe_id
                for slot in self.slots
                if slot.locked_recipe_id is not None and slot.locked_recipe_id not in known_recipes
            }
        )
        if unknown_locks:
            raise ValueError(f"locked recipes are missing from candidates: {unknown_locks}")
        return self


class PlanningAssignment(BaseModel):
    slot_id: str
    recipe_id: str


class PlanningShoppingSelection(BaseModel):
    ingredient_id: str
    required_quantity: float | None
    unit: str | None
    pantry_deduction: float = Field(ge=0)
    remaining_quantity: float | None
    selected_product_id: str | None
    packages: int = Field(ge=0)
    purchase_cost_sgd: float = Field(ge=0)
    surplus_quantity: float | None
    note: str | None = None


class PlanningConstraintCheck(BaseModel):
    code: str
    status: CheckStatus
    hard: bool = True
    scope_id: str | None = None
    actual: float | str | None = None
    limit: float | str | None = None
    margin: float | None = None
    detail: str


class PlanningValidationReport(BaseModel):
    status: CheckStatus
    hard_failure_count: int = Field(ge=0)
    indeterminate_count: int = Field(ge=0)
    checks: list[PlanningConstraintCheck]
    purchase_total_sgd: float
    catalog_version: str
    product_snapshot_version: str
    policy_version: str


class PlanningTrace(BaseModel):
    algorithm: str
    algorithm_version: str
    deterministic: bool
    candidate_limit: int | None = None
    warnings: list[str] = Field(default_factory=list)


class FinalPlanningSolution(BaseModel):
    problem_id: str
    status: PlanningStatus
    assignments: list[PlanningAssignment]
    shopping: list[PlanningShoppingSelection]
    validation: PlanningValidationReport
    trace: PlanningTrace
