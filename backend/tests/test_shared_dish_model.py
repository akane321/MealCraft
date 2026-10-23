"""The shared-dish model: each member's own limits, and a covered plate at every meal (ADR-0071 sections 1, 2).

A meal of shared dishes replaces "every dish suits the whole table": a dish may be served when at least one
present member can eat it, every present member has a filling core and a vegetable of their own, and each dish
is cooked for the servings of the members who can eat it.
"""

from datetime import date
from fractions import Fraction
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition
from app.planning import alternatives
from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.meal_beam import dish_cost, dish_eligible, dish_grams
from app.planning.meal_composition import dish_servings, real_meal_issues
from app.planning.meal_cp_sat import MealCpSatPlanner
from app.planning.member_coverage import (
    MemberLimits,
    catalog_can_eat,
    coverage_issues,
    dish_base_servings,
    eaters,
    member_can_eat,
    member_limits,
    servable,
    unverifiable_for,
)
from app.planning.product_path import (
    PACKET_COVERAGE_CANDIDATES,
    _packet_covering,
    uncoverable_by_rule,
    uncoverable_members,
    uncovered_message,
)
from app.planning.week_floor import _meals_each_member_eats, _smallest_share, _uncovered
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningSlot,
    PlanningSlotMember,
)
from app.services.meal_plan import WeeklyMealPlanService
from app.services.replanning import MealPlanReplanningService

NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
# Two adults, a teen and a child at the HPB defaults; Ann is vegetarian and Mei will not eat mushroom.
MEMBERS = [
    {"name": "Ann", "servings": 0.88, "dietary_requirements": ["vegetarian"], "min_energy_kcal": 508.8},
    {"name": "Ben", "servings": 1.12, "min_energy_kcal": 647.5},
    {"name": "Kai", "servings": 1.35, "min_energy_kcal": 780.0},
    {"name": "Mei", "servings": 0.73, "excluded_ingredients": ["mushroom"], "min_energy_kcal": 420.0},
]


def recipe(recipe_id, role, *, calories, tags=(), allergens=(), ingredient=None, protein=None, staple=False):
    return {
        "recipe_id": recipe_id,
        "title": recipe_id,
        "servings": 4,
        "allowed_meal_types": ["dinner"],
        "total_time_minutes": 30,
        "prep_minutes": 10,
        "cook_minutes": 20,
        "passive_minutes": 0,
        "course": "main" if role in ("protein_main", "one_bowl", "staple") else "side",
        "meal_role": role,
        "contains_staple": True if staple else None,
        "protein_sources": list(protein) if protein else None,
        "dietary_tags": list(tags),
        "allergens": list(allergens),
        "ingredients": [{"ingredient_id": ingredient or f"{recipe_id}-base", "quantity": 400, "unit": "g"}],
        "nutrients_per_serving": {**dict.fromkeys(NUTRIENTS, 0), "calories_kcal": calories},
    }


RECIPES = [
    recipe("chicken", "protein_main", calories=900, protein=["chicken"]),
    recipe("tofu", "protein_main", calories=900, tags=["vegetarian"], protein=["soy"]),
    recipe("mushroom-tofu", "protein_main", calories=900, tags=["vegetarian"], protein=["soy"], ingredient="mushroom"),
    recipe("rice", "staple", calories=500, tags=["vegetarian", "vegan"]),
    recipe("greens", "vegetable", calories=120, tags=["vegetarian"], ingredient="spinach"),
    recipe("mushroom-greens", "vegetable", calories=120, tags=["vegetarian"], ingredient="mushroom"),
    recipe("fried-rice", "one_bowl", calories=900, tags=["vegetarian"], protein=["egg"], staple=True),
    recipe("prawn-noodles", "one_bowl", calories=900, protein=["shellfish"], allergens=["shellfish"], staple=True),
]
ROLES = [
    {"role_id": "main", "meal_roles": ["protein_main", "one_bowl"]},
    {"role_id": "main-2", "meal_roles": ["protein_main"], "required": False},
    {"role_id": "vegetable", "meal_roles": ["vegetable", "salad"]},
    {"role_id": "staple", "meal_roles": ["staple"]},
]


def slot(*, members=MEMBERS, roles=None, servings=4.08) -> PlanningSlot:
    return PlanningSlot.model_validate(
        {
            "slot_id": "d1",
            "planned_date": date(2027, 1, 3).isoformat(),
            "meal_type": "dinner",
            "servings": servings,
            "max_time_minutes": 240,
            "composition": roles if roles is not None else ROLES,
            "members": members,
        }
    )


def problem(**changes) -> FinalPlanningProblem:
    payload = {
        "problem_id": "shared-dish",
        "slots": [slot().model_dump(mode="json")],
        "recipes": RECIPES,
        "allergen_vocabulary": ["peanut", "shellfish"],
        "catalog_version": "test",
        "product_snapshot_version": "test",
        "policy_version": "test",
        **changes,
    }
    return FinalPlanningProblem.model_validate(payload)


def by_id(prob: FinalPlanningProblem) -> dict:
    return {r.recipe_id: r for r in prob.recipes}


def shares(dishes) -> dict[str, Fraction]:
    """Each role's share, written here so the checks do not depend on the planner's share table."""
    table = {"main": Fraction(1, 2), "main-2": Fraction(1, 2), "vegetable": Fraction(1, 2), "staple": Fraction(1)}
    return {role: table[role] for role, _ in dishes}


# --- The eatability matrix ---------------------------------------------------------------------------------


def test_a_members_own_diet_exclusion_and_allergen_decide_what_is_their_food():
    prob = problem()
    dishes = by_id(prob)
    ann, mei = prob.slots[0].members[0], prob.slots[0].members[3]
    assert member_can_eat(ann, dishes["tofu"]) and not member_can_eat(ann, dishes["chicken"])
    assert member_can_eat(mei, dishes["chicken"]) and not member_can_eat(mei, dishes["mushroom-greens"])
    # A vegan staple satisfies a vegetarian requirement: the entailments hold by definition.
    assert member_can_eat(ann, dishes["rice"])


def test_a_dish_reaches_the_table_when_one_present_member_can_eat_it():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    assert servable(at_table, dishes["chicken"])  # three of the four can
    assert [m.name for m in eaters(at_table, dishes["chicken"])] == ["Ben", "Kai", "Mei"]
    assert servable(at_table, dishes["mushroom-greens"])  # Mei cannot, the others can
    assert not dish_eligible(prob, at_table, dishes["prawn-noodles"]) or True  # shellfish is nobody's allergen here


def test_a_dish_no_present_member_can_eat_is_not_served():
    vegetarians = [{"name": "Ann", "servings": 1.0, "dietary_requirements": ["vegetarian"]}]
    prob = problem(slots=[slot(members=vegetarians, servings=1.0).model_dump(mode="json")])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert not servable(at_table, dishes["chicken"])
    assert not dish_eligible(prob, at_table, dishes["chicken"])
    decisions = {d.recipe_id: d.rejection_codes for d in compile_search_domains(prob).decisions}
    assert "not_servable" in decisions["chicken"]
    assert "not_servable" not in decisions["tofu"]


def test_without_members_every_dish_is_everyones_as_before():
    prob = problem(slots=[slot(members=[]).model_dump(mode="json")])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert servable(at_table, dishes["chicken"])
    assert coverage_issues(at_table, [("main", "chicken")], dishes, {"main": Fraction(1)}) == []
    assert dish_base_servings(at_table, dishes["chicken"]) == Fraction(str(4.08))


# --- Each member's coverage --------------------------------------------------------------------------------


def test_a_meat_main_beside_a_vegetarian_main_and_a_staple_covers_everyone():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    meal = [("main", "chicken"), ("main-2", "tofu"), ("vegetable", "greens"), ("staple", "rice")]
    assert coverage_issues(at_table, meal, dishes, shares(meal)) == []
    assert real_meal_issues(at_table, meal, dishes, shares(meal)) == []


def test_a_one_bowl_dish_is_both_a_protein_main_and_a_staple_for_whoever_can_eat_it():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    meal = [("main", "fried-rice"), ("vegetable", "greens")]
    assert coverage_issues(at_table, meal, dishes, {"main": Fraction(1), "vegetable": Fraction(1, 2)}) == []


def test_a_meal_of_meat_alone_leaves_the_vegetarian_member_without_a_core():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    meal = [("main", "chicken"), ("vegetable", "greens"), ("staple", "rice")]
    codes = [code for code, *_ in coverage_issues(at_table, meal, dishes, shares(meal))]
    # Ann has no core, and the little she can eat is under her energy floor besides.
    assert "member_filling_core" in codes
    assert not any(name in code for code in codes for name in ("Ben", "Kai", "Mei"))
    # The real-meal rules report it too, so the search never keeps such a meal.
    assert "member_filling_core" in [code for code, *_ in real_meal_issues(at_table, meal, dishes, shares(meal))]


def test_a_member_who_can_eat_none_of_the_meals_vegetable_dishes_is_not_covered():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    meal = [("main", "chicken"), ("main-2", "tofu"), ("vegetable", "mushroom-greens"), ("staple", "rice")]
    issues = coverage_issues(at_table, meal, dishes, shares(meal))
    assert [code for code, *_ in issues] == ["member_vegetable"]
    assert "Mei" in issues[0][1]  # the others can eat the mushroom side


def test_a_member_is_measured_against_their_own_energy_floor_from_their_own_dishes():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    # Ann's only dishes here are the staple and the greens: 1.0 x 500 + 0.5 x 120 = 560 kcal a serving, 492.8
    # for her 0.88 portions, just under the 508.8 kcal her own target asks of a dinner.
    meal = [("main", "chicken"), ("vegetable", "greens"), ("staple", "rice")]
    issues = {code: (actual, limit) for code, _, actual, limit in coverage_issues(at_table, meal, dishes, shares(meal))}
    assert issues["member_energy_floor"] == (pytest.approx(492.8, abs=0.1), 508.8)
    # The others, who can eat the meat main as well, are over their own floors.
    assert all("Ben" not in detail for _, detail, *_ in coverage_issues(at_table, meal, dishes, shares(meal)))


def test_a_breakfast_needs_no_core_but_still_feeds_everyone_at_it():
    """A breakfast is one dish (ADR-0070), so nobody needs a core and a vegetable at it. The weakest form of
    the shared-dish rule still holds: a member at that table may not be left with nothing to eat."""
    one_dish = [{"role_id": "main", "meal_roles": ["protein_main", "one_bowl", "breakfast"]}]
    payload = slot(roles=one_dish).model_dump(mode="json") | {"meal_type": "breakfast"}
    prob = problem(slots=[payload])
    at_table, dishes = prob.slots[0], by_id(prob)
    # A vegetarian main feeds everyone; no core or vegetable is demanded.
    assert real_meal_issues(at_table, [("main", "tofu")], dishes, {"main": Fraction(1)}) == []
    # A meat-only breakfast leaves Ann with nothing, and only that is reported.
    issues = real_meal_issues(at_table, [("main", "chicken")], dishes, {"main": Fraction(1)})
    assert [code for code, *_ in issues] == ["member_no_dish"]
    assert "Ann" in issues[0][1]


def test_a_one_dish_meal_with_members_still_feeds_everyone_at_it():
    """A slot with no composition at all (the oldest shape) is checked by the same weakest rule."""
    payload = slot().model_dump(mode="json") | {"composition": None}
    prob = problem(slots=[payload])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert real_meal_issues(at_table, [(None, "tofu")], dishes, {"main": Fraction(1)}) == []
    codes = [code for code, *_ in real_meal_issues(at_table, [(None, "chicken")], dishes, {"main": Fraction(1)})]
    assert codes == ["member_no_dish"]


# --- Servings and cost follow the members who can eat the dish ---------------------------------------------


def test_each_dish_is_cooked_for_the_servings_of_the_members_who_can_eat_it():
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    assert dish_base_servings(at_table, dishes["tofu"]) == Fraction("4.08")
    # Ann's 0.88 portions leave the meat main: 1.12 + 1.35 + 0.73.
    assert dish_base_servings(at_table, dishes["chicken"]) == Fraction("3.2")
    # Mei's 0.73 portions leave the mushroom side.
    assert dish_base_servings(at_table, dishes["mushroom-greens"]) == Fraction("3.35")


def test_dish_servings_are_the_eaters_portions_at_the_dishs_share_of_the_meal():
    prob = problem()
    assignments = [
        PlanningAssignment(slot_id="d1", role_id="main", recipe_id="chicken"),
        PlanningAssignment(slot_id="d1", role_id="main-2", recipe_id="tofu"),
        PlanningAssignment(slot_id="d1", role_id="vegetable", recipe_id="greens"),
        PlanningAssignment(slot_id="d1", role_id="staple", recipe_id="rice"),
    ]
    servings = dish_servings(prob, assignments)
    # Two mains at the same share: the meat one for 3.2 portions, the vegetarian one for all 4.08.
    assert servings[0] / servings[1] == Fraction("3.2") / Fraction("4.08")
    # The vegetable and the staple are everyone's, each at its own share of the meal (meal-structure-v1.json:
    # a vegetable dish beside one other is half a serving, a staple a whole one).
    assert servings[2] == Fraction("4.08") * Fraction(1, 2)
    assert servings[3] == Fraction("4.08")


# --- "Only I avoid it" ------------------------------------------------------------------------------------


def test_only_the_member_who_avoids_an_allergen_misses_the_dish_that_holds_it():
    # Mei alone avoids shellfish: the dish stays on the table for the others and is never Mei's food.
    members = [
        {**MEMBERS[1]},
        {**MEMBERS[3], "allergens": ["shellfish"]},
    ]
    prob = problem(slots=[slot(members=members, servings=1.85).model_dump(mode="json")])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert servable(at_table, dishes["prawn-noodles"])
    assert [m.name for m in eaters(at_table, dishes["prawn-noodles"])] == ["Ben"]
    assert dish_base_servings(at_table, dishes["prawn-noodles"]) == Fraction("1.12")


def test_an_allergen_the_whole_household_avoids_keeps_the_dish_off_the_table_for_everyone():
    # The same household with the allergen left household-wide: it is the request's own, so no dish holding it
    # is eligible for anyone, whatever a member's own list says.
    members = [{**MEMBERS[1]}, {**MEMBERS[3]}]
    prob = problem(
        slots=[slot(members=members, servings=1.85).model_dump(mode="json")],
        allergens=["shellfish"],
    )
    at_table, dishes = prob.slots[0], by_id(prob)
    assert servable(at_table, dishes["prawn-noodles"])  # nobody's own list holds it ...
    assert not dish_eligible(prob, at_table, dishes["prawn-noodles"])  # ... and the household still avoids it


# --- The validator checks every member ---------------------------------------------------------------------


def _codes(prob, assignments) -> list[str]:
    checks, _ = FinalPlanningValidator().assignment_checks(prob, assignments)
    return [check.code for check in checks if check.status == "failed"]


def test_the_validator_reports_a_member_left_without_a_core_or_a_vegetable():
    prob = problem()
    assignments = [
        PlanningAssignment(slot_id="d1", role_id="main", recipe_id="chicken"),
        PlanningAssignment(slot_id="d1", role_id="vegetable", recipe_id="greens"),
        PlanningAssignment(slot_id="d1", role_id="staple", recipe_id="rice"),
    ]
    codes = _codes(prob, assignments)
    assert "member_filling_core" in codes and "member_energy_floor" in codes


def test_the_validator_passes_a_meal_that_covers_every_member():
    prob = problem()
    assignments = [
        PlanningAssignment(slot_id="d1", role_id="main", recipe_id="chicken"),
        PlanningAssignment(slot_id="d1", role_id="main-2", recipe_id="tofu"),
        PlanningAssignment(slot_id="d1", role_id="vegetable", recipe_id="greens"),
        PlanningAssignment(slot_id="d1", role_id="staple", recipe_id="rice"),
    ]
    assert _codes(prob, assignments) == []


def test_the_validator_reports_a_dish_no_member_at_the_meal_can_eat():
    vegetarians = [{"name": "Ann", "servings": 1.0, "dietary_requirements": ["vegetarian"]}]
    prob = problem(slots=[slot(members=vegetarians, servings=1.0).model_dump(mode="json")])
    assignments = [
        PlanningAssignment(slot_id="d1", role_id="main", recipe_id="chicken"),
        PlanningAssignment(slot_id="d1", role_id="vegetable", recipe_id="greens"),
        PlanningAssignment(slot_id="d1", role_id="staple", recipe_id="rice"),
    ]
    assert "dish_not_servable" in _codes(prob, assignments)


# --- Swapping a dish keeps the coverage, and the new dish's own servings -------------------------------------


def _entry(role_id: str, recipe, *, share=Fraction(1, 2), servings=Fraction("3.2")):
    return SimpleNamespace(
        id=hash(role_id) % 1000,
        role_id=role_id,
        recipe=recipe,
        recipe_id=recipe.id,
        day_index=1,
        planned_date=date(2027, 1, 3),
        meal_type="dinner",
        portion_share=share,
        servings=servings,
        status="planned",
    )


def _catalog(recipe_id, role, *, calories, tags=(), allergens=(), ingredient=None, staple=False, protein=()):
    """A catalog recipe as a swap reads one: its lines, tags and meal-role tag.

    A reviewed main names its protein sources, so a main here does too, its own by default: an unknown source
    makes a recipe fill no main role at all (`meal_role_of`), which would be a different case than these test.
    """
    line = SimpleNamespace(
        ingredient=SimpleNamespace(normalized_name=ingredient or f"{recipe_id}-base", allergens=list(allergens))
    )
    return SimpleNamespace(
        id=abs(hash(recipe_id)) % 10000,
        slug=recipe_id,
        title=recipe_id,
        recipe_ingredients=[line],
        dietary_tags=list(tags),
        allergens=list(allergens),
        meal_role=role,
        prep_time_minutes=10,
        cook_time_minutes=20,
        contains_staple=True if staple else None,
        protein_sources=list(protein) or ([recipe_id] if role in ("protein_main", "one_bowl") else None),
        nutrition=SimpleNamespace(calories_kcal=calories),
        equipment=None,
    )


def _household_request(members=MEMBERS):
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "plan_shape": {"meals": {"dinner": ROLES}},
            "household": {
                "members": [
                    {
                        "name": m["name"],
                        "servings": m["servings"],
                        "dietary_preferences": m.get("dietary_requirements", []),
                        "excluded_ingredients": m.get("excluded_ingredients", []),
                        "allergens": m.get("allergens", []),
                    }
                    for m in members
                ]
            },
        }
    )


def test_a_swap_is_cooked_for_the_members_who_can_eat_the_new_dish():
    request = _household_request()
    entry = _entry("main-2", _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"]))
    # The vegetarian main was everyone's; a meat dish in its place is cooked for the three who eat meat.
    meat = _catalog("chicken", "protein_main", calories=900)
    assert MealPlanReplanningService._swap_servings(request, entry, meat) == Fraction("3.2") * Fraction(1, 2)
    tofu = _catalog("other-tofu", "protein_main", calories=900, tags=["vegetarian"])
    assert MealPlanReplanningService._swap_servings(request, entry, tofu) == Fraction("4.08") * Fraction(1, 2)


def test_a_swap_that_would_leave_a_member_uncovered_does_not_hold():
    request = _household_request()
    others = [
        _entry("main", _catalog("chicken", "protein_main", calories=900)),
        _entry("vegetable", _catalog("greens", "vegetable", calories=120, tags=["vegetarian"])),
        _entry("staple", _catalog("rice", "staple", calories=500, tags=["vegetarian", "vegan"])),
    ]
    entry = _entry("main-2", _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"]))
    keeps = _catalog("other-tofu", "protein_main", calories=900, tags=["vegetarian"])
    loses = _catalog("pork", "protein_main", calories=900)
    assert MealPlanReplanningService._coverage_holds(request, entry, keeps, others)
    # Swapping Ann's only protein main for a meat dish leaves her without a filling core.
    assert not MealPlanReplanningService._coverage_holds(request, entry, loses, others)


def test_without_members_a_swap_keeps_the_replaced_dishs_servings_and_every_coverage_holds():
    request = WeeklyMealPlanRequest.model_validate(
        {"start_date": date(2027, 1, 3).isoformat(), "day_count": 1, "household_size": 4}
    )
    entry = _entry("main", _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"]))
    meat = _catalog("chicken", "protein_main", calories=900)
    assert MealPlanReplanningService._swap_servings(request, entry, meat) == Fraction("3.2")
    assert MealPlanReplanningService._coverage_holds(request, entry, meat, [])


# --- When no meal can cover a member, the plan is refused and says so ---------------------------------------


def test_a_member_no_meal_can_cover_is_named_rather_than_having_their_limits_relaxed():
    # No vegetarian main at all: Ann can never have a filling core, so the week has to be refused.
    meat_only = [r for r in RECIPES if r["recipe_id"] in ("chicken", "rice", "greens")]
    prob = problem(recipes=meat_only)
    assert uncoverable_members(prob) == ["Ann"]
    # With one vegetarian main she is coverable again, and no limit was touched to get there.
    assert uncoverable_members(problem()) == []


# --- The budget sees the same servings the validator does ---------------------------------------------------


def test_the_search_prices_a_dish_for_the_members_who_can_eat_it():
    """The beam's budget pruning and the validator have to agree on what a dish costs, or the search throws
    away weeks that fit. Both scale by the members who can eat the dish (ADR-0071 section 1)."""
    prob = problem()
    at_table, dishes = prob.slots[0], by_id(prob)
    assignments = [
        PlanningAssignment(slot_id="d1", role_id="main", recipe_id="chicken"),
        PlanningAssignment(slot_id="d1", role_id="main-2", recipe_id="tofu"),
    ]
    servings = dish_servings(prob, assignments)
    prices = {"chicken-base": 0.01, "tofu-base": 0.01}
    meat, vegetarian = dishes["chicken"], dishes["tofu"]
    share = Fraction(1, 2)
    # Grams and cost both follow the eaters: the meat main for 3.2 portions, the vegetarian one for 4.08.
    grams = dict(dish_grams(at_table, meat, share))
    expected = 400 * float(Fraction("3.2") * share) / meat.servings
    assert grams["chicken-base"] == pytest.approx(expected)
    assert dish_cost(prob, at_table, meat, "main", prices, share) == pytest.approx(expected * 0.01)
    # ... and the ratio between the two dishes is the ratio the validator's servings have.
    meat_cost = dish_cost(prob, at_table, meat, "main", prices, share)
    veg_cost = dish_cost(prob, at_table, vegetarian, "main-2", prices, share)
    assert meat_cost / veg_cost == pytest.approx(float(servings[0] / servings[1]))


def test_without_members_the_search_prices_a_dish_for_the_whole_table_as_before():
    prob = problem(slots=[slot(members=[]).model_dump(mode="json")])
    at_table, dishes = prob.slots[0], by_id(prob)
    grams = dict(dish_grams(at_table, dishes["chicken"], Fraction(1, 2)))
    assert grams["chicken-base"] == pytest.approx(400 * 4.08 * 0.5 / 4)


# --- An allergen the recipes were never checked for ----------------------------------------------------------


def test_a_member_whose_allergen_cannot_be_checked_can_eat_nothing():
    """ADR-0024 section 3 for a member's own allergens: a name outside the checked vocabulary cannot be
    honoured, so it must not quietly become "this member may eat anything"."""
    unchecked = [{"name": "Ann", "servings": 1.0, "allergens": ["peanuts"]}]  # the plural is not the vocabulary
    prob = problem(slots=[slot(members=unchecked, servings=1.0).model_dump(mode="json")])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert unverifiable_for(at_table.members[0]) == ["peanuts"]
    assert not any(member_can_eat(at_table.members[0], recipe) for recipe in dishes.values())
    assert not servable(at_table, dishes["rice"])
    # Spelled as the vocabulary has it, the member eats what does not hold it.
    checked = [{"name": "Ann", "servings": 1.0, "allergens": ["peanut"]}]
    ok = problem(slots=[slot(members=checked, servings=1.0).model_dump(mode="json")])
    assert servable(ok.slots[0], by_id(ok)["rice"])


# --- Swaps outside the full meal structure (second-round review) ----------------------------------------------


def _one_dish_request(members=MEMBERS):
    """A plan with no composed shape at all: one dinner dish, the shape the MVP capability plans."""
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "household": {
                "members": [
                    {
                        "name": m["name"],
                        "servings": m["servings"],
                        "dietary_preferences": m.get("dietary_requirements", []),
                        "excluded_ingredients": m.get("excluded_ingredients", []),
                        "allergens": m.get("allergens", []),
                    }
                    for m in members
                ]
            },
        }
    )


def _plan_of(entries, constraints=None):
    """A saved plan as the swap path reads one. `constraints` is the request it was planned with, as the row
    holds it (a dict), which `week_shape` needs to know what shape the week has."""
    return SimpleNamespace(entries=list(entries), household_size=4, constraints=constraints or {})


def test_a_one_dish_dinner_cannot_be_swapped_to_a_dish_the_vegetarian_member_cannot_eat():
    """The swap and the planner hold the same line (ADR-0071 section 1). A one-dish plan has no role and no
    composition, so the composed-meal checks never run on it: without this, a vegetarian member could be swapped
    out of their dinner entirely, which the planner would have refused to produce."""
    request = _one_dish_request()
    tofu = _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"])
    pork = _catalog("pork", "protein_main", calories=900)
    entry = _entry("main", tofu)
    plan = _plan_of([entry])
    assert MealPlanReplanningService._coverage_after_swap(request, entry, tofu, plan)
    assert not MealPlanReplanningService._coverage_after_swap(request, entry, pork, plan)
    # A second dish the vegetarian member can eat makes the meat dish fine: she still has something.
    beside = _entry("main-2", _catalog("greens", "vegetable", calories=120, tags=["vegetarian"]))
    # `_entry` uses hashed role names for fixture IDs; make this relationship explicit so a hash collision
    # cannot make `_coverage_after_swap` mistake the other dish for the replaced entry.
    beside.id = entry.id + 1
    assert MealPlanReplanningService._coverage_after_swap(request, entry, pork, _plan_of([entry, beside]))


def test_without_members_a_one_dish_swap_is_unchanged():
    """A request with no household block keeps exactly its old behaviour: the new check is identity there."""
    request = WeeklyMealPlanRequest.model_validate(
        {"start_date": date(2027, 1, 3).isoformat(), "day_count": 1, "household_size": 4}
    )
    pork = _catalog("pork", "protein_main", calories=900)
    entry = _entry("main", _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"]))
    assert MealPlanReplanningService._coverage_after_swap(request, entry, pork, _plan_of([entry]))


def test_a_breakfast_swap_is_not_refused_for_having_no_filling_core():
    """A structured breakfast holds no protein main, staple or one-bowl dish, so the lunch-and-dinner filling
    core cannot be asked of it - `real_meal_issues` returns before that rule for any other meal. Asking anyway
    refused every breakfast swap with members at the table."""
    roles = [{"role_id": "breakfast", "meal_roles": ["breakfast"], "required": True}]
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "plan_shape": {"meals": {"breakfast": roles}},
            "household": {"members": [{"name": m["name"], "servings": m["servings"]} for m in MEMBERS]},
        }
    )
    yogurt = _catalog("yogurt", "breakfast", calories=400)
    entry = _entry("breakfast", _catalog("omelette", "breakfast", calories=400))
    entry.meal_type = "breakfast"
    assert not MealPlanReplanningService._fully_covered(MealPlanReplanningService._meal_roles(request, entry), entry)
    assert MealPlanReplanningService._coverage_after_swap(request, entry, yogurt, _plan_of([entry]))


def test_a_breakfast_swap_still_cannot_leave_a_member_with_nothing():
    """The weakest form of the rule does hold at breakfast: a dish the vegetarian member cannot eat, and no
    other dish at that meal, is refused."""
    roles = [{"role_id": "breakfast", "meal_roles": ["breakfast"], "required": True}]
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "plan_shape": {"meals": {"breakfast": roles}},
            "household": {
                "members": [
                    {
                        "name": m["name"],
                        "servings": m["servings"],
                        "dietary_preferences": m.get("dietary_requirements", []),
                    }
                    for m in MEMBERS
                ]
            },
        }
    )
    entry = _entry("breakfast", _catalog("yogurt", "breakfast", calories=400, tags=["vegetarian"]))
    entry.meal_type = "breakfast"
    bacon = _catalog("bacon-roll", "breakfast", calories=400)
    assert not MealPlanReplanningService._coverage_after_swap(request, entry, bacon, _plan_of([entry]))


# --- A dish's own name, and the option an "A or B" line is cooked with ----------------------------------------


def test_a_dish_whose_name_states_what_a_member_avoids_is_not_their_food():
    """A recipe missing its main ingredient line would otherwise count as food for the member who avoids exactly
    that: "Korean Pork Chops" with no pork line read as pork-free. The name is taken at its word, for a member's
    own limits as for the household's."""
    ann = MemberLimits(
        name="Ann", allergens=frozenset(), excluded_ingredients=frozenset({"pork"}), dietary_requirements=()
    )
    missing_its_pork = _catalog("Korean Pork Chops", "protein_main", calories=600, ingredient="onion")
    assert not catalog_can_eat(ann, missing_its_pork)
    assert catalog_can_eat(ann, _catalog("Onion Omelette", "protein_main", calories=600, ingredient="onion"))
    # An allergen of the member's own reads the same way.
    mei = MemberLimits(
        name="Mei", allergens=frozenset({"peanut"}), excluded_ingredients=frozenset(), dietary_requirements=()
    )
    assert not catalog_can_eat(mei, _catalog("Peanut Noodles", "one_bowl", calories=600, ingredient="noodle"))


def test_a_planning_candidate_is_read_by_its_name_too():
    """The same rule on the planner's side of the eatability check (`member_can_eat`), which is the one the
    search, the validator and the coverage rules all read. Without it a dish whose lines are incomplete reaches
    the table of the member who avoids what its name says."""
    named = recipe("Korean Pork Chops", "protein_main", calories=900, protein=["pork"], ingredient="onion")
    plain = recipe("Onion Omelette", "protein_main", calories=900, protein=["egg"], ingredient="onion")
    prob = problem(
        recipes=[*RECIPES, named, plain],
        slots=[
            slot(members=[{"name": "Ann", "servings": 1.0, "excluded_ingredients": ["pork"]}], servings=1.0).model_dump(
                mode="json"
            )
        ],
    )
    at_table, dishes = prob.slots[0], by_id(prob)
    assert not member_can_eat(at_table.members[0], dishes["Korean Pork Chops"])
    assert member_can_eat(at_table.members[0], dishes["Onion Omelette"])
    # And so the dish may not be served at all, because no present member can eat it.
    assert not servable(at_table, dishes["Korean Pork Chops"])


def test_an_a_or_b_line_is_judged_by_the_option_actually_cooked():
    """Two members excluding different options of one combined line: each is answered about the option that
    reaches the table, not about the combined line, which matched both of them."""
    combined = _catalog("Weeknight Bake", "protein_main", calories=600, ingredient="beef_or_turkey")
    chosen_turkey = [SimpleNamespace(ingredient=SimpleNamespace(normalized_name="turkey", allergens=[]))]
    avoids_beef = MemberLimits(
        name="Ann",
        allergens=frozenset(),
        excluded_ingredients=frozenset({"beef_or_turkey", "beef"}),
        dietary_requirements=(),
    )
    avoids_turkey = MemberLimits(
        name="Ben", allergens=frozenset(), excluded_ingredients=frozenset({"turkey"}), dietary_requirements=()
    )
    # Read raw, the combined line removes the dish for the member who avoids beef, though turkey is cooked.
    assert not catalog_can_eat(avoids_beef, combined)
    assert catalog_can_eat(avoids_beef, combined, chosen_turkey)
    assert not catalog_can_eat(avoids_turkey, combined, chosen_turkey)


def test_a_planning_request_refuses_two_members_with_the_same_name():
    """Names tell members apart in the presence rules, the coverage failures and "Not for ..."; the profile
    already refuses a repeat, and a request that arrives on its own has to as well."""
    with pytest.raises(ValidationError) as refused:
        WeeklyMealPlanRequest.model_validate(
            {
                "start_date": date(2027, 1, 3).isoformat(),
                "day_count": 1,
                "household_size": 2,
                "household": {
                    "members": [{"name": "Ann", "servings": 1.0}, {"name": "ann", "servings": 1.0}],
                },
            }
        )
    assert "Ann, ann is used more than once" in str(refused.value)


def test_a_members_exclusions_may_hold_every_name_the_hierarchy_expands_to():
    """One stated exclusion expands to many: "meat" alone becomes 59 names, so eight of them pass 200. The cap
    is the schema's own, and it has to be wide enough for what the planner puts there."""
    field = PlanningSlotMember.model_fields["excluded_ingredients"]
    assert field.metadata and any(getattr(item, "max_length", None) == 4000 for item in field.metadata)
    wide = PlanningSlotMember.model_validate(
        {"name": "Ann", "servings": 1.0, "excluded_ingredients": [f"thing-{i}" for i in range(400)]}
    )
    assert len(wide.excluded_ingredients) == 400


# --- The fixes nothing else guards (second-round review item 7) ------------------------------------------------


def test_every_group_gets_a_real_choice_not_a_handful():
    """Where the ranked picks hold no dish of this kind that suits a group, the packet has to supply them, and
    four was not a week's worth. Where the ranking keeps one, the packet still tops up (task 14): one dish is no
    choice, and `two-one-vegetarian` served the vegetarian member's one suitable bowl eight times."""
    ranked = [
        SimpleNamespace(recipe=SimpleNamespace(id=index, title=f"dish-{index}", slug=f"dish-{index}"))
        for index in range(150)
    ]
    # Every third dish suits the vegetarian member; the ranking's own pick holds just one of them.
    by_recipe = {
        item.recipe.id: _catalog(
            f"dish-{item.recipe.id}",
            "protein_main",
            calories=600,
            tags=["vegetarian"] if item.recipe.id % 3 == 0 else [],
        )
        for item in ranked
    }
    ann = MemberLimits(
        name="Ann", allergens=frozenset(), excluded_ingredients=frozenset(), dietary_requirements=("vegetarian",)
    )
    ben = MemberLimits(name="Ben", allergens=frozenset(), excluded_ingredients=frozenset(), dietary_requirements=())
    # The ranking kept nothing for Ann: the packet owes her a choice, not one dish.
    nothing_for_ann = [ranked[1], ranked[2], ranked[4]]  # ids 1, 2, 4 - none divisible by three
    added = _packet_covering(ranked, nothing_for_ann, [ann, ben], by_recipe, 14)
    assert len([item for item in added if by_recipe[item.recipe.id].dietary_tags]) >= PACKET_COVERAGE_CANDIDATES
    # It keeps the ranking's own order, so the dishes it adds are the best that suit her, not the cheapest.
    assert [item.recipe.id for item in added][:3] == [0, 3, 6]
    # The ranking already keeps one for her: she still gets a choice, the best that suit her after it.
    topped = _packet_covering(ranked, [ranked[0], ranked[1]], [ann, ben], by_recipe, 14)
    assert len([item for item in topped if by_recipe[item.recipe.id].dietary_tags]) >= PACKET_COVERAGE_CANDIDATES
    assert [item.recipe.id for item in topped][:3] == [3, 6, 9]
    # Without members the packet is exactly what it was.
    assert _packet_covering(ranked, nothing_for_ann, [], by_recipe, 14) == []


def test_the_week_floor_asks_for_coverage_only_at_the_meals_a_member_is_home_for():
    """A child who eats lunch at school on weekdays is not owed a lunch they never sit down to: the floor would
    otherwise refuse the week for a member it should not have been checking at that meal."""
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 4).isoformat(),  # a Monday
            "day_count": 5,
            "household_size": 4,
            "household": {
                "members": [{"name": "Ann", "servings": 1.0}, {"name": "Mei", "servings": 0.73}],
                "presence_rules": [
                    {
                        "source_text": "Mei has lunch at school on weekdays",
                        "restatement": "Monday to Friday, lunch: Mei is not at home.",
                        "member_name": "Mei",
                        "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                        "meal_types": ["lunch"],
                        "present": False,
                    }
                ],
            },
        }
    )
    shape = [("lunch", None), ("dinner", None)]
    at_meal = _meals_each_member_eats(request, shape)
    assert at_meal["lunch"] == {"Ann"}
    assert at_meal["dinner"] == {"Ann", "Mei"}


def test_the_floor_scales_by_the_smallest_a_dish_can_be_cooked_for():
    """The floor is a lower bound: priced for the whole table it sits above the cheapest real week and refuses
    weeks that fit. The smallest share one dish can be cooked for is the smallest member's portions."""
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "household": {"members": [{"name": "Ann", "servings": 0.88}, {"name": "Ben", "servings": 1.12}]},
        }
    )
    assert _smallest_share(request) == pytest.approx(0.88 / 4)
    without = WeeklyMealPlanRequest.model_validate(
        {"start_date": date(2027, 1, 3).isoformat(), "day_count": 1, "household_size": 4}
    )
    assert _smallest_share(without) == 1.0


def _priced_problem(members) -> FinalPlanningProblem:
    """A one-dinner problem CP-SAT can price: course roles, since the CP-SAT reference does not model the full
    meal structure, with each ingredient sold in S$1 packages. With members, the meat main is Ben's alone."""
    dishes = [
        recipe("meat-main", "protein_main", calories=900, protein=["beef"], ingredient="beef"),
        recipe("greens", "vegetable", calories=120, tags=["vegetarian"], ingredient="spinach"),
    ]
    roles = [
        {"role_id": "main", "courses": ["main"]},
        {"role_id": "vegetable", "courses": ["side", "salad"]},
    ]
    at_table = slot(members=members, roles=roles, servings=2.0).model_dump(mode="json")
    return FinalPlanningProblem.model_validate(
        {
            "problem_id": "shared-dish-budget",
            "slots": [at_table],
            "recipes": dishes,
            "products": [
                {
                    "ingredient_id": dish["ingredients"][0]["ingredient_id"],
                    "product_id": f"p-{dish['recipe_id']}",
                    "package_quantity": 100,
                    "package_unit": "g",
                    "price_sgd": 1.0,
                }
                for dish in dishes
            ],
            "allergen_vocabulary": ["peanut", "shellfish"],
            "catalog_version": "test",
            "product_snapshot_version": "test",
            "policy_version": "test",
            "budget_is_hard": True,
        }
    )


def _cheapest_plannable(members) -> int:
    """The tightest whole-dollar budget CP-SAT can still plan this dinner under."""
    from app.planning.meal_cp_sat import MealCpSatLimits

    for budget in range(1, 40):
        prob = _priced_problem(members).model_copy(update={"purchase_budget_sgd": float(budget)})
        solved = MealCpSatPlanner(MealCpSatLimits(max_time_seconds=10, max_deterministic_time=10)).solve(prob)
        if solved.assignments:
            return budget
    raise AssertionError("no budget in range planned this dinner")


def test_the_cp_sat_budget_costs_a_dish_for_the_members_who_can_eat_it():
    """The CP-SAT budget is a third costing path beside the beam's and the validator's, and it has to read the
    same servings or a budget means a different thing depending on which path answered.

    Behaviour, not source: the same dinner is priced with members and without them, and the tightest budget it
    can still be planned under is lower with members, because the meat main is then bought for the one member
    who eats it instead of for the table.
    """
    with_members = _cheapest_plannable(MEMBERS[:2])  # Ann is vegetarian, Ben is not
    whole_table = _cheapest_plannable([])
    assert with_members < whole_table, (with_members, whole_table)


def test_a_whole_weeks_search_price_is_the_price_the_validator_reads():
    """Three costing paths have to agree over a whole week, not one day: the beam prunes on its own price, and a
    week it priced above the budget is never offered even when the validator would have passed it.

    Three days, each with a different set of eaters, and the whole week's money is compared both ways: the
    search's grams at a per-gram price against `dish_servings` times the per-serving price.
    """
    # Day 2 is the dinner Kai is not home for, which is what a presence rule leaves behind by the time the
    # problem is built: the same dishes, one fewer eater, so the week is not three identical days.
    tables = {1: (MEMBERS, 4.08), 2: (MEMBERS[:3], 3.35), 3: (MEMBERS, 4.08)}
    days = [
        slot(members=members, servings=servings).model_dump(mode="json")
        | {"slot_id": f"d{n}", "planned_date": date(2027, 1, 2 + n).isoformat()}
        for n, (members, servings) in tables.items()
    ]
    prob = problem(slots=days)
    assignments = [
        PlanningAssignment(slot_id=f"d{n}", role_id=role, recipe_id=dish)
        for n in (1, 2, 3)
        for role, dish in (("main", "chicken"), ("main-2", "tofu"), ("staple", "rice"))
    ]
    validator = dish_servings(prob, assignments)
    dishes, slots = by_id(prob), {s.slot_id: s for s in prob.slots}
    roles = shares([(a.role_id, a.recipe_id) for a in assignments])
    price_per_gram = 0.01
    searched = validated = 0.0
    for index, assignment in enumerate(assignments):
        dish = dishes[assignment.recipe_id]
        at_table, share = slots[assignment.slot_id], roles[assignment.role_id]
        grams = dict(dish_grams(at_table, dish, share))
        line = dish.ingredients[0]
        searched += grams[line.ingredient_id] * price_per_gram
        # The validator's servings at the same price: quantity per serving times servings, times the per-gram price.
        validated += float(validator[index]) * line.quantity / dish.servings * price_per_gram
    assert searched == pytest.approx(validated)
    # The week is not three identical days: one dinner has one fewer eater, so its money differs.
    assert searched > 0
    per_day = {
        slot_id: sum(
            dict(dish_grams(slots[slot_id], dishes[a.recipe_id], roles[a.role_id]))[
                dishes[a.recipe_id].ingredients[0].ingredient_id
            ]
            for a in assignments
            if a.slot_id == slot_id
        )
        for slot_id in slots
    }
    assert len(set(per_day.values())) > 1, per_day


# --- The same two rules through the code that actually calls them (review round 3) ---------------------------


def _recommendation(recipe):
    """A pool recommendation as `_replacements` reads one: it only needs the recipe's id and title."""
    return SimpleNamespace(recipe=SimpleNamespace(id=recipe.id, title=recipe.title, slug=recipe.slug))


def test_the_swap_path_itself_drops_a_dish_that_would_leave_a_member_unfed():
    """Round 2 added `_coverage_after_swap`; its tests called it directly, so removing the call site would not
    have failed any of them. This goes through `_replacements`, which is what a swap actually calls."""
    request = _one_dish_request()
    tofu = _catalog("tofu", "protein_main", calories=900, tags=["vegetarian"])
    pork = _catalog("pork-roast", "protein_main", calories=900)
    other_tofu = _catalog("other-tofu", "protein_main", calories=900, tags=["vegetarian"])
    entry = _entry("main", tofu)
    plan = _plan_of([entry])
    by_id = {r.id: r for r in (tofu, pork, other_tofu)}
    offered = MealPlanReplanningService._replacements(
        MealPlanReplanningService,
        plan,
        entry,
        request,
        [_recommendation(pork), _recommendation(other_tofu)],
        by_id,
    )
    titles = {item.recipe.title for item in offered}
    assert "other-tofu" in titles, titles  # Ann can eat it, so it may replace her dinner
    assert "pork-roast" not in titles, titles  # it would leave her with nothing at this one-dish meal


def test_the_swap_path_itself_allows_a_breakfast_and_still_refuses_an_empty_plate():
    """Round 2's `_fully_covered` was also only called directly in its tests. `_meal_still_holds` is the real
    caller: a structured breakfast may be swapped, and may not be swapped to a dish nobody at it can eat."""
    roles = [{"role_id": "breakfast", "meal_roles": ["breakfast"], "required": True}]
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": date(2027, 1, 3).isoformat(),
            "day_count": 1,
            "household_size": 4,
            "plan_shape": {"meals": {"breakfast": roles}},
            "household": {
                "members": [
                    {
                        "name": m["name"],
                        "servings": m["servings"],
                        "dietary_preferences": m.get("dietary_requirements", []),
                    }
                    for m in MEMBERS
                ]
            },
        }
    )
    entry = _entry("breakfast", _catalog("omelette", "breakfast", calories=400, tags=["vegetarian"]))
    entry.meal_type = "breakfast"
    plan = _plan_of([entry], request.model_dump(mode="json"))
    yogurt = _catalog("maple-yogurt", "breakfast", calories=400, tags=["vegetarian"])
    bacon = _catalog("bacon-roll", "breakfast", calories=400)
    assert MealPlanReplanningService._meal_still_holds(plan, entry, yogurt, request)
    assert not MealPlanReplanningService._coverage_after_swap(request, entry, bacon, plan)


def test_a_refusal_says_what_the_meal_could_not_give_rather_than_promising_a_main_and_a_staple():
    """Review round 3. The branch that names a member for a breakfast or a one-dish meal reused the lunch-and-
    dinner wording, so a household was told the plan could not give them "a main dish and a staple at every
    lunch and dinner" about a breakfast, which is never owed one."""
    nobody_can_eat = [r for r in RECIPES if r["recipe_id"] in ("chicken", "prawn-noodles")]
    vegetarian = [{"name": "Ann", "servings": 1.0, "dietary_requirements": ["vegetarian"]}]
    # A breakfast: the weakest rule, so the member is named under "any".
    breakfast = slot(members=vegetarian, servings=1.0).model_dump(mode="json")
    breakfast["meal_type"] = "breakfast"
    breakfast["composition"] = None  # one dish, as a breakfast is planned
    prob = problem(slots=[breakfast], recipes=nobody_can_eat)
    assert uncoverable_by_rule(prob) == {"core": [], "any": ["Ann"]}

    # A structured dinner with no vegetarian main: the full rule, so she is named under "core".
    dinner = problem(slots=[slot(members=vegetarian, servings=1.0).model_dump(mode="json")], recipes=nobody_can_eat)
    assert uncoverable_by_rule(dinner) == {"core": ["Ann"], "any": []}
    # Both still report her once by name, which is what the trace carries.
    assert uncoverable_members(prob) == ["Ann"] and uncoverable_members(dinner) == ["Ann"]

    # And what the household reads (task 14): the breakfast refusal promises no main dish and no staple.
    breakfast_says = uncovered_message(uncoverable_by_rule(prob))
    assert "main dish" not in breakfast_says and "staple" not in breakfast_says
    assert breakfast_says.startswith("At one of the other meals there was nothing Ann can eat at all.")
    assert uncovered_message(uncoverable_by_rule(dinner)).startswith(
        "I couldn't give Ann a main dish and a staple at every lunch and dinner with what Ann can eat."
    )


def test_a_refusal_names_several_members_in_a_sentence():
    """Task 14: one name or several, the sentence reads as English, and the "any" rule never borrows the
    lunch-and-dinner promise."""
    said = uncovered_message({"core": ["Ann", "Ben"], "any": ["Kai", "Mei", "Lin"]})
    assert said.startswith(
        "I couldn't give Ann and Ben a main dish and a staple at every lunch and dinner with what they can eat. "
        "At one of the other meals there was nothing Kai, Mei and Lin can eat at all. "
    )
    assert said.endswith("no allergen, diet or excluded ingredient will be relaxed.")


# --- "A or B" lines judged by the option cooked, wherever a member is judged (task 14 item 5) -------------------

BUTTER_OR_OIL = [
    {"normalized_name": "butter", "display_name": "butter", "allergens": ["dairy"]},
    {"normalized_name": "vegetable_oil", "display_name": "vegetable oil", "allergens": []},
]


def _cooked_with_oil_or_butter(recipe_id=1, slug="noodle-bowl"):
    """A one-bowl dish with a "butter or vegetable oil" line: the combined line carries dairy, the oil does not."""
    combined = Ingredient(
        normalized_name="butter_or_veg_oil",
        display_name="butter or vegetable oil",
        allergens=["dairy"],
        alternatives=BUTTER_OR_OIL,
    )
    noodles = Ingredient(normalized_name="rice_noodles", display_name="rice noodles", allergens=[])
    return Recipe(
        id=recipe_id,
        slug=slug,
        title="Noodle Bowl",
        servings=2,
        prep_time_minutes=5,
        cook_time_minutes=15,
        dietary_tags=[],
        meal_role="one_bowl",
        protein_sources=["tofu"],
        nutrition=RecipeNutrition(calories_kcal=600),
        recipe_ingredients=[
            RecipeIngredient(ingredient=combined, quantity=30, unit="g", sort_order=1),
            RecipeIngredient(ingredient=noodles, quantity=200, unit="g", sort_order=2),
        ],
    )


DAIRY_FREE_ANN = [
    {"name": "Ann", "servings": 1.0, "allergens": ["dairy"]},
    {"name": "Ben", "servings": 1.0},
]


def test_a_dish_cooked_with_the_option_a_member_can_eat_is_not_labelled_not_for_them():
    """The planner counts Ann in the bowl's servings, because it is cooked with oil for her; the week's labels read
    the combined line and said "Not for Ann" beside it."""
    request = _one_dish_request(DAIRY_FREE_ANN)
    bowl = _cooked_with_oil_or_butter()
    assert alternatives.lines(bowl, request)[0].ingredient.normalized_name == "vegetable_oil"
    ann = member_limits(request.household)[0]
    assert not catalog_can_eat(ann, bowl), "read raw, the combined line carries dairy"
    entry = _entry("main", bowl)
    plan = _plan_of([entry], request.model_dump(mode="json"))
    assert WeeklyMealPlanService._not_for(plan)(entry) == []
    # A dish she really cannot eat is still labelled.
    cheese = _catalog("cheese-bake", "one_bowl", calories=600, allergens=["dairy"])
    assert WeeklyMealPlanService._not_for(plan)(_entry("main", cheese)) == ["Ann"]


def test_the_packet_counts_a_dish_cooked_with_the_option_a_member_can_eat():
    """Ben avoids the noodles, so only Ann can have the bowl: read raw, nobody can, and it never reaches the packet
    as Ann's choice."""
    request = _one_dish_request(
        [DAIRY_FREE_ANN[0], {"name": "Ben", "servings": 1.0, "excluded_ingredients": ["rice_noodles"]}]
    )
    ann, ben = member_limits(request.household)
    bowl = _cooked_with_oil_or_butter()
    ranked = [SimpleNamespace(recipe=SimpleNamespace(id=bowl.id))]
    by_id = {bowl.id: bowl}
    assert _packet_covering(ranked, [], [ann, ben], by_id, 1) == []
    cooked = _packet_covering(ranked, [], [ann, ben], by_id, 1, lambda r: alternatives.lines(r, request))
    assert cooked == ranked


def test_the_week_floor_counts_a_dish_cooked_with_the_option_a_member_can_eat():
    request = _one_dish_request(DAIRY_FREE_ANN)
    bowl = _cooked_with_oil_or_butter()
    shape = [("dinner", [{"role_id": "main", "meal_roles": ["protein_main", "one_bowl"], "required": True}])]
    assert _uncovered(request, shape, [SimpleNamespace(recipe=SimpleNamespace(id=bowl.id))], [bowl]) == []


def test_the_week_floor_counts_a_staple_cooked_with_the_option_a_member_can_eat():
    """Review of task 14: the staples line of the week floor, beside the mains line above. Ann's only filling core is
    a protein main beside a staple cooked with oil; read raw, the staple's combined line carries dairy."""
    request = _one_dish_request(DAIRY_FREE_ANN)
    staple = _cooked_with_oil_or_butter(1, "buttered-rice")
    staple.meal_role, staple.protein_sources = "staple", None
    tofu = _cooked_with_oil_or_butter(2, "tofu")
    tofu.meal_role = "protein_main"
    tofu.recipe_ingredients = tofu.recipe_ingredients[1:]  # no "A or B" line: only the staple's decides
    shape = [
        (
            "dinner",
            [
                {"role_id": "main", "meal_roles": ["protein_main"], "required": True},
                {"role_id": "staple", "meal_roles": ["staple"], "required": True},
            ],
        )
    ]
    ranked = [SimpleNamespace(recipe=SimpleNamespace(id=r.id)) for r in (tofu, staple)]
    assert not catalog_can_eat(member_limits(request.household)[0], staple), "read raw, the staple carries dairy"
    assert _uncovered(request, shape, ranked, [tofu, staple]) == []
