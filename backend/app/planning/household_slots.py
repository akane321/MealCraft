"""The one place a household's rules are read for planning (layer 08): who eats each meal, its time limit,
which basic seasonings are at home, and the nutrition limits it switched on.

Every function takes `household=None` as "no household block": the request plans exactly as before.
"""

from datetime import date
from fractions import Fraction
from functools import lru_cache

from app.data.household_reference import basic_seasonings, meal_shares
from app.data.ingredient_hierarchy import expand_exclusions
from app.schemas.household_rules import WEEKDAYS, HouseholdPlanning
from app.schemas.planning_nutrition import ProductNutritionTarget


def _applies(rule, planned_date: date, meal: str) -> bool:
    weekday = WEEKDAYS[planned_date.weekday()]
    return (not rule.weekdays or weekday in rule.weekdays) and (not rule.meal_types or meal in rule.meal_types)


def slot_servings(household: HouseholdPlanning, planned_date: date, meal: str) -> int | float:
    """The servings of the members home for this meal: each usually-home member, then each rule that names the
    weekday and meal, the last one for a member winning. 0 when nobody is home. A whole number stays an int, so a
    household of whole portions plans exactly as a household size does."""
    present = {member.name: member.default_present for member in household.members or []}
    for rule in household.presence_rules:
        if rule.member_name in present and _applies(rule, planned_date, meal):
            present[rule.member_name] = rule.present
    total = sum(
        (Fraction(str(member.servings)) for member in household.members or [] if present[member.name]), Fraction(0)
    )
    return int(total) if total.denominator == 1 else float(total)


def slot_time_limit(household: HouseholdPlanning | None, default: int, planned_date: date, meal: str) -> int:
    """The meal's cooking-time limit: the tightest rule naming its weekday and meal, else the household's own."""
    limits = [
        rule.max_minutes
        for rule in (household.cooking_time_rules if household else [])
        if _applies(rule, planned_date, meal)
    ]
    return min(limits) if limits else default


def widest_time_limit(household: HouseholdPlanning | None, default: int) -> int:
    """The limit the recipe pool is filtered by, so a rule that loosens one meal ("weekends: no limit") has
    dishes for it; each meal's own limit is held by the planner."""
    return max([default, *(rule.max_minutes for rule in (household.cooking_time_rules if household else []))])


@lru_cache(maxsize=256)
def _assumed(missing: tuple[str, ...], excluded: tuple[str, ...]) -> frozenset[str]:
    return frozenset(basic_seasonings()) - set(missing) - set(expand_exclusions(excluded))


def assumed_basics(household: HouseholdPlanning | None, excluded: list[str]) -> frozenset[str]:
    """The basic seasonings taken as at home: off the list, unpriced, outside the budget.

    Shopping only. A basic stays a recipe ingredient for allergens, exclusions and diets, and one the household
    excludes is never assumed, so its exclusion is still matched against the recipe's lines.
    """
    if household is None:
        return frozenset()
    return _assumed(tuple(sorted(household.missing_basics)), tuple(sorted(excluded)))


def basics_note(names) -> str | None:
    """The grocery list's note for the basics a week uses and does not buy."""
    shown = sorted(basic_seasonings()[name]["display_name"].lower() for name in names if name in basic_seasonings())
    if not shown:
        return None
    return (
        f"Basic seasonings are assumed at home and left off this list: {', '.join(shown)}. "
        "Mark one as run out on your profile to buy it."
    )


def limit_targets(household: HouseholdPlanning | None, planned_meals) -> list[ProductNutritionTarget]:
    """Each switched-on limit as a hard per-day band per person, pro-rated to the meals planned (ADR-0071
    section 3: dinner alone keeps within its 35% of the day)."""
    if household is None:
        return []
    shares = meal_shares()
    share = sum(Fraction(str(shares.get(meal, 0))) for meal in set(planned_meals))
    return [
        ProductNutritionTarget(metric=limit.nutrient, scope="per_day", upper=round(float(limit.max_value * share), 1))
        for limit in household.nutrition_limits
        if limit.max_value is not None and share
    ]
