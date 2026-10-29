"""The one place a household's rules are read for planning (layer 08): who eats each meal, its time limit,
which basics (seasonings, rice, flours and the like) are at home, and the nutrition limits it switched on.

Every function takes `household=None` as "no household block": the request plans exactly as before.
"""

from collections import Counter
from datetime import date
from fractions import Fraction
from functools import lru_cache

from app.data.household_reference import basic_seasonings, basic_short_labels, hpb, meal_shares
from app.data.ingredient_hierarchy import expand_exclusions
from app.schemas.household_rules import WEEKDAYS, HouseholdPlanning
from app.schemas.planning_nutrition import ProductNutritionTarget
from app.schemas.planning_v2 import PlanningSlotMember


def _applies(rule, planned_date: date, meal: str) -> bool:
    weekday = WEEKDAYS[planned_date.weekday()]
    return (not rule.weekdays or weekday in rule.weekdays) and (not rule.meal_types or meal in rule.meal_types)


def _present(household: HouseholdPlanning, planned_date: date, meal: str) -> list:
    """The members home for this meal: each usually-home member, then each rule that names the weekday and meal,
    the last one for a member winning."""
    present = {member.name: member.default_present for member in household.members or []}
    for rule in household.presence_rules:
        if rule.member_name in present and _applies(rule, planned_date, meal):
            present[rule.member_name] = rule.present
    return [member for member in household.members or [] if present[member.name]]


def present_members(household: HouseholdPlanning, planned_date: date, meal: str) -> list:
    """The members home for this meal (the presence rules applied), in the household's own order."""
    return _present(household, planned_date, meal)


def slot_members(
    household: HouseholdPlanning | None, planned_date: date, meal: str, energy_floor_share: float | None
) -> list[PlanningSlotMember]:
    """The slot's members for the shared-dish model (ADR-0071 section 1): who is home, with each one's own
    allergens, exclusions, diet and energy floor for this meal.

    Empty without a household block or without members, which is the whole-table rule this replaces. A member's
    exclusions are expanded here, as the household's are, so "no pork" also keeps bacon out of that member's
    food. The energy floor is that member's HPB target times the meal's share; with no researched target it
    stays the adult reference at that member's portions, which is the floor the whole table had.
    """
    if household is None or household.members is None:
        return []
    adult = hpb()["adult_reference"]["energy_kcal"]
    members = []
    for member in _present(household, planned_date, meal):
        floor = None
        if energy_floor_share:
            need = member.daily_energy_kcal or member.servings * adult
            floor = round(energy_floor_share * need, 1)
        members.append(
            PlanningSlotMember(
                name=member.name,
                servings=member.servings,
                allergens=sorted(member.allergens),
                excluded_ingredients=sorted(expand_exclusions(member.excluded_ingredients)),
                dietary_requirements=sorted(member.dietary_preferences),
                min_energy_kcal=floor,
            )
        )
    return members


def slot_servings(household: HouseholdPlanning, planned_date: date, meal: str) -> int | float:
    """The servings of the members home for this meal. 0 when nobody is home. A whole number stays an int, so a
    household of whole portions plans exactly as a household size does."""
    total = sum((Fraction(str(member.servings)) for member in _present(household, planned_date, meal)), Fraction(0))
    return int(total) if total.denominator == 1 else float(total)


def slot_people(household: HouseholdPlanning, planned_date: date, meal: str) -> int:
    """How many members are home for this meal: the dish count follows people present (ADR-0070), not portions,
    so two adults and three children are five at the table."""
    return len(_present(household, planned_date, meal))


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
    excludes is never assumed, so its exclusion is still matched against the recipe's lines. A basic any single
    member excludes is not assumed either: the household buys it knowingly rather than cooking with a jar of it
    nobody meant to use (ADR-0071 section 1 moves the limits to members, it does not move this assumption).
    """
    if household is None:
        return frozenset()
    stated = {*excluded, *(item for member in household.members or [] for item in member.excluded_ingredients)}
    return _assumed(tuple(sorted(household.missing_basics)), tuple(sorted(stated)))


def basics_note(names) -> str | None:
    """The grocery list's note for what a week uses and does not buy: categories and counts, not every name."""
    table = basic_seasonings()
    counts = Counter(table[name]["category"] for name in names if name in table)
    if not counts:
        return None
    shown = ", ".join(f"{noun} ({counts[key]})" for key, noun in basic_short_labels().items() if key in counts)
    return (
        f"Pantry basics are assumed at home and left off this list: {shown}. "
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


def rules_on(constraints) -> bool:
    """Whether a request plans with the household's rules (layer 08): a household block, or a meal of meal roles
    (ADR-0070). Without either it plans exactly as before: no tags read, no shelf life, no equipment."""
    if getattr(constraints, "household", None) is not None:
        return True
    shape = getattr(constraints, "plan_shape", None)
    meals = list(shape.meals.values()) if shape is not None else [getattr(constraints, "meal_composition", None)]
    return any(roles and roles[0].meal_roles for roles in meals)
