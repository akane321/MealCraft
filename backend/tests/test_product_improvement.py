from datetime import timedelta

from app.planning.meal_beam import MealBeamPlanner
from app.planning.product_improvement import improve_product_plan
from app.schemas.planning_v2 import PlanningAssignment
from tests.test_diversity_greedy import setup_problem


def test_two_trip_product_improvement_keeps_locked_meal_and_separate_budgets():
    problem, _ = setup_problem()
    problem.slots[0].locked_recipe_id = "a"
    problem.slots[1].planned_date += timedelta(days=7)
    problem.slots[1].trip = 2
    initial = [PlanningAssignment(slot_id=s.slot_id, recipe_id="a") for s in problem.slots]
    builder = MealBeamPlanner()
    shopping = builder._build_shopping(problem, initial)
    report = builder.validator.validate(problem, initial, shopping)
    assert report.status == "passed" and report.purchase_total_sgd == 4
    result, evidence = improve_product_plan(problem, (initial, shopping, report), dict.fromkeys("abc", 0))
    assert evidence["improved"]
    assert result[2].status == "passed"
    assert result[2].purchase_total_sgd == 4
    assert next(a.recipe_id for a in result[0] if a.slot_id == "s0") == "a"
    assert len({a.recipe_id for a in result[0]}) == 2
    assert [a.recipe_id for a in initial] == ["a", "a"]


def test_product_improvement_is_repeatable_and_never_worsens_incumbent():
    problem, _ = setup_problem()
    beam = MealBeamPlanner().solve(problem)
    seed = (beam.assignments, beam.shopping, beam.validation)
    first, a = improve_product_plan(problem, seed, dict.fromkeys("abc", 0))
    second, b = improve_product_plan(problem, seed, dict.fromkeys("abc", 0))
    assert first == second
    assert a["after"] == b["after"] <= a["before"]
