from types import SimpleNamespace

import pytest

from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation import algorithm_ladder_baseline as runner
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.baseline_resources import BaselineResources
from app.schemas.planning_v2 import PlanningMealRole, PlanningNutrients
from tests.test_diversity_greedy import setup_problem


def synthetic(monkeypatch):
    problem, _ = setup_problem(20)
    problem.problem_id = "synthetic"
    for slot in problem.slots:
        slot.composition = [PlanningMealRole(role_id="main", courses=["main"], required=True)]
    monkeypatch.setattr(runner, "build_problem", lambda *_: problem)
    episode = {
        "episode_id": "synthetic",
        "scenario": {
            "user_request": "Plan dinners for two.",
            "household_profile": {
                "household_size": 2,
                "allergens": [],
                "excluded_ingredients": [],
                "dietary_preferences": [],
            },
        },
        "recipe_steps": {r.recipe_id: ["Cook the listed rice and serve."] for r in problem.recipes},
    }
    return problem, episode


def resources(problem):
    facts = IngredientEvaluationFacts(
        (),
        PlanningNutrients(
            calories_kcal=100,
            protein_g=2,
            carbohydrate_g=20,
            fat_g=1,
            sodium_mg=1,
            sugar_g=0,
        ),
    )
    names = {"rice": "Rice"}
    return BaselineResources(
        names=names,
        aliases={},
        matcher=IngredientMatcher(names, mode="spelling"),
        ingredient_facts={"rice": facts},
        frozen_products=problem.products,
        not_purchased=frozenset(),
    )


@pytest.mark.parametrize("system_id", runner.implemented_system_ids())
def test_each_offline_arm_uses_current_schema_and_zero_model_cost(monkeypatch, system_id):
    problem, episode = synthetic(monkeypatch)
    generated = runner.generate(episode, system_id=system_id)
    assert generated.usage.total_tokens == 0 and generated.cost_usd == 0
    assert generated.response.status == "plan"
    for meal in generated.response.plan.meals:
        for dish in meal.dishes:
            assert dish.servings > 0 and dish.steps == ["Cook the listed rice and serve."]
            assert dish.ingredients and dish.role_id
    result = runner.run_episode(episode, system_id=system_id, resources=resources(problem))
    assert result["scored"]["recomputation"]["nutrition_complete"]
    assert result["development_only"]
    assert result["deterministic"] == (system_id != "algorithm-rung-6-cp-sat")
    assert result["scored"]["validation"].get("skipped")  # No gold problem: not an automatic pass.


def test_missing_steps_and_non_gram_quantities_fail_instead_of_being_invented(monkeypatch):
    problem, episode = synthetic(monkeypatch)
    episode["recipe_steps"] = {}
    with pytest.raises(ValueError, match="Missing original recipe steps"):
        runner.generate(episode, system_id=runner.implemented_system_ids()[0])
    episode["recipe_steps"] = {r.recipe_id: ["Cook rice."] for r in problem.recipes}
    for recipe in problem.recipes:
        recipe.ingredients[0].unit = "cups"
    with pytest.raises((ValueError, RuntimeError)):
        runner.generate(episode, system_id=runner.implemented_system_ids()[0])


@pytest.mark.parametrize("status", ["unknown", "feasible", "score_mismatch", "infeasible"])
def test_solver_status_is_not_converted_to_proven_infeasibility(monkeypatch, status):
    problem, _ = synthetic(monkeypatch)
    monkeypatch.setattr(runner.NativeSharedScoreCpSat, "solve_exact", lambda *_: {"status": status})
    with pytest.raises(RuntimeError, match=status):
        runner._cp_sat(problem, runner._objective(problem))


def test_multiple_dishes_are_grouped_by_slot(monkeypatch):
    problem, episode = synthetic(monkeypatch)
    from app.schemas.planning_v2 import PlanningAssignment

    solution = SimpleNamespace(
        assignments=[
            PlanningAssignment(slot_id=problem.slots[0].slot_id, recipe_id="a", role_id="main"),
            PlanningAssignment(slot_id=problem.slots[0].slot_id, recipe_id="b", role_id="side"),
        ]
    )
    response = runner._response_from_solution(problem, solution, system_id="dev", recipe_steps=episode["recipe_steps"])
    assert len(response.plan.meals) == 1
    assert len(response.plan.meals[0].dishes) == 2
    assert [d.role_id for d in response.plan.meals[0].dishes] == ["main", "side"]


def test_protected_paths_are_rejected_before_the_loader(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_load_episodes", lambda _: pytest.fail("Must not open protected input"))
    with pytest.raises(ValueError, match="Protected"):
        runner.load_development_episodes(tmp_path / "heldout" / "never-open.json")
