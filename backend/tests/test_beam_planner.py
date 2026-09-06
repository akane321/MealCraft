from pathlib import Path

import pytest

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.schemas.planning_v2 import FinalPlanningProblem

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"


def packet():
    return FinalPlanningProblem.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_is_feasible_and_input_order_does_not_change_decisions():
    problem = packet()
    first = BeamPlanner().solve(problem)
    reversed_problem = problem.model_copy(
        update={"slots": list(reversed(problem.slots)), "recipes": list(reversed(problem.recipes))}
    )
    assert first.status == "feasible"
    assert first.model_dump_json() == BeamPlanner().solve(reversed_problem).model_dump_json()


def test_search_can_find_budget_valid_combination_missed_by_greedy():
    data = packet().model_dump()
    recipe = data["recipes"][0]
    a = dict(
        recipe,
        recipe_id="a",
        servings=1,
        total_time_minutes=5,
        ingredients=[{"ingredient_id": "rice", "quantity": 1000, "unit": "g"}],
    )
    b = dict(
        recipe,
        recipe_id="b",
        servings=1,
        total_time_minutes=10,
        ingredients=[{"ingredient_id": "rice", "quantity": 10, "unit": "g"}],
    )
    slot = data["slots"][0]
    data.update(
        recipes=[a, b],
        slots=[dict(slot, slot_id=str(i), locked_recipe_id=None, servings=1, max_time_minutes=20) for i in range(2)],
        nutrition_bands=[],
        pantry=[],
        purchase_budget_sgd=1,
        products=[
            {"ingredient_id": "rice", "product_id": "bag", "package_quantity": 100, "package_unit": "g", "price_sgd": 1}
        ],
    )
    problem = FinalPlanningProblem.model_validate(data)
    assert FinalScopeReferencePlanner().solve(problem).status == "candidate_rejected"
    result = BeamPlanner(BeamLimits(width=4)).solve(problem)
    assert result.status == "feasible"
    assert [assignment.recipe_id for assignment in result.assignments] == ["b", "b"]
    assert result.validation.purchase_total_sgd == 1


def test_expansion_limit_returns_no_partial_plan_and_no_infeasibility_claim():
    result = BeamPlanner(BeamLimits(max_expansions=1)).solve(packet())
    assert result.status == "candidate_rejected"
    assert result.assignments == []
    assert any("expansion_limit_reached=True" in warning for warning in result.trace.warnings)


def test_locked_allergen_conflict_does_not_get_relaxed():
    problem = packet()
    locked = next(slot for slot in problem.slots if slot.locked_recipe_id)
    recipe = next(recipe for recipe in problem.recipes if recipe.recipe_id == locked.locked_recipe_id)
    problem = problem.model_copy(update={"allergens": recipe.allergens})
    assert BeamPlanner().solve(problem).status == "candidate_rejected"


@pytest.mark.parametrize("limits", [{"width": 0}, {"max_expansions": 0}])
def test_invalid_resource_limits_are_rejected(limits):
    with pytest.raises(ValueError):
        BeamLimits(**limits)
