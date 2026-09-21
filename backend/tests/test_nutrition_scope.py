from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.core.paths import repository_root
from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.nutrition_scope import compile_nutrition_targets, nutrition_guard_loss, nutrition_scope_notes
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.planning_nutrition import ProductNutritionTarget
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def packet(targets):
    source = FinalPlanningProblem.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/final-scope-multislot.json").read_text(encoding="utf-8")
    ).model_dump()
    recipes = []
    for rid, calories in [("low", 300), ("high", 700), ("even-a", 500), ("even-b", 500)]:
        r = deepcopy(source["recipes"][0])
        r.update(
            recipe_id=rid,
            servings=1,
            total_time_minutes=10,
            allowed_meal_types=["dinner"],
            allergens=[],
            ingredients=[dict(ingredient_id="rice", quantity=100, unit="g")],
        )
        r["nutrients_per_serving"]["calories_kcal"] = calories
        recipes.append(r)
    source.update(
        recipes=recipes,
        slots=[dict(slot_id=str(i), planned_date="2026-09-21", meal_type="dinner", servings=2) for i in range(2)],
        products=[
            dict(ingredient_id="rice", product_id="rice-bag", package_quantity=1000, package_unit="g", price_sgd=1)
        ],
        pantry=[],
        purchase_budget_sgd=None,
        allergens=[],
        dietary_requirements=[],
        health_preferences=[],
        nutrition_bands=[b.model_dump() for b in compile_nutrition_targets(targets, 0.25)],
    )
    return FinalPlanningProblem.model_validate(source)


def report(problem, choices):
    assignments = [
        PlanningAssignment(slot_id=s.slot_id, recipe_id=r) for s, r in zip(problem.slots, choices, strict=True)
    ]
    shopping = FinalScopeReferencePlanner()._build_shopping(problem, assignments)
    return FinalPlanningValidator().validate(problem, assignments, shopping)


def target(**kwargs):
    return ProductNutritionTarget(metric="calories_kcal", **kwargs)


def test_default_average_and_explicit_per_meal_produce_different_checks():
    average = packet([target(lower=450, upper=550)])
    per_meal = packet([target(lower=450, upper=550, scope="per_serving")])
    assert report(average, ["low", "high"]).status == "passed"
    assert report(per_meal, ["low", "high"]).status == "failed"
    assert any(c.status == "failed" and not c.hard for c in report(average, ["low", "high"]).checks)


def test_slot_average_does_not_sum_meals_on_same_day_or_multiply_servings():
    problem = packet([target(lower=500, upper=500)])
    result = report(problem, ["even-a", "even-b"])
    assert result.status == "passed"
    assert next(c.actual for c in result.checks if c.code.endswith("horizon_average")) == 500
    problem.nutrition_bands[0].average_basis = "represented_days"
    assert report(problem, ["even-a", "even-b"]).status == "failed"


def test_even_plan_scores_better_than_extremes_and_search_finds_it():
    problem = packet([target(lower=450, upper=550)])
    recipes = {r.recipe_id: r for r in problem.recipes}
    even = sum(nutrition_guard_loss(problem, recipes[r]) for r in ["even-a", "even-b"])
    extreme = sum(nutrition_guard_loss(problem, recipes[r]) for r in ["low", "high"])
    assert even < extreme
    solution = BeamPlanner(BeamLimits(width=64)).solve(problem)
    assert solution.status == "feasible"
    assert {a.recipe_id for a in solution.assignments} == {"even-a", "even-b"}


def test_same_catalog_different_scope_yields_different_valid_plan():
    average = packet([target(upper=550)])
    per_meal = packet([target(upper=550, scope="per_serving")])
    losses = {"low": 0, "high": 0, "even-a": 1, "even-b": 1}
    a = BeamPlanner(BeamLimits(width=64), local_losses=losses).solve(average)
    b = BeamPlanner(BeamLimits(width=64), local_losses=losses).solve(per_meal)
    assert a.status == b.status == "feasible"
    assert {x.recipe_id for x in a.assignments} == {"low", "high"}
    assert all(x.recipe_id != "high" for x in b.assignments)
    assert nutrition_scope_notes([target(upper=550)]) != nutrition_scope_notes([target(upper=550, scope="per_serving")])


def test_optional_slot_uses_selected_denominator_and_does_not_make_unsafe_bound():
    problem = packet([target(lower=500, upper=500)])
    problem.slots[1].required = False
    result = BeamPlanner().solve(problem)
    assert result.status == "feasible"
    assert all(a.recipe_id.startswith("even") for a in result.assignments)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"lower": 600, "upper": 500},
        {"upper": float("inf")},
        {"upper": float("nan")},
        {"upper": -1},
        {"upper": 500, "scope": "per_day"},
    ],
)
def test_invalid_target_rejected(values):
    with pytest.raises(ValidationError):
        target(**values)


@pytest.mark.parametrize("value", [-1, 2, float("nan"), float("inf")])
def test_guard_parameter_range(value):
    with pytest.raises(ValidationError):
        WeeklyMealPlanRequest(nutrition_guard_band=value)


def test_zero_bound_is_retained_and_scope_notes_are_concrete():
    bands = compile_nutrition_targets([target(upper=0, scope="per_serving")], 0.25)
    assert bands[0].upper == 0 and bands[0].hard
    assert "at most 0" in nutrition_scope_notes([target(upper=0)])[0]


def test_empty_selected_average_is_indeterminate():
    problem = packet([target(upper=550)])
    for slot in problem.slots:
        slot.required = False
    result = FinalPlanningValidator().validate(problem, [], [])
    assert result.status == "indeterminate"


def test_missing_product_scope_does_not_change_evaluation_packet_default():
    assert target(upper=550).scope == "horizon_average"
    problem = packet([])
    from app.schemas.planning_v2 import PlanningNutritionBand

    problem.nutrition_bands = [PlanningNutritionBand(metric="calories_kcal", scope="horizon_average", upper=550)]
    assert problem.nutrition_bands[0].average_basis == "represented_days"
    assert report(problem, ["even-a", "even-b"]).status == "failed"


def test_documented_fixture_requests_and_large_bounds():
    import json

    data = json.loads((repository_root() / "data/fixtures/planning-v2/nutrition-scope-requests-v1.json").read_text())
    for request in data["requests"]:
        compiled = WeeklyMealPlanRequest.model_validate(request)
        assert compiled.nutrition_constraints
    with pytest.raises(ValidationError):
        target(upper=1e308)


def test_user_scope_notes_include_units():
    assert nutrition_scope_notes([target(upper=500, scope="per_serving")]) == [
        "Energy: at most 500 kcal per person for each planned meal."
    ]


def test_nutrition_and_diversity_rules_work_together():
    from app.planning.exhaustive_oracle import exhaustive_assignments
    from tests.test_planning_diversity import packet as diversity_packet

    problem = diversity_packet()
    problem.nutrition_bands = compile_nutrition_targets([target(upper=500)], 0.25)
    problem.recipes[0].nutrients_per_serving.calories_kcal = 700
    beam = BeamPlanner(BeamLimits(width=256)).solve(problem)
    oracle = exhaustive_assignments(problem)
    assert beam.status == "feasible"
    assert tuple((a.slot_id, a.recipe_id) for a in beam.assignments) == oracle.best_choices
    assert len({a.recipe_id for a in beam.assignments}) == len(problem.slots)
    assert all(a.recipe_id != problem.recipes[0].recipe_id for a in beam.assignments)
