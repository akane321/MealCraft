from dataclasses import replace

import pytest

from app.core.paths import repository_root
from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.planning.mixed_shopping import build_mixed_shopping, validate_mixed_shopping
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def packet():
    path = repository_root() / "data/fixtures/planning-v2/final-scope-multislot.json"
    data = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8")).model_dump()
    recipe, slot = data["recipes"][0], data["slots"][0]
    data.update(
        recipes=[
            dict(recipe, recipe_id="a", servings=2, ingredients=[dict(ingredient_id="rice", quantity=100, unit="g")])
        ],
        slots=[dict(slot, slot_id=str(i), servings=3, locked_recipe_id=None) for i in range(2)],
        pantry=[dict(ingredient_id="rice", quantity=50, unit="g")],
        products=[
            dict(ingredient_id="rice", product_id=str(q), package_quantity=q, package_unit="g", price_sgd=p)
            for q, p in [(150, 2), (100, 1.5)]
        ],
        nutrition_bands=[],
        purchase_budget_sgd=3.5,
    )
    return FinalPlanningProblem.model_validate(data)


def assignments():
    return [PlanningAssignment(slot_id=str(i), recipe_id="a") for i in range(2)]


def test_serving_scaling_pantry_once_and_mixed_budget():
    problem = packet()
    before = problem.model_dump_json()
    result = build_mixed_shopping(problem, assignments())
    assert result.status == "feasible"
    line = result.lines[0]
    assert (line.required_quantity, line.pantry_deduction, line.remaining_quantity) == (300, 50, 250)
    assert result.purchase_total_sgd == 3.5
    assert len(line.purchase.allocations) == 2
    assert validate_mixed_shopping(problem, assignments(), result) == ()
    assert problem.model_dump_json() == before


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("required_quantity", 1, "required_quantity"),
        ("pantry_deduction", 100, "pantry_deduction"),
        ("remaining_quantity", 1, "remaining_quantity"),
        ("remaining_quantity", float("nan"), "remaining_quantity"),
    ],
)
def test_validator_rebuilds_demand_after_mutation(field, value, code):
    problem = packet()
    result = build_mixed_shopping(problem, assignments())
    forged = replace(result, lines=(replace(result.lines[0], **{field: value}),))
    assert code in validate_mixed_shopping(problem, assignments(), forged)


def test_forged_total_missing_and_duplicate_lines():
    problem = packet()
    result = build_mixed_shopping(problem, assignments())
    assert "purchase_total" in validate_mixed_shopping(problem, assignments(), replace(result, purchase_total_sgd=0))
    for lines in ((), result.lines * 2):
        assert "shopping_line_identity" in validate_mixed_shopping(problem, assignments(), replace(result, lines=lines))


def test_unknown_pantry_never_deducted_and_duplicate_pantry_is_unresolved():
    problem = packet()
    unknown = problem.model_copy(
        update={"pantry": [problem.pantry[0].model_copy(update={"quantity": None})], "purchase_budget_sgd": None}
    )
    assert build_mixed_shopping(unknown, assignments()).lines[0].pantry_deduction == 0
    duplicate = problem.model_copy(update={"pantry": problem.pantry * 2})
    assert build_mixed_shopping(duplicate, assignments()).status == "needs_data"


def test_budget_and_assignment_failures_remain_hard():
    problem = packet()
    assert (
        build_mixed_shopping(problem.model_copy(update={"purchase_budget_sgd": 3}), assignments()).status
        == "candidate_rejected"
    )
    assert build_mixed_shopping(problem, assignments()[:1]).status == "candidate_rejected"
    assert build_mixed_shopping(problem, assignments() * 2).status == "candidate_rejected"
    problem = problem.model_copy(update={"allergens": problem.recipes[0].allergens})
    assert build_mixed_shopping(problem, assignments()).status == "candidate_rejected"


def test_hybrid_cp_sat_matches_complete_mixed_enumeration():
    pytest.importorskip("ortools")
    problem = packet()
    expected = exhaustive_mixed_plan(problem)
    actual = exhaustive_mixed_plan(problem, use_cp_sat=True)
    assert expected.status == actual.status == "optimal_for_frozen_packet"
    assert actual.best_choices == expected.best_choices
    assert actual.best_loss == expected.best_loss
    assert actual.shopping.purchase_total_sgd == expected.shopping.purchase_total_sgd == 3.5


def test_limits_and_missing_products_cannot_prove_no_solution():
    problem = packet().model_copy(update={"products": []})
    result = exhaustive_mixed_plan(problem)
    assert result.status == "incomplete_evidence"
    assert result.unresolved_combinations == 1
    problem = packet()
    problem = problem.model_copy(
        update={"recipes": problem.recipes + [problem.recipes[0].model_copy(update={"recipe_id": "b"})]}
    )
    assert exhaustive_mixed_plan(problem, max_assignments=1).status == "limit_exceeded"
    assert exhaustive_mixed_plan(problem, max_package_combinations=1).status == "incomplete_evidence"


def test_fractional_serving_demand_is_not_silently_rounded():
    problem = packet()
    recipe = problem.recipes[0].model_copy(update={"servings": 7})
    problem = problem.model_copy(update={"recipes": [recipe]})
    result = build_mixed_shopping(problem, assignments())
    assert result.status == "needs_data"
    assert result.issues == ("quantity_not_representable",)


def test_mixed_beam_recovers_budget_rejected_by_single_product_policy():
    problem = packet()
    assert BeamPlanner().solve(problem).status == "candidate_rejected"
    result = solve_mixed_beam(problem)
    assert result.status == "feasible"
    assert result.shopping.purchase_total_sgd == 3.5
    assert result.choices == exhaustive_mixed_plan(problem).best_choices
    assert result == solve_mixed_beam(problem.model_copy(update={"products": list(reversed(problem.products))}))


def test_mixed_beam_cannot_return_partial_plan_after_cap():
    result = solve_mixed_beam(packet(), limits=BeamLimits(max_expansions=1))
    assert result.status == "candidate_rejected"
    assert result.expansion_limit_reached
    assert result.choices == ()


def test_mixed_beam_preserves_unknown_evidence():
    result = solve_mixed_beam(packet().model_copy(update={"products": []}))
    assert result.status == "needs_data"
    assert result.unresolved_candidates == 1
