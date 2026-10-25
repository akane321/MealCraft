"""The shared-dish model (ADR-0071 section 1): each member's own limits, and a covered plate at every meal.

A meal is a set of shared dishes, as at a family table. Three rules replace "every dish suits the whole table":

- **A dish may be served** when at least one present member can eat it (`servable`).
- **Each present member is covered** at every lunch and dinner: among the dishes that member can eat there is a
  filling core, a vegetable dish whenever the meal has one, and that member's own energy floor (`coverage_issues`).
  This is hard, and ADR-0068 keeps it outside idealization: a limit the data cannot confirm leaves the dish out,
  never the member uncovered.
- **Each dish is cooked, bought and priced** for the servings of the present members who can eat it
  (`dish_base_servings`), not for the whole table.

A slot with no members plans exactly as before: every dish is everyone's, cooked for the slot's servings, and no
member is checked on their own. The household-wide allergens, exclusions and diets of the request still apply to
every dish on top of a member's own, so an allergen nobody marked "only I avoid it" keeps the dish off the table.
"""

import re
from dataclasses import dataclass
from fractions import Fraction

from app.data.allergens import checked_allergens
from app.data.ingredient_hierarchy import expand_exclusions
from app.planning.dietary_tags import satisfies
from app.schemas.planning_v2 import PlanningSlot, PlanningSlotMember

MAIN_ROLE = "main"
STAPLE_ROLE = "staple"
VEGETABLE_ROLE = "vegetable"


@dataclass(frozen=True)
class MemberLimits:
    """One member's own limits where dishes are catalog recipes: the recipe pool, and a swap.

    `excluded_ingredients` is expanded over the ingredient hierarchy once per member; `stated` keeps the
    household's own words, so a reason can say which of them removed the dish. The field names match
    `PlanningSlotMember`, so both read through the same checks.
    """

    name: str
    allergens: frozenset[str]
    excluded_ingredients: frozenset[str]
    dietary_requirements: tuple[str, ...]
    stated: tuple[str, ...] = ()
    servings: float = 1.0
    min_energy_kcal: float | None = None


def member_limits(household) -> list[MemberLimits]:
    """Each member's own limits, or an empty list without a household block or without members.

    Empty means the request's own allergens, exclusions and diets are the whole household's, exactly as before
    the shared-dish model: every candidate must satisfy all of them.
    """
    members = getattr(household, "members", None) if household is not None else None
    return [
        MemberLimits(
            name=member.name,
            allergens=frozenset(member.allergens),
            excluded_ingredients=frozenset(expand_exclusions(member.excluded_ingredients)),
            dietary_requirements=tuple(member.dietary_preferences),
            stated=tuple(member.excluded_ingredients),
            servings=member.servings,
        )
        for member in members or []
    ]


def covering_groups(members) -> list[tuple]:
    """The sets of members a role's dishes have to be able to suit: each member on their own, and all of them
    together when their limits differ, because a meal with one dish of a kind has to suit everyone from it.

    Empty when there are fewer than two members or no member has limits of their own: a household whose members
    are all alike keeps exactly the dishes it kept before the shared-dish model.
    """
    if len(members) < 2 or not any(m.allergens or m.excluded_ingredients or m.dietary_requirements for m in members):
        return []
    groups: list[tuple] = [(member,) for member in members]
    limits = {(tuple(m.allergens), tuple(m.excluded_ingredients), tuple(m.dietary_requirements)) for m in members}
    if len(limits) > 1:
        groups.append(tuple(members))
    return groups


def title_mentions(title: str, avoided: list[str]) -> list[str]:
    """The avoided words a recipe's name states outright (`pork` in "Pork Chops").

    A dish whose name says what it is made of is taken at its word, whichever list the word came from. It lives
    here because a member's own limits read it too: a recipe missing its main ingredient line would otherwise
    count as food for a member who avoids exactly that.
    """
    lowered = title.lower()
    words = {item.replace("_", " ") for item in avoided if not item.startswith("group:")}
    return sorted(word for word in words if re.search(rf"\b{re.escape(word)}(?:e?s)?\b", lowered))


def named_against(member, title: str) -> bool:
    """Whether a dish's own name states something this member avoids: their exclusions or any of their allergens."""
    return bool(title_mentions(title, [*member.excluded_ingredients, *member.allergens]))


def unverifiable_for(member) -> list[str]:
    """This member's own allergens that no recipe was checked for (ADR-0024 section 3).

    The household-wide list is held to the same rule by the planner, which rejects every dish when one of its
    allergens is outside the checked vocabulary. A member's own allergens have to meet it too, or marking an
    allergen "only I avoid it" would turn a name nobody can verify - a misspelling, a plural, a food outside
    the vocabulary - into a member who may eat anything. Here it goes the other way: unverifiable means this
    member can eat nothing, and the plan is refused for leaving them uncovered rather than quietly fed.
    """
    return sorted(set(member.allergens) - checked_allergens())


def unknown_safety_for(member, recipe) -> list[str]:
    """Unknown evidence cannot cover the member who has that safety requirement."""
    unknown = set(recipe.unknown_safety or ())
    return [
        code
        for field, required, code in (
            ("allergens", member.allergens, "allergen_status_unknown"),
            ("diet", member.dietary_requirements, "dietary_status_unknown"),
        )
        if required and field in unknown
    ]


def member_can_eat(member, recipe) -> bool:
    """Whether this dish is this member's food: their own allergens, exclusions and diet.

    `recipe` is a planning candidate. The household-wide limits are checked once for the dish itself
    (`dish_eligible`, the validator's dish checks); this is only what differs between members at one table.
    """
    if unverifiable_for(member) or unknown_safety_for(member, recipe):
        return False
    if set(recipe.allergens) & set(member.allergens):
        return False
    if {item.ingredient_id for item in recipe.ingredients} & set(member.excluded_ingredients):
        return False
    if named_against(member, recipe.title):
        return False
    return satisfies(member.dietary_requirements, recipe.dietary_tags)


def catalog_can_eat(member, recipe, lines=None) -> bool:
    """`member_can_eat` for a catalog recipe (`app.models.recipe.Recipe`), as the pool and a swap read it.

    `lines` are the recipe's lines as this household cooks them (`alternatives.lines`), where the caller has
    them: an "A or B" line is then judged by the option actually chosen, so two members excluding different
    options are each answered about the one that reaches the table rather than about the combined line.
    Without them the recipe's own lines are read, which is what the combined line used to mean.
    """
    if unverifiable_for(member) or unknown_safety_for(member, recipe):
        return False
    lines = recipe.recipe_ingredients if lines is None else lines
    allergens = {*(recipe.allergens or ()), *(a for item in lines for a in (item.ingredient.allergens or ()))}
    if allergens & set(member.allergens):
        return False
    if {item.ingredient.normalized_name for item in lines} & set(member.excluded_ingredients):
        return False
    if named_against(member, recipe.title):
        return False
    return satisfies(member.dietary_requirements, recipe.dietary_tags)


def eaters(slot: PlanningSlot, recipe) -> list[PlanningSlotMember]:
    """The members home for this meal who can eat this dish, in the slot's order."""
    return [member for member in slot.members if member_can_eat(member, recipe)]


def servable(slot: PlanningSlot, recipe) -> bool:
    """Whether the dish may be served at this meal: at least one present member can eat it."""
    return not slot.members or any(member_can_eat(member, recipe) for member in slot.members)


def dish_base_servings(slot: PlanningSlot, recipe) -> Fraction:
    """The servings a dish is cooked for before its portion share: the present members who can eat it.

    Without members this is the slot's own servings, so every quantity, price and shopping line of a request
    with no household block is the arithmetic this replaces. A dish no present member can eat is a hard
    validation failure (`dish_not_servable`); its servings stay the slot's so the report can still be produced.
    """
    if not slot.members:
        return Fraction(str(slot.servings))
    able = eaters(slot, recipe)
    if not able:
        return Fraction(str(slot.servings))
    return sum((Fraction(str(member.servings)) for member in able), Fraction(0))


def role_base(role_id: str | None) -> str:
    """ "main-2" -> "main": the kind of dish a role id names (`meal_composition.role_base`, without its import)."""
    return (role_id or MAIN_ROLE).split("-")[0]


@dataclass(frozen=True)
class CoverageDish:
    """One dish of a meal as the coverage rules read it, whatever kind of recipe object it came from."""

    role_id: str
    protein_main: bool
    carries_staple: bool
    calories_kcal: float
    share: float
    eaten_by: frozenset[str]


def coverage_failures(members, dishes: list[CoverageDish]) -> list[tuple[str, str, float | None, float]]:
    """Every present member this meal leaves uncovered, as (code, detail, actual, limit).

    For each member, among the dishes that member can eat:

    - a **filling core**: a protein main beside the staple, or one dish that carries its staple, which counts as
      both for the members who can eat it (ADR-0070 section 2);
    - a **vegetable dish**, whenever the meal holds one at all;
    - the **energy floor**: that member's portions of their own dishes against their share of their HPB daily
      target (ADR-0071 section 3), in place of one adult reference for the table.

    Member names are the keys of `CoverageDish.eaten_by`, so a member with the same name twice is one member;
    the profile keeps names distinct.
    """
    meal_has_vegetable = any(role_base(dish.role_id) == VEGETABLE_ROLE for dish in dishes)
    failures: list[tuple[str, str, float | None, float]] = []
    for member in members:
        mine = [dish for dish in dishes if member.name in dish.eaten_by]
        staple = any(role_base(dish.role_id) == STAPLE_ROLE for dish in mine)
        mains = [dish for dish in mine if role_base(dish.role_id) == MAIN_ROLE]
        core = any(dish.carries_staple for dish in mains) or (staple and any(dish.protein_main for dish in mains))
        if not core:
            detail = f"{member.name} has no filling core among the dishes {member.name} can eat."
            failures.append(("member_filling_core", detail, None, 1))
        if meal_has_vegetable and not any(role_base(dish.role_id) == VEGETABLE_ROLE for dish in mine):
            detail = f"The meal's vegetable dishes are none that {member.name} can eat."
            failures.append(("member_vegetable", detail, None, 1))
        floor = member.min_energy_kcal
        if floor is not None:
            # What this member eats of the meal: their portions of the dishes that are their food.
            energy = member.servings * sum(dish.share * dish.calories_kcal for dish in mine)
            if energy - floor < -1e-6:
                detail = f"The dishes {member.name} can eat give less than {member.name}'s energy floor."
                failures.append(("member_energy_floor", detail, round(energy, 1), floor))
    return failures


def member_has_a_dish(slot: PlanningSlot, dishes, recipes: dict) -> list[tuple[str, str, float | None, float]]:
    """Every present member this meal gives nothing at all to eat, as (code, detail, actual, limit).

    The weakest form of the shared-dish rule, and the only one a meal outside the full structure can be held
    to: a breakfast is one dish, and a meal of the older course roles carries no meal-role tags to judge a
    filling core by. Serving a dish because one member can eat it still has to leave nobody at that table with
    an empty plate (ADR-0071 section 1), so this is checked wherever the full coverage rules cannot be.
    """
    if not slot.members:
        return []
    served = [recipes[recipe_id] for _, recipe_id in dishes]
    return [
        (
            "member_no_dish",
            f"Nothing at this {slot.meal_type} is a dish {member.name} can eat.",
            None,
            1,
        )
        for member in slot.members
        if not any(member_can_eat(member, recipe) for recipe in served)
    ]


def coverage_issues(slot: PlanningSlot, dishes, recipes: dict, shares) -> list[tuple[str, str, float | None, float]]:
    """`coverage_failures` for a planning slot. `dishes` are (role id, recipe id) pairs, `shares` each role's
    portion share. Empty for a meal with no members, which is every request without a household block."""
    if not slot.members or shares is None:
        return []
    # Imported here, not above: `meal_composition` reads this module's rules, and the dish that carries its
    # staple and the role a dish may fill have one definition each (ADR-0070 section 2), which live beside the
    # meal's own structure. `meal_role_of` is the admissible role, so a main whose protein sources are unknown
    # is no filling core for anyone.
    from app.planning.meal_composition import fills_staple, meal_role_of

    read = []
    for role, recipe_id in dishes:
        recipe = recipes[recipe_id]
        read.append(
            CoverageDish(
                role_id=role or MAIN_ROLE,
                protein_main=meal_role_of(recipe) == "protein_main",
                carries_staple=fills_staple(recipe),
                calories_kcal=recipe.nutrients_per_serving.calories_kcal,
                share=float(shares[role or MAIN_ROLE]),
                eaten_by=frozenset(m.name for m in slot.members if member_can_eat(m, recipe)),
            )
        )
    return coverage_failures(slot.members, read)
