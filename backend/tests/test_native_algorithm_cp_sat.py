import pytest

from app.planning.algorithm_reference import EnumeratedReference
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.schemas.planning_v2 import PlanningNutritionBand, PlanningProductOption
from tests.test_algorithm_cp_sat import household_week
from tests.test_diversity_greedy import setup_problem


def test_native_matches_full_enumeration():
    problem, objective = setup_problem()
    native = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert native["status"] == "optimal_for_native_model", native
    assert native["score"] == exact["score"]
    assert native["meal_variables"] == 6


def test_native_household_week_nutrition_and_two_shops():
    problem, objective = household_week()
    native = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert native["status"] == "optimal_for_native_model", native
    assert native["score"] == exact["score"]
    assert native["meal_variables"] == 14
    assert sum(r["pantry_deduction"] for r in native["shopping"]) == 300


def test_native_does_not_relax_budget():
    problem, objective = setup_problem(1.99)
    assert NativeSharedScoreCpSat(objective).solve_exact(problem)["status"] == "infeasible"


@pytest.mark.parametrize("bounds", [{"lower": 10000}, {"upper": 1}])
def test_native_day_and_horizon_bounds_reject_impossible_cases(bounds):
    problem, objective = household_week()
    for scope in ("per_day", "horizon_average"):
        problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope=scope, **bounds)]
        assert NativeSharedScoreCpSat(objective).solve_exact(problem)["status"] == "infeasible"


@pytest.mark.parametrize("price", [0.7, 1.2, 2.01])
def test_multiple_package_sizes_match_reference_checkout(price):
    problem, objective = setup_problem()
    problem.products.append(
        PlanningProductOption(
            ingredient_id="rice",
            product_id="small",
            package_quantity=100,
            package_unit="g",
            price_sgd=price,
        )
    )
    native = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert native["status"] == "optimal_for_native_model"
    assert native["score"] == exact["score"]


@pytest.mark.parametrize("scope", ["per_dish", "per_slot", "per_day", "horizon_average"])
def test_native_soft_nutrition_matches_enumeration(scope):
    problem, objective = setup_problem()
    problem.recipes[0].nutrients_per_serving.calories_kcal = 300
    problem.nutrition_bands = [
        PlanningNutritionBand(metric="calories_kcal", scope=scope, lower=550, upper=650, hard=False)
    ]
    objective.scales[f"nutrition_calories_kcal_{scope}"] = 500
    native = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert native["status"] == "optimal_for_native_model", native
    assert native["score"] == exact["score"]


@pytest.mark.parametrize(
    "rules",
    [
        {"max_uses_per_recipe": 1},
        {"recipe_counts": [{"recipe_id": "b", "min_uses": 2, "max_uses": 2}]},
        {"ingredient_meals": [{"ingredient_id": "rice", "min_meals": 2}]},
    ],
)
def test_explicit_repetition_rules_match_enumeration(rules):
    from app.schemas.planning_v2 import PlanningRepetitionRules

    problem, objective = setup_problem()
    problem.repetition_rules = PlanningRepetitionRules.model_validate(rules)
    native = NativeSharedScoreCpSat(objective).solve_exact(problem)
    exact = EnumeratedReference(objective).solve_reference(problem)
    assert native["status"] == "optimal_for_native_model", native
    assert native["score"] == exact["score"]


def test_impossible_explicit_count_is_infeasible():
    from app.schemas.planning_v2 import PlanningRepetitionRules

    problem, objective = setup_problem()
    problem.repetition_rules = PlanningRepetitionRules(recipe_counts=[{"recipe_id": "a", "min_uses": 3}])
    assert NativeSharedScoreCpSat(objective).solve_exact(problem)["status"] == "infeasible"


@pytest.mark.parametrize("factory", [setup_problem, household_week])
def test_speed_optimizations_preserve_proven_score(factory):
    problem, objective = factory()
    planner = NativeSharedScoreCpSat(objective)
    baseline = planner.solve_exact(problem, optimize=False)
    optimized = planner.solve_exact(problem, optimize=True)
    assert baseline["status"] == optimized["status"] == "optimal_for_native_model"
    assert baseline["score"] == optimized["score"]
    assert optimized["workers"] == 4
    if problem.nutrition_bands:
        assert optimized["symmetry_pairs"] == 0
