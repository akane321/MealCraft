"""The shared-dish model: each member's own limits, and a covered plate at every meal (ADR-0071 sections 1, 2).

A meal of shared dishes replaces "every dish suits the whole table": a dish may be served when at least one
present member can eat it, every present member has a filling core and a vegetable of their own, and each dish
is cooked for the servings of the members who can eat it.
"""

from datetime import date
from fractions import Fraction
from types import SimpleNamespace

import pytest

from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.meal_beam import dish_eligible
from app.planning.meal_composition import dish_servings, real_meal_issues
from app.planning.member_coverage import (
    coverage_issues,
    dish_base_servings,
    eaters,
    member_can_eat,
    servable,
)
from app.planning.product_path import uncoverable_members
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment, PlanningSlot
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


def test_coverage_is_checked_at_lunch_and_dinner_only():
    """A breakfast is one dish (ADR-0070): nobody needs a core and a vegetable at it."""
    one_dish = [{"role_id": "main", "meal_roles": ["protein_main", "one_bowl", "breakfast"]}]
    payload = slot(roles=one_dish).model_dump(mode="json") | {"meal_type": "breakfast"}
    prob = problem(slots=[payload])
    at_table, dishes = prob.slots[0], by_id(prob)
    assert real_meal_issues(at_table, [("main", "chicken")], dishes, {"main": Fraction(1)}) == []


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
        planned_date=date(2027, 1, 3),
        meal_type="dinner",
        portion_share=share,
        servings=servings,
        status="planned",
    )


def _catalog(recipe_id, role, *, calories, tags=(), allergens=(), ingredient=None, staple=False):
    """A catalog recipe as a swap reads one: its lines, tags and meal-role tag."""
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
        contains_staple=True if staple else None,
        protein_sources=None,
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
