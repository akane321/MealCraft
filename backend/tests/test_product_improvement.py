from datetime import timedelta
from functools import partial

from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.meal_beam import MealBeamPlanner
from app.planning.product_improvement import adjacent_repetitions, improve_product_plan
from app.planning.product_path import product_validation
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


def test_product_keeps_beam_if_annealing_introduces_adjacent_repetition(monkeypatch):
    problem, _ = setup_problem()
    builder = MealBeamPlanner()
    seed = [PlanningAssignment(slot_id=s.slot_id, recipe_id=rid) for s, rid in zip(problem.slots, "ab", strict=True)]
    shopping = builder._build_shopping(problem, seed)
    report = builder.validator.validate(problem, seed, shopping)

    def adjacent(self, problem, *, initial, **kwargs):
        result = initial.model_copy(deep=True)
        result.assignments[1].recipe_id = result.assignments[0].recipe_id
        result.shopping = builder._build_shopping(problem, result.assignments)
        result.validation = builder.validator.validate(problem, result.assignments, result.shopping)
        return result

    monkeypatch.setattr(AnnealingPlanner, "solve", adjacent)
    result, trace = improve_product_plan(problem, (seed, shopping, report), dict.fromkeys("abc", 0))
    assert result[0] == seed
    assert trace["retained_beam_reason"] == "adjacent_repetition_increased"
    assert trace["adjacent_repetitions_before"] == trace["adjacent_repetitions_after"] == 0
    assert trace["adjacent_repetitions_proposed"] == 1
    assert trace["after"] == trace["before"]
    assert not trace["improved"]


def test_adjacent_repeat_guard_respects_exempt_roles_and_meals_not_input_order():
    problem, _ = setup_problem()
    dishes = [PlanningAssignment(slot_id=s.slot_id, recipe_id="a", role_id="staple") for s in problem.slots]
    assert adjacent_repetitions(problem, list(reversed(dishes))) == 1
    problem.uncounted_roles = ["staple"]
    assert adjacent_repetitions(problem, dishes) == 0


def test_improvement_preserves_hard_recipe_count_even_for_one_shared_title_kind():
    problem, _ = setup_problem(100)
    for recipe in problem.recipes:
        recipe.title = "Invented rice bowl"
    initial = [
        PlanningAssignment(slot_id=slot.slot_id, recipe_id=rid) for slot, rid in zip(problem.slots, "ab", strict=True)
    ]
    builder = MealBeamPlanner()
    shopping = builder._build_shopping(problem, initial)
    validate = partial(product_validation, builder.validator, minimum_distinct_dishes=2)
    report = validate(problem, initial, shopping)
    result, _ = improve_product_plan(problem, (initial, shopping, report), {"a": 1, "b": 1, "c": 0}, validate=validate)
    assert result[2].status == "passed"
    assert len({a.recipe_id for a in result[0]}) >= 2
    assert any(c.code == "minimum_distinct_dishes" for c in result[2].checks)


def test_improvement_checks_per_meal_budget_not_just_weekly_checkout():
    problem, _ = setup_problem(100)
    problem.recipes[2].ingredients[0].quantity = 1000
    initial = [PlanningAssignment(slot_id=slot.slot_id, recipe_id="a") for slot in problem.slots]
    builder = MealBeamPlanner()
    shopping = builder._build_shopping(problem, initial)
    validate = partial(product_validation, builder.validator, per_meal_budget=1.5)
    report = validate(problem, initial, shopping)
    assert report.status == "passed"
    result, _ = improve_product_plan(problem, (initial, shopping, report), {"a": 1, "b": 1, "c": 0}, validate=validate)
    assert result[2].status == "passed"
    assert "c" not in {a.recipe_id for a in result[0]}
    assert all(c.status == "passed" for c in result[2].checks if c.code == "per_meal_budget")
