from pathlib import Path

import pytest

from app.planning.beam_planner import BeamPlanner
from app.planning.constraint_compiler import compile_constraints, compile_search_domains
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.input_audit import NonfinitePlanningInput
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.planning.whole_plan_scoring import score_plan
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def score(problem):
    return score_plan(problem, [PlanningAssignment(slot_id=s.slot_id, recipe_id="a") for s in problem.slots])


@pytest.mark.parametrize(
    "entry",
    [
        BeamPlanner().solve,
        exhaustive_assignments,
        solve_mixed_beam,
        exhaustive_mixed_plan,
        score,
        FinalScopeReferencePlanner().solve,
        compile_constraints,
        compile_search_domains,
    ],
)
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_direct_calls_raise_typed_error_before_search_or_scoring(entry, value):
    problem = packet()
    problem.recipes[0].nutrients_per_serving.protein_g = value
    with pytest.raises(NonfinitePlanningInput) as caught:
        entry(problem)
    assert caught.value.issues[0].path == "recipes[0].nutrients_per_serving.protein_g"
    assert caught.value.issues[0].code == "nonfinite_number"


def test_library_boundary_checks_entire_packet_and_preserves_unknown_stock():
    problem = packet()
    problem.pantry[0].quantity = None
    problem.purchase_budget_sgd = 100
    assert solve_mixed_beam(problem).status == "feasible"
    problem.products[0].price_sgd = float("inf")
    with pytest.raises(NonfinitePlanningInput) as caught:
        solve_mixed_beam(problem)
    assert caught.value.issues[0].path == "products[0].price_sgd"
