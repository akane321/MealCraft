from pathlib import Path

import pytest

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def packet(scope="per_day"):
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"
    data = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8")).model_dump()
    recipe = data["recipes"][0]
    recipes = []
    for name, protein in [("a", 10), ("b", 50)]:
        r = dict(recipe, recipe_id=name, total_time_minutes=10)
        r["nutrients_per_serving"] = dict(recipe["nutrients_per_serving"], protein_g=protein)
        recipes.append(r)
    slot = data["slots"][0]
    data.update(
        recipes=recipes,
        slots=[dict(slot, slot_id=str(i), locked_recipe_id=None, max_time_minutes=20) for i in range(2)],
        nutrition_bands=[
            {"metric": "protein_g", "scope": scope, "lower": 100 if scope != "per_slot" else 50, "hard": False}
        ],
        preference_weights={"nutrition": 1, "variety": 0, "time": 0, "pantry": 0, "health": 0},
        health_preferences=[],
        purchase_budget_sgd=None,
    )
    return FinalPlanningProblem.model_validate(data)


def choose(recipe):
    return [PlanningAssignment(slot_id=str(i), recipe_id=recipe) for i in range(2)]


@pytest.mark.parametrize("scope", ["per_slot", "per_day", "horizon_average"])
def test_user_target_deviation_has_hand_calculated_value(scope):
    problem = packet(scope)
    assert score_plan(problem, choose("a")).total_loss == pytest.approx(0.8, abs=1e-6)
    assert score_plan(problem, choose("b")).total_loss == 0
    problem.slots[0].servings = 10
    assert score_plan(problem, choose("b")).total_loss == 0


def test_whole_plan_beam_and_oracle_use_same_objective():
    problem = packet()
    policy = WholePlanPolicy()
    result = BeamPlanner(BeamLimits(width=8), policy).solve(problem)
    oracle = exhaustive_assignments(problem, scoring_policy=policy)
    assert result.status == "feasible"
    assert all(a.recipe_id == "b" for a in result.assignments)
    assert score_plan(problem, result.assignments, policy).total_loss == oracle.best_loss == 0


def test_missing_dimensions_are_removed_from_weight_denominator():
    problem = packet().model_copy(update={"nutrition_bands": []})
    data = problem.model_dump()
    data["preference_weights"] = {"nutrition": 1, "time": 1, "variety": 0, "pantry": 0, "health": 0}
    problem = FinalPlanningProblem.model_validate(data)
    result = score_plan(problem, choose("a"))
    assert result.total_loss == 0.5
    assert next(c for c in result.components if c.name == "nutrition").loss is None


def test_incomplete_assignments_cannot_be_scored_as_a_complete_plan():
    with pytest.raises(ValueError):
        score_plan(packet(), [])


def test_soft_preference_cannot_override_failed_hard_constraints():
    problem = packet()
    problem = problem.model_copy(update={"allergens": problem.recipes[0].allergens})
    assert BeamPlanner(scoring_policy=WholePlanPolicy()).solve(problem).status == "candidate_rejected"


def test_priority_pantry_ranking_does_not_deduct_unknown_stock():
    problem = packet()
    data = problem.model_dump()
    data.update(
        preference_weights={"nutrition": 0, "time": 0, "variety": 0, "pantry": 1, "health": 0},
        pantry=[{"ingredient_id": problem.recipes[0].ingredients[0].ingredient_id, "priority_use": True}],
    )
    problem = FinalPlanningProblem.model_validate(data)
    assert score_plan(problem, choose("a")).total_loss == 0
    assert problem.pantry[0].quantity is None


@pytest.mark.parametrize("scope", ["per_slot", "per_day", "horizon_average"])
def test_experimental_nutrition_bound_is_below_every_completion(scope):
    from itertools import product

    from app.planning.constraint_compiler import compile_search_domains
    from app.planning.whole_plan_scoring import nutrition_lower_bound

    problem = packet(scope)
    domains = {slot.slot_id: slot for slot in compile_search_domains(problem).slots}
    policy = WholePlanPolicy()
    for prefix_length in range(3):
        for prefix in product("ab", repeat=prefix_length):
            choices = tuple((str(i), r) for i, r in enumerate(prefix))
            lower = nutrition_lower_bound(problem, choices, problem.slots[prefix_length:], domains, policy)
            for suffix in product("ab", repeat=2 - prefix_length):
                assignments = [PlanningAssignment(slot_id=str(i), recipe_id=r) for i, r in enumerate(prefix + suffix)]
                assert lower <= score_plan(problem, assignments, policy).total_loss + 1e-12


def test_health_preferences_use_catalog_values_without_inventing_a_target():
    problem = packet()
    data = problem.model_dump()
    data["recipes"][0]["nutrients_per_serving"]["sugar_g"] = 5
    data["recipes"][1]["nutrients_per_serving"]["sugar_g"] = 20
    data.update(
        health_preferences=["low-sugar"],
        preference_weights={"nutrition": 0, "time": 0, "variety": 0, "pantry": 0, "health": 1},
    )
    problem = FinalPlanningProblem.model_validate(data)
    assert score_plan(problem, choose("a")).total_loss == 0
    assert score_plan(problem, choose("b")).total_loss == 1
    assert all(band.metric != "sugar_g" for band in problem.nutrition_bands)


def test_all_zero_weights_have_defined_result_and_stable_assignment_order():
    data = packet().model_dump()
    data["preference_weights"] = {name: 0 for name in data["preference_weights"]}
    problem = FinalPlanningProblem.model_validate(data)
    score = score_plan(problem, choose("a"))
    assert score.total_loss == 0
    assert score == score_plan(problem, list(reversed(choose("a"))))
