"""Household member, rule and preference types of the Sprint 2 schema foundation.

They are defined here and not yet wired: no request or response model uses them, so the API is unchanged
until a feature PR wires one in. Meanings and NULL rules are in docs/design/sprint2-schema-foundation.md.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.catalog_tags import Equipment, FlavorTag
from app.schemas.planning_v2 import MealType, NutrientMetric

# Member keys a feature PR adds to the members JSON. None reads as: adult, the average of both sexes,
# moderate activity, no personal goal.
AgeBand = Literal["toddler", "child", "teen", "adult", "senior"]
Sex = Literal["female", "male"]
ActivityLevel = Literal["low", "moderate", "high"]
PersonalGoal = Literal["fat_loss", "muscle_gain"]
Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# household_profile_versions.missing_equipment: equipment the household says it lacks; NULL or [] lacks none.
MissingEquipment = list[Equipment]


class _StatedRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The household's own words, and the restatement shown on the confirmation card.
    source_text: str = Field(min_length=1, max_length=500)
    restatement: str = Field(min_length=1, max_length=200)
    # Empty is every weekday, and every meal.
    weekdays: list[Weekday] = Field(default_factory=list, max_length=7)
    meal_types: list[MealType] = Field(default_factory=list, max_length=4)


class PresenceRule(_StatedRule):
    """Whether one member eats at home on some weekdays and meals ("the kids have lunch at school on weekdays").

    Rules name weekdays and meals only, never dates.
    """

    member_name: str = Field(min_length=1, max_length=80)
    present: bool


class CookingTimeRule(_StatedRule):
    """A cooking-time limit for some weekdays and meals ("weekday dinners within 30 minutes")."""

    max_minutes: int = Field(ge=5, le=240)


class NutritionLimit(BaseModel):
    """A limit the household switched on, such as sodium within the HPB limit."""

    model_config = ConfigDict(extra="forbid")
    nutrient: NutrientMetric
    scope: Literal["per_day"] = "per_day"
    # None: each member's own HPB limit for this nutrient.
    max_value: float | None = Field(default=None, gt=0)


class FlavorBoost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flavor: FlavorTag
    weekdays: list[Weekday] = Field(default_factory=list, max_length=7)
    meal_types: list[MealType] = Field(default_factory=list, max_length=4)


class PlanningPreferences(BaseModel):
    """Soft preferences read from the conversation. They change soft goals and default rules, never a hard limit."""

    model_config = ConfigDict(extra="forbid")
    # Meals whose dish may repeat across days: the variety penalty is off for them ("the same breakfast daily").
    repeat_allowed_meals: list[MealType] = Field(default_factory=list, max_length=4)
    flavor_boosts: list[FlavorBoost] = Field(default_factory=list, max_length=20)
    more_vegetables: bool = False
    lighter: bool = False
