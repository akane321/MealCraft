"""A meal of several dishes: roles, portion shares, meal time and dish-level safety (ADR-0036)."""

from datetime import date

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.mixed_shopping import derive_mixed_demands
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment

NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")


def recipe(recipe_id, course, prep, cook, *, calories, allergens=(), ingredient=None):
    return {
        "recipe_id": recipe_id,
        "title": recipe_id,
        "servings": 4,
        "allowed_meal_types": ["dinner"],
        "total_time_minutes": prep + cook,
        "prep_minutes": prep,
        "cook_minutes": cook,
        "passive_minutes": 0,
        "course": course,
        "allergens": list(allergens),
        "ingredients": [{"ingredient_id": ingredient or f"{recipe_id}-base", "quantity": 400, "unit": "g"}],
        "nutrients_per_serving": {**dict.fromkeys(NUTRIENTS, 0), "calories_kcal": calories},
    }


def problem(**changes) -> FinalPlanningProblem:
    recipes = [
        recipe("chicken", "main", 15, 25, calories=500),
        recipe("greens", "side", 10, 22, calories=100),
        recipe("broth", "soup", 15, 30, calories=200),
        recipe("peanut-slaw", "side", 10, 0, calories=150, allergens=["peanut"]),
    ]
    payload = {
        "problem_id": "meal-composition",
        "slots": [
            {
                "slot_id": "d1",
                "planned_date": date(2026, 9, 28).isoformat(),
                "meal_type": "dinner",
                "servings": 4,
                "max_time_minutes": 120,
                "composition": [
                    {"role_id": "main", "courses": ["main"]},
                    {"role_id": "vegetable", "courses": ["side", "salad"]},
                    {"role_id": "soup", "courses": ["soup"], "required": False},
                ],
            }
        ],
        "recipes": recipes,
        "products": [
            {
                "ingredient_id": f"{r['recipe_id']}-base",
                "product_id": f"p-{r['recipe_id']}",
                "package_quantity": 100,
                "package_unit": "g",
                "price_sgd": 1.0,
            }
            for r in recipes
        ],
        "allergens": ["peanut"],
        "allergen_vocabulary": ["peanut"],
        "catalog_version": "test",
        "product_snapshot_version": "test",
        "policy_version": "test",
    }
    payload.update(changes)
    return FinalPlanningProblem.model_validate(payload)


def meal(*dishes):
    return [PlanningAssignment(slot_id="d1", role_id=role, recipe_id=recipe_id) for role, recipe_id in dishes]


def validate(packet, assignments):
    shopping = FinalScopeReferencePlanner()._build_shopping(packet, assignments)
    return FinalPlanningValidator().validate(packet, assignments, shopping), shopping


def failed(report):
    return {check.code for check in report.checks if check.status == "failed" and check.hard}


def test_three_dish_meal_scales_each_dish_to_its_portion_share():
    packet = problem()
    report, shopping = validate(packet, meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth")))

    assert report.status == "passed", report.checks
    required = {line.ingredient_id: line.required_quantity for line in shopping}
    # 400 g serves 4; the household of 4 eats 0.6 of a main and 0.4 of each other dish.
    assert required == {"chicken-base": 240, "greens-base": 160, "broth-base": 160}
    demands, issues = derive_mixed_demands(
        packet, meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth"))
    )
    assert not issues
    assert {d.ingredient_id: d.required_quantity for d in demands} == required


def test_a_role_takes_only_its_courses_and_required_roles_must_be_filled():
    report, _ = validate(problem(), meal(("main", "broth"), ("soup", "chicken")))

    assert {"meal_role_course", "meal_role_missing"} <= failed(report)


def test_every_dish_is_checked_for_safety_not_just_the_main():
    report, _ = validate(problem(), meal(("main", "chicken"), ("vegetable", "peanut-slaw")))

    allergen = [check for check in report.checks if check.code == "allergen"]
    assert allergen and all(check.status == "failed" for check in allergen)


def test_meal_time_is_the_one_cook_estimate_not_the_longest_dish():
    packet = problem()
    packet.slots[0].max_time_minutes = 100
    report, _ = validate(packet, meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth")))

    time = next(check for check in report.checks if check.code == "time_limit")
    # Each dish alone is at most 45 minutes; the meal is 105 (ADR-0036 section 3).
    assert (time.status, time.actual) == ("failed", 105)


def test_meal_nutrition_is_the_share_weighted_sum_and_dish_bands_see_each_dish():
    packet = problem(
        nutrition_bands=[
            {"metric": "calories_kcal", "scope": "per_slot", "upper": 400},
            {"metric": "calories_kcal", "scope": "per_dish", "upper": 450},
        ]
    )
    report, _ = validate(packet, meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth")))

    by_scope = {(c.code, c.scope_id): c for c in report.checks if c.code.startswith("nutrition_")}
    # 0.6 * 500 + 0.4 * 100 + 0.4 * 200 = 420 kcal a person.
    assert by_scope["nutrition_calories_kcal_per_slot", "d1"].actual == 420
    assert by_scope["nutrition_calories_kcal_per_slot", "d1"].status == "failed"
    assert by_scope["nutrition_calories_kcal_per_dish", "d1/main"].status == "failed"
    assert by_scope["nutrition_calories_kcal_per_dish", "d1/vegetable"].status == "passed"


def test_a_meal_repeats_no_dish_and_names_only_its_own_roles():
    repeated, _ = validate(problem(), meal(("main", "chicken"), ("vegetable", "chicken")))
    unknown, _ = validate(problem(), meal(("main", "chicken"), ("vegetable", "greens"), ("dessert", "broth")))

    assert "meal_duplicate_dish" in failed(repeated)
    assert "meal_role" in failed(unknown)


def test_meal_beam_plans_a_composed_meal_the_validator_accepts():
    from app.planning.meal_beam import MealBeamPlanner

    solution = MealBeamPlanner().solve(problem())

    assert solution.status == "feasible", solution.validation.checks
    roles = {a.role_id: a.recipe_id for a in solution.assignments}
    # The optional soup is filled because it fits the 120-minute meal.
    assert roles == {"main": "chicken", "vegetable": "greens", "soup": "broth"}
    assert "peanut-slaw" not in roles.values()
    assert solution == MealBeamPlanner().solve(problem())


def test_meal_beam_drops_an_optional_dish_the_meal_time_cannot_hold():
    from app.planning.meal_beam import MealBeamPlanner

    packet = problem()
    packet.slots[0].max_time_minutes = 70  # main + vegetable is 70; adding the soup is 105
    solution = MealBeamPlanner().solve(packet)

    assert solution.status == "feasible", solution.validation.checks
    assert {a.role_id for a in solution.assignments} == {"main", "vegetable"}


def test_meal_beam_plans_one_dish_slots_like_before():
    from app.planning.meal_beam import MealBeamPlanner
    from tests.test_planning_v2 import load_problem

    solution = MealBeamPlanner().solve(load_problem())

    assert solution.status == "feasible", solution.validation.checks
    assert all(a.role_id is None for a in solution.assignments)


def test_cp_sat_reaches_the_meal_beam_objective_and_proves_it():
    from app.planning.meal_beam import MealBeamPlanner
    from app.planning.meal_cp_sat import MealCpSatLimits, MealCpSatPlanner

    for limit in (120, 70):
        packet = problem()
        packet.slots[0].max_time_minutes = limit
        exact = MealCpSatPlanner(MealCpSatLimits(max_time_seconds=10, max_deterministic_time=10)).solve_exact(packet)
        beam_loss = min(state.loss for state in MealBeamPlanner().search_candidates(packet).states)

        assert exact.status == "optimal" and exact.solution.status == "feasible"
        assert abs(exact.objective - beam_loss) < 0.005  # the same objective, in thousandths


def test_cp_sat_proves_a_budget_no_plan_can_meet():
    from app.planning.meal_cp_sat import MealCpSatLimits, MealCpSatPlanner

    packet = problem(purchase_budget_sgd=1.0)  # the cheapest meal needs several S$1 packages
    solution = MealCpSatPlanner(MealCpSatLimits(max_time_seconds=10, max_deterministic_time=10)).solve(packet)

    assert solution.status == "infeasible" and not solution.assignments


def three_days(**changes):
    base = problem().model_dump(mode="json")
    base["recipes"] += [
        recipe("beef", "main", 10, 20, calories=520),
        recipe("beans", "side", 5, 10, calories=120, ingredient="beans-base"),
    ]
    base["products"].append(
        {
            "ingredient_id": "beans-base",
            "product_id": "p-beans",
            "package_quantity": 100,
            "package_unit": "g",
            "price_sgd": 1.0,
        }
    )
    base["products"].append(
        {
            "ingredient_id": "beef-base",
            "product_id": "p-beef",
            "package_quantity": 100,
            "package_unit": "g",
            "price_sgd": 1.0,
        }
    )
    base["slots"] = [
        {**base["slots"][0], "slot_id": f"d{i}", "planned_date": f"2026-09-{28 + i:02d}"} for i in range(3)
    ]
    base.update(changes)
    return FinalPlanningProblem.model_validate(base)


def planners():
    from app.planning.meal_beam import MealBeamPlanner
    from app.planning.meal_cp_sat import MealCpSatLimits, MealCpSatPlanner

    return MealBeamPlanner(), MealCpSatPlanner(MealCpSatLimits(max_time_seconds=10, max_deterministic_time=10))


def test_a_dish_the_household_asks_for_twice_is_planned_twice_by_both_planners():
    packet = three_days(repetition_rules={"recipe_counts": [{"recipe_id": "beef", "min_uses": 2}]})

    for planner in planners():
        solution = planner.solve(packet)
        assert solution.status == "feasible", (planner, solution.validation.checks)
        assert sum(a.recipe_id == "beef" for a in solution.assignments) >= 2


def test_an_ingredient_asked_for_in_every_meal_and_no_repeats_are_hard_rules():
    wanted = three_days(repetition_rules={"ingredient_meals": [{"ingredient_id": "beans-base", "min_meals": 3}]})
    for planner in planners():
        solution = planner.solve(wanted)
        assert solution.status == "feasible"
        assert sum(a.recipe_id == "beans" for a in solution.assignments) == 3  # beans are the only dish with beans

    # Two mains cannot fill three dinners without repeating one.
    no_repeats = three_days(repetition_rules={"max_uses_per_recipe": 1})
    beam, exact = planners()
    assert beam.solve(no_repeats).status == "candidate_rejected"
    assert exact.solve(no_repeats).status == "infeasible"


def test_the_validator_reports_a_broken_repetition_rule():
    packet = three_days(repetition_rules={"recipe_counts": [{"recipe_id": "beef", "min_uses": 2}]})
    assignments = [
        PlanningAssignment(slot_id=f"d{i}", role_id=role, recipe_id=recipe_id)
        for i in range(3)
        for role, recipe_id in (("main", "chicken"), ("vegetable", "greens"))
    ]
    report, _ = validate(packet, assignments)

    assert "repetition_rule" in failed(report)


def test_meal_beam_keeps_a_cheap_dish_in_reach_of_a_hard_budget():
    """The beam ranks dishes by loss; under a budget the cheap ones must stay candidates."""
    from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner

    base = problem().model_dump(mode="json")
    # Two mains the loss cannot tell apart, so the id decides: the dear one ranks first.
    base["recipes"] += [
        recipe("aaa-dear", "main", 15, 25, calories=500, ingredient="dear-base"),
        recipe("zzz-cheap", "main", 15, 25, calories=500, ingredient="cheap-base"),
    ]
    base["products"] += [
        {
            "ingredient_id": "dear-base",
            "product_id": "p-dear",
            "package_quantity": 100,
            "package_unit": "g",
            "price_sgd": 20.0,
        },
        {
            "ingredient_id": "cheap-base",
            "product_id": "p-cheap",
            "package_quantity": 100,
            "package_unit": "g",
            "price_sgd": 1.0,
        },
    ]
    base["purchase_budget_sgd"] = 8.0  # the dear main alone busts it; the cheap week does not
    base["budget_is_hard"] = True
    packet = FinalPlanningProblem.model_validate(base)

    solution = MealBeamPlanner(MealBeamLimits(candidates_per_role=1)).solve(packet)

    assert solution.status == "feasible", solution.validation.checks
    assert sum(line.purchase_cost_sgd for line in solution.shopping) <= 8.0
