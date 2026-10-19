"""The full meal structure's hard rules (ADR-0070) on toy problems, through the meal beam and the validator."""

from datetime import date, timedelta

import pytest

from app.data import meal_structure
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.meal_beam import MealBeamPlanner
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShape, default_plan_shape
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment, PlanningMealRole

NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")


def recipe(
    recipe_id, meal_role, *, kcal=500, proteins=(), ingredient=None, staple=None, equipment=None, perishable=None
):
    return {
        "recipe_id": recipe_id,
        "title": recipe_id,
        "servings": 4,
        "allowed_meal_types": ["lunch", "dinner"],
        "total_time_minutes": 30,
        "course": "main",
        "ingredients": [{"ingredient_id": ingredient or f"{recipe_id}-base", "quantity": 400, "unit": "g"}],
        "nutrients_per_serving": {**dict.fromkeys(NUTRIENTS, 0), "calories_kcal": kcal},
        "meal_role": meal_role,
        "contains_staple": staple,
        "protein_sources": list(proteins),
        "equipment": equipment,
        "perishable": perishable,
    }


RECIPES = [
    recipe("chicken", "protein_main", kcal=600, proteins=["chicken"]),
    recipe("chicken-two", "protein_main", kcal=600, proteins=["chicken"]),
    recipe("duck", "protein_main", kcal=600, proteins=["duck"]),
    recipe("bowl", "one_bowl", kcal=700, proteins=["pork"], staple=True),
    recipe("rice", "staple", kcal=300),
    recipe("greens", "vegetable", kcal=100, ingredient="spinach"),
    recipe("slaw", "salad", kcal=80, ingredient="cabbage"),
    recipe("broth", "soup", kcal=150),
    recipe("cake", "dessert", kcal=400),
]
DINNER = [
    {"role_id": "main", "meal_roles": ["protein_main", "one_bowl"]},
    {"role_id": "main-2", "meal_roles": ["protein_main"], "required": False},
    {"role_id": "vegetable", "meal_roles": ["vegetable", "salad"]},
    {"role_id": "soup", "meal_roles": ["soup"], "required": False},
    {"role_id": "staple", "meal_roles": ["staple"]},
]


def problem(*, days=1, composition=DINNER, floor=578.25, recipes=RECIPES, **changes) -> FinalPlanningProblem:
    payload = {
        "problem_id": "real-meal",
        "slots": [
            {
                "slot_id": f"d{day}",
                "planned_date": (date(2027, 1, 3) + timedelta(days=day - 1)).isoformat(),
                "meal_type": "dinner",
                "servings": 2,
                "composition": composition,
                "min_energy_kcal": floor,
                "days_after_shopping": (day - 1) % 7 + 1,
            }
            for day in range(1, days + 1)
        ],
        "recipes": recipes,
        "products": [
            {
                "ingredient_id": r["ingredients"][0]["ingredient_id"],
                "product_id": f"p-{r['recipe_id']}",
                "package_quantity": 100,
                "package_unit": "g",
                "price_sgd": 1.0,
            }
            for r in recipes
        ],
        "composition_policy": {"structured_shares": meal_structure.portion_shares()},
        "perishable_days": 3,
        "catalog_version": "test",
        "product_snapshot_version": "test",
        "policy_version": "test",
    }
    payload.update(changes)
    return FinalPlanningProblem.model_validate(payload)


def meal(*dishes, slot="d1"):
    return [PlanningAssignment(slot_id=slot, role_id=role, recipe_id=recipe_id) for role, recipe_id in dishes]


def failed(packet, assignments):
    shopping = FinalScopeReferencePlanner()._build_shopping(packet, assignments)
    report = FinalPlanningValidator().validate(packet, assignments, shopping)
    return {check.code for check in report.checks if check.status == "failed" and check.hard}


FULL = (("main", "chicken"), ("main-2", "duck"), ("vegetable", "greens"), ("soup", "broth"), ("staple", "rice"))


def test_a_full_meal_passes_and_shares_follow_the_structure():
    packet = problem()
    assert failed(packet, meal(*FULL)) == set()
    from app.planning.meal_composition import meal_shares

    shares = meal_shares(packet, packet.slots[0], list(FULL))
    assert {role: float(share) for role, share in shares.items()} == {
        "main": 0.5,
        "main-2": 0.5,
        "vegetable": 0.5,
        "soup": 0.5,
        "staple": 1.0,
    }


@pytest.mark.parametrize(
    ("dishes", "code"),
    [
        # A one-bowl dish carries its staple: no second one.
        ((("main", "bowl"), ("vegetable", "greens"), ("staple", "rice")), "meal_filling_core"),
        # A protein main needs its staple.
        ((("main", "chicken"), ("vegetable", "greens"), ("soup", "broth")), "meal_filling_core"),
        # Chicken twice among the mains.
        (
            (("main", "chicken"), ("main-2", "chicken-two"), ("vegetable", "greens"), ("staple", "rice")),
            "meal_protein_repeat",
        ),
        # A salad is no main, a dessert no part of a dinner.
        ((("main", "slaw"), ("vegetable", "greens"), ("staple", "rice")), "meal_role_tag"),
        ((("main", "chicken"), ("vegetable", "cake"), ("staple", "rice")), "meal_nonmeal_dish"),
        # Two optional dishes left out: one move only.
        ((("main", "chicken"), ("vegetable", "greens"), ("staple", "rice")), "meal_dish_count"),
        # The vegetable beside a protein main is required.
        ((("main", "chicken"), ("main-2", "duck"), ("soup", "broth"), ("staple", "rice")), "meal_role_missing"),
    ],
)
def test_each_hard_rule_is_refused_with_its_code(dishes, code):
    assert code in failed(problem(), meal(*dishes))


def test_chicken_and_duck_are_different_sources_and_a_bowl_may_skip_the_vegetable():
    assert failed(problem(), meal(*FULL)) == set()
    # A one-bowl dish, its soup, no staple and no vegetable: the vegetable is the meal's one move.
    assert failed(problem(), meal(("main", "bowl"), ("main-2", "duck"), ("soup", "broth"))) == set()


def test_energy_floor_is_hard():
    assert "meal_energy_floor" in failed(problem(floor=2000), meal(*FULL))


def test_the_beam_plans_only_real_meals_and_the_staple_repeats_under_a_cap_of_one():
    packet = problem(days=2, repetition_rules={"max_uses_per_recipe": 1})
    solution = MealBeamPlanner().solve(packet)
    assert solution.status == "feasible", [c for c in solution.validation.checks if c.status == "failed"]
    staples = [a.recipe_id for a in solution.assignments if a.role_id == "staple"]
    by_slot = {}
    for a in solution.assignments:
        by_slot.setdefault(a.slot_id, {})[a.role_id] = a.recipe_id
    # Rice may serve both dinners (only one staple exists), every other dish at most once.
    assert staples.count("rice") == len(staples) >= 1
    others = [a.recipe_id for a in solution.assignments if a.role_id != "staple"]
    assert len(others) == len(set(others))
    for dishes in by_slot.values():
        assert "cake" not in dishes.values() and dishes.get("main") not in {"slaw", "greens"}


def test_perishable_dish_after_day_three_and_missing_equipment_are_refused():
    tagged = [
        *RECIPES,
        recipe("salmon", "protein_main", kcal=600, proteins=["fish"], perishable=True),
        recipe("roast", "protein_main", kcal=600, proteins=["beef"], equipment=[["oven", "air_fryer"]]),
    ]
    late = problem(days=4, recipes=tagged)
    day_four = [(r, d) for r, d in FULL if r != "main"] + [("main", "salmon")]
    assert "perishable_within_days" in failed(late, meal(*day_four, slot="d4"))
    assert "perishable_within_days" not in failed(late, meal(*day_four, slot="d3"))
    no_oven = problem(recipes=tagged, missing_equipment=["oven"])
    roast = [(r, d) for r, d in FULL if r != "main"] + [("main", "roast")]
    assert "equipment" not in failed(no_oven, meal(*roast))  # an air fryer will do
    assert "equipment" in failed(problem(recipes=tagged, missing_equipment=["oven", "air_fryer"]), meal(*roast))
    solution = MealBeamPlanner().solve(problem(days=4, recipes=tagged))
    assert all(a.recipe_id != "salmon" for a in solution.assignments if a.slot_id == "d4")


def test_two_trips_shop_separately_and_hold_the_budget_on_each():
    packet = problem(days=8, purchase_budget_sgd=30)
    slots = [slot.model_copy(update={"trip": 1 + index // 7}) for index, slot in enumerate(packet.slots)]
    packet = packet.model_copy(update={"slots": slots})
    plan = [a for index in range(1, 9) for a in meal(*FULL, slot=f"d{index}")]
    shopping = FinalScopeReferencePlanner()._build_shopping(packet, plan)
    assert {line.trip for line in shopping} == {1, 2}
    rice = {line.trip: line.required_quantity for line in shopping if line.ingredient_id == "rice-base"}
    assert rice[1] == pytest.approx(7 * rice[2])  # seven dinners on the first trip, one on the second
    report = FinalPlanningValidator().validate(packet, plan, shopping)
    budgets = [c for c in report.checks if c.code == "purchase_budget"]
    assert [c.scope_id for c in budgets] == ["trip-1", "trip-2"]
    assert {c.scope_id: c.status for c in budgets} == {"trip-1": "failed", "trip-2": "passed"}


def test_legacy_roles_dump_as_before_and_kinds_do_not_mix():
    role = PlanningMealRole(role_id="main", courses=["main"])
    assert role.model_dump() == {"role_id": "main", "courses": ["main"], "required": True}
    with pytest.raises(ValueError):
        PlanningMealRole(role_id="main", courses=["main"], meal_roles=["protein_main"])
    with pytest.raises(ValueError):
        MealPlanShape.model_validate({"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}, DINNER[0]]}})
    # A structured lunch needs its staple; a salad fills only the vegetable dish.
    with pytest.raises(ValueError):
        MealPlanShape.model_validate({"meals": {"lunch": [{"role_id": "main", "meal_roles": ["protein_main"]}]}})
    with pytest.raises(ValueError):
        MealPlanShape.model_validate({"meals": {"lunch": [{"role_id": "main", "meal_roles": ["one_bowl", "salad"]}]}})
    assert MealPlanShape.model_validate({"meals": {"dinner": MEAL_PRESETS["dinner"]["one main"]}})


def test_the_default_is_the_full_structure_and_dinner_grows_with_the_people():
    from app.planning.product_path import meal_structure_roles, people_at

    shape = default_plan_shape()
    assert list(shape.meals) == ["breakfast", "lunch", "dinner"]
    counts = {}
    for people in (1, 2, 3, 4, 5, 6, 7, 8):
        kinds = [role.role_id.split("-")[0] for role in meal_structure_roles(shape.meals["dinner"], people)]
        counts[people] = (kinds.count("main"), kinds.count("vegetable"), kinds.count("soup"), kinds.count("staple"))
    assert counts == {
        1: (1, 1, 1, 1),
        2: (1, 1, 1, 1),
        3: (2, 1, 1, 1),
        4: (2, 1, 1, 1),
        5: (2, 2, 1, 1),
        6: (2, 2, 1, 1),
        7: (3, 2, 1, 1),
        8: (3, 2, 1, 1),
    }
    assert [people_at(s) for s in (0.73, 2.49, 2.5, 4.89)] == [1, 2, 3, 5]
    # A household of members counts the members present, not their portions: two adults and three toddlers are
    # five at the table (the 5-6 row) on about 3.3 portions.
    from datetime import date

    from app.planning.household_slots import slot_people, slot_servings
    from app.schemas.household_rules import HouseholdPlanning

    servings = [1.0, 1.0, 0.43, 0.47, 0.43, 0.7]
    household = HouseholdPlanning.model_validate(
        {"members": [{"name": f"M{n}", "servings": s, "default_present": n < 5} for n, s in enumerate(servings)]}
    )
    assert slot_servings(household, date(2027, 1, 4), "dinner") == pytest.approx(3.33)
    assert slot_people(household, date(2027, 1, 4), "dinner") == 5
    assert meal_structure.dinner_counts()[0] == {
        "min_people": 1,
        "max_people": 2,
        "protein_mains": 1,
        "vegetables": 1,
        "soup": 1,
        "staple": 1,
    }


def test_core_combinations_skip_only_meals_whose_filling_core_fails():
    """The meal beam's speed-up leaves out exactly the combinations `real_meal_issues` refuses for their core."""
    from itertools import product

    from app.planning.meal_beam import core_combinations
    from app.planning.meal_composition import real_meal_issues

    built = problem()
    slot = built.slots[0]
    by_id = {r.recipe_id: r for r in built.recipes}
    roles = slot.composition
    options = {
        "main": ["chicken", "duck", "bowl"],
        "main-2": ["chicken-two", "duck", None],
        "vegetable": ["greens", "slaw", None],
        "soup": ["broth", None],
        "staple": ["rice", None],
    }
    per_role = [[None if o is None else (role.role_id, o) for o in options[role.role_id]] for role in roles]
    kept = set(core_combinations(per_role, roles, by_id, "dinner"))
    for combination in product(*per_role):
        dishes = tuple(d for d in combination if d is not None)
        core_fails = any(code == "meal_filling_core" for code, *_ in real_meal_issues(slot, dishes, by_id, None))
        assert (combination in kept) is not core_fails, combination
    # A breakfast, or any meal with no meal-role core, keeps every combination.
    assert set(core_combinations(per_role, roles, by_id, None)) == set(product(*per_role))
