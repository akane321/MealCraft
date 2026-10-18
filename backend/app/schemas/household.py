from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.clock import today as local_today
from app.data.household_reference import basic_seasonings, default_servings, sodium_limit
from app.schemas.household_rules import (
    AgeBand,
    CookingTimeRule,
    NutritionLimit,
    PersonalGoal,
    PresenceRule,
    Sex,
    restate,
)
from app.schemas.meal_plan import MealPlanShape, WeeklyMealPlanResponse
from app.schemas.planning_v2 import MealComposition, PlanningMealRole
from app.schemas.product import PricingMode
from app.schemas.recommendation import (
    NO_COOKING_TIME_LIMIT,
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
    # Portions a meal, to two decimals; None is the HPB default from age band, sex and goal (layer 08).
    servings_per_meal: float | None = Field(default=1, ge=0.25, le=3)
    age_band: AgeBand | None = None
    sex: Sex | None = None
    # Fat loss: 10% smaller default portions. Muscle gain: protein-rich dishes rank higher.
    goal: PersonalGoal | None = None
    # False is an occasional guest, who eats only at the meals a presence rule adds them to.
    default_present: bool = True
    allergens: list[str] = Field(default_factory=list, max_length=20)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=4)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("servings_per_meal")
    @classmethod
    def two_decimals(cls, value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @field_validator("allergens")
    @classmethod
    def normalize_allergens(cls, values: list[str]) -> list[str]:
        return _normalize_terms(values)

    @field_validator("excluded_ingredients")
    @classmethod
    def normalize_excluded_ingredients(cls, values: list[str]) -> list[str]:
        return _normalize_terms(values, ingredient_ids=True)

    def resolved_servings(self) -> tuple[float, str]:
        """Portions a meal and where they came from: as stated, or the HPB default."""
        if self.servings_per_meal is not None:
            return self.servings_per_meal, "stated"
        return default_servings(self.age_band, self.sex, self.goal)


class HouseholdMemberResponse(HouseholdMemberInput):
    resolved_servings_per_meal: float
    servings_source: Literal["stated", "hpb_default", "fallback_todo"]

    @classmethod
    def of(cls, member: dict) -> "HouseholdMemberResponse":
        stated = HouseholdMemberInput.model_validate(member)
        servings, source = stated.resolved_servings()
        return cls(**stated.model_dump(), resolved_servings_per_meal=servings, servings_source=source)


class HouseholdProfileWrite(BaseModel):
    name: str = Field(default="My household", min_length=1, max_length=120)
    members: list[HouseholdMemberInput] = Field(min_length=1, max_length=12)
    # Only what the household states is a constraint: an unstated limit is no limit.
    max_cooking_time_minutes: int = Field(default=NO_COOKING_TIME_LIMIT, ge=5, le=240)
    budget_per_meal_sgd: float | None = Field(default=None, gt=0, le=1000)
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    health_preferences: list[HealthPreference] = Field(default_factory=list, max_length=3)
    nutrition_targets: NutritionTargets = Field(default_factory=NutritionTargets)
    max_sodium_mg_per_meal: float | None = Field(default=None, ge=100, le=5000)
    available_ingredients: list[AvailableIngredientInput] = Field(default_factory=list, max_length=100)
    pricing_mode: PricingMode = "fixture"
    # Dish roles of every meal (ADR-0036); None is one dish a meal.
    meal_composition: MealComposition | None = None
    # Which meals are planned and each one's dishes (ADR-0046); None is the default shape.
    plan_shape: MealPlanShape | None = None
    # Layer 08: confirmed sentences as rules, the basics run out, and the limits switched on.
    presence_rules: list[PresenceRule] = Field(default_factory=list, max_length=20)
    cooking_time_rules: list[CookingTimeRule] = Field(default_factory=list, max_length=20)
    missing_basics: list[str] = Field(default_factory=list, max_length=20)
    nutrition_limits: list[NutritionLimit] = Field(default_factory=list, max_length=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("missing_basics")
    @classmethod
    def known_basics(cls, values: list[str]) -> list[str]:
        names = sorted({value.strip().lower().replace(" ", "_") for value in values if value.strip()})
        unknown = [name for name in names if name not in basic_seasonings()]
        if unknown:
            raise ValueError(f"not a basic seasoning: {', '.join(unknown)}")
        return names

    @field_validator("nutrition_limits")
    @classmethod
    def sodium_only(cls, values: list[NutritionLimit]) -> list[NutritionLimit]:
        if any(limit.nutrient != "sodium_mg" for limit in values):
            raise ValueError("Only a sodium limit is supported")
        return values

    @model_validator(mode="after")
    def validate_total_servings(self) -> "HouseholdProfileWrite":
        if sum(member.resolved_servings()[0] for member in self.members) > 12:
            raise ValueError("total servings_per_meal must not exceed 12")
        return self

    @model_validator(mode="after")
    def validate_household_rules(self) -> "HouseholdProfileWrite":
        home = [member for member in self.members if member.default_present]
        if not home:
            raise ValueError("At least one member must usually eat at home")
        names = {member.name for member in self.members}
        for rule in self.presence_rules:
            if rule.member_name not in names:
                raise ValueError(f"A presence rule names {rule.member_name}, who is not a member")
        if any(limit.max_value is None for limit in self.nutrition_limits) and not any(
            sodium_limit(member.age_band) is not None for member in home
        ):
            raise ValueError("Enter a daily sodium limit: HPB gives no limit for this age group.")
        # The card's sentence is always the server's own template.
        for rule in [*self.presence_rules, *self.cooking_time_rules]:
            rule.restatement = restate(rule)
        return self


class HouseholdProfileUpdate(HouseholdProfileWrite):
    expected_version: int = Field(ge=1)


class HouseholdProfileVersionResponse(BaseModel):
    version: int
    members: list[HouseholdMemberResponse]
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
    meal_composition: list[PlanningMealRole] | None = None
    plan_shape: MealPlanShape | None = None
    presence_rules: list[PresenceRule] = Field(default_factory=list)
    cooking_time_rules: list[CookingTimeRule] = Field(default_factory=list)
    missing_basics: list[str] = Field(default_factory=list)
    nutrition_limits: list[NutritionLimit] = Field(default_factory=list)
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
    meal_composition: MealComposition | None = None


class HouseholdProfilePlanRequest(BaseModel):
    start_date: date = Field(default_factory=local_today)
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


class RuleParseMember(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    age_band: AgeBand | None = None
    default_present: bool = True


class RuleParseRequest(BaseModel):
    """One sentence about who is home or how long cooking may take, read into draft rules; nothing is stored."""

    kind: Literal["presence", "cooking_time"]
    text: str = Field(min_length=1, max_length=500)
    members: list[RuleParseMember] = Field(min_length=1, max_length=12)
    # The member writing, whom "I" and "my" mean.
    speaker: str | None = Field(default=None, max_length=80)


class RuleParseResponse(BaseModel):
    rules: list[PresenceRule] | list[CookingTimeRule]
    # Why the sentence could not be read in full; when any, the card shows them and offers no confirm.
    issues: list[str]
    provider: Literal["openai", "rules"]
    # True when the model was asked and failed, so the rules read the sentence instead.
    fell_back: bool


class BasicSeasoning(BaseModel):
    normalized_name: str
    display_name: str
    allergens: list[str]


class ReferenceSource(BaseModel):
    title: str
    url: str
    retrieved_on: date


class HouseholdReferenceResponse(BaseModel):
    """The profile page's reference values; the page looks them up and never repeats a formula."""

    # age band -> sex ("female", "male", "any") -> goal ("none", "fat_loss", "muscle_gain") -> portions a meal.
    default_servings: dict[str, dict[str, dict[str, float]]]
    # age band -> HPB daily sodium limit in mg; None where HPB gives none.
    sodium_limit_mg: dict[str, float | None]
    basics: list[BasicSeasoning]
    meal_shares: dict[str, float]
    sources: list[ReferenceSource]
