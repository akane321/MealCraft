"""Household member, rule and preference types of the Sprint 2 schema foundation.

Wired by layer 08 PR-1: `AgeBand`, `Sex`, `ActivityLevel`, `PersonalGoal`, `Weekday`, `PresenceRule`,
`CookingTimeRule` and `NutritionLimit` are profile fields, and `HouseholdPlanning` carries them into a planning
request. Layer 08 PR-3 wires `MissingEquipment`. Still unwired: `FlavorBoost` and `PlanningPreferences`.
Meanings and NULL rules are in docs/design/sprint2-schema-foundation.md.
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


class PlanningMember(BaseModel):
    """A member as the planner sees one: portions a meal (stated, or the HPB default), whether usually home, and
    the limits that are this member's own (ADR-0071 section 1: a dish may be served when at least one present
    member can eat it, and every present member is covered).

    `allergens` holds every allergen of this member, including the ones only this member avoids: a dish with one
    is never this member's food. The household-wide avoidance stays in the request's own `allergens`, so an
    allergen nobody marked "only I avoid it" keeps every dish of the week off the table (ADR-0071 section 2).
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    servings: float = Field(gt=0, le=3)
    default_present: bool = True
    allergens: list[str] = Field(default_factory=list, max_length=20)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    dietary_preferences: list[str] = Field(default_factory=list, max_length=4)
    # This member's HPB daily energy target in kcal, after a fat-loss goal; None where HPB researched none, and
    # the meal's energy floor then stays the adult reference at this member's servings (ADR-0070 section 3).
    daily_energy_kcal: float | None = Field(default=None, gt=0, le=6000)


class HouseholdPlanning(BaseModel):
    """The household's own rules for a planning request (layer 08); absent, a request plans as before.

    Its presence alone means the basic seasonings are assumed at home (ADR-0068, ADR-0072 section 2).
    """

    model_config = ConfigDict(extra="forbid")
    # None: every meal is cooked for `household_size` (a conversation changed the size), and the request's own
    # allergens, exclusions and diets are the whole household's, as before the shared-dish model.
    members: list[PlanningMember] | None = Field(default=None, min_length=1, max_length=12)
    presence_rules: list[PresenceRule] = Field(default_factory=list, max_length=20)
    cooking_time_rules: list[CookingTimeRule] = Field(default_factory=list, max_length=20)
    # Basic seasonings the household has run out of: bought and priced as any ingredient.
    missing_basics: list[str] = Field(default_factory=list, max_length=20)
    # Each limit's max_value resolved (a profile's None is its members' HPB limit) before planning.
    nutrition_limits: list[NutritionLimit] = Field(default_factory=list, max_length=1)
    # A member's muscle-gain goal: protein-rich dishes rank higher.
    protein_priority: bool = False
    # Equipment the kitchen lacks: a recipe whose equipment cannot be met is never planned (section 4.3).
    missing_equipment: MissingEquipment = Field(default_factory=list, max_length=5)


def limits_of_every_member(household: HouseholdPlanning | None) -> dict[str, list[str]]:
    """Every member's own limits as one household-wide set, for the moment the members are dropped.

    A request that keeps its members holds each limit against its own member (ADR-0071 section 1). When the
    members go - a size the conversation states replaces them - nothing is left to hold those limits, so they
    have to become the whole household's or they vanish. Allergens marked "only I avoid it" are folded in with
    the rest: once the member they belong to is gone, there is nobody left to keep them for, and the safe
    reading of an allergen with no owner is that the household avoids it.
    """
    members = household.members if household is not None else None
    return {
        "allergens": sorted({item for member in members or [] for item in member.allergens}),
        "excluded_ingredients": sorted({item for member in members or [] for item in member.excluded_ingredients}),
        "dietary_preferences": sorted({item for member in members or [] for item in member.dietary_preferences}),
    }


WEEKDAYS: tuple[Weekday, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _joined(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def day_phrase(weekdays: list[str]) -> str:
    days = sorted(set(weekdays), key=WEEKDAYS.index)
    if not days or len(days) == 7:
        return "Every day"
    if days == list(WEEKDAYS[:5]):
        return "Monday to Friday"
    if days == ["saturday", "sunday"]:
        return "Saturday and Sunday"
    start = WEEKDAYS.index(days[0])
    if len(days) > 2 and days == list(WEEKDAYS[start : start + len(days)]):
        return f"{days[0].capitalize()} to {days[-1].capitalize()}"
    return _joined([day.capitalize() for day in days])


def meal_phrase(meal_types: list[str]) -> str:
    order = ("breakfast", "lunch", "dinner", "snack")
    meals = sorted(set(meal_types), key=order.index)
    return "every meal" if not meals else _joined(meals)


def restate(rule: PresenceRule | CookingTimeRule) -> str:
    """The confirmation card's sentence, always from this template and never from a model."""
    when = f"{day_phrase(rule.weekdays)}, {meal_phrase(rule.meal_types)}"
    if isinstance(rule, PresenceRule):
        return f"{when}: {rule.member_name} {'eats at home' if rule.present else 'eats elsewhere'}."[:200]
    if rule.max_minutes >= 240:
        return f"{when}: no cooking-time limit."
    return f"{when}: within {rule.max_minutes} minutes."
