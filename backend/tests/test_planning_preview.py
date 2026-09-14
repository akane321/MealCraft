import json
from dataclasses import replace

import pytest

from app.core.paths import repository_root
from app.planning import preview
from app.planning.beam_planner import BeamLimits
from app.schemas.planning_v2 import FinalPlanningProblem


def packet():
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def test_preview_is_repeatable_and_preserves_input():
    problem = packet()
    before = problem.model_dump_json()
    result = preview.preview_plan(problem)
    assert result.validated
    assert result.solution.shopping.purchase_total_sgd == 3.5
    assert result.to_json() == preview.preview_plan(problem).to_json()
    assert problem.model_dump_json() == before
    output = json.loads(result.to_json())
    assert output["validated"]
    assert output["limits"] == {"width": 32, "max_expansions": 10000}


def test_digest_tracks_input_and_limits_are_separate():
    problem = packet()
    first = preview.preview_plan(problem)
    assert preview.preview_plan(problem, limits=BeamLimits(1, 100)).input_sha256 == first.input_sha256
    problem.products[0].price_sgd += 1
    assert preview.preview_plan(problem).input_sha256 != first.input_sha256


def test_unknown_pantry_is_not_deducted():
    problem = packet()
    problem.pantry[0].quantity = None
    problem.purchase_budget_sgd = 100
    result = preview.preview_plan(problem)
    assert result.validated
    assert result.solution.shopping.lines[0].pantry_deduction == 0
    assert any(i.code == "unknown_pantry_quantity" for i in result.input_issues)


@pytest.mark.parametrize("condition", ["missing_products", "package_limit", "expansion_limit", "allergen", "budget"])
def test_unvalidated_outcomes_never_become_infeasibility_proofs(condition):
    problem = packet()
    kwargs = {}
    if condition == "missing_products":
        problem.products = []
    elif condition == "package_limit":
        kwargs["max_package_combinations"] = 1
    elif condition == "expansion_limit":
        kwargs["limits"] = BeamLimits(32, 1)
    elif condition == "allergen":
        problem.allergens = problem.recipes[0].allergens
    else:
        problem.purchase_budget_sgd = 1
    result = preview.preview_plan(problem, **kwargs)
    assert not result.validated
    assert result.validation_issues is None
    assert result.solution.status != "infeasible"
    if condition == "missing_products":
        assert any(i.startswith("package_needs_data:") for i in result.solution.candidate_issues)
    if condition == "package_limit":
        assert any(i.startswith("package_limit_exceeded:") for i in result.solution.candidate_issues)
    if condition == "expansion_limit":
        assert result.solution.expansion_limit_reached


@pytest.mark.parametrize("field", ["budget", "price", "version", "nonfinite"])
def test_invalid_packet_is_rejected_before_search(monkeypatch, field):
    problem = packet()
    if field == "budget":
        problem.purchase_budget_sgd = 3.499
    elif field == "price":
        problem.products[0].price_sgd = 1.001
    elif field == "version":
        problem.catalog_version = " "
    else:
        problem.recipes[0].nutrients_per_serving.protein_g = float("inf")
    monkeypatch.setattr(preview, "solve_mixed_beam", lambda *a, **kw: pytest.fail("search must not run"))
    with pytest.raises(ValueError):
        preview.preview_plan(problem)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5])
def test_package_limit_must_be_a_positive_integer(limit):
    with pytest.raises(ValueError):
        preview.preview_plan(packet(), max_package_combinations=limit)


def test_independent_validation_rejects_forged_solver_total(monkeypatch):
    problem = packet()
    valid = preview.preview_plan(problem).solution
    forged = replace(valid, shopping=replace(valid.shopping, purchase_total_sgd=0))
    monkeypatch.setattr(preview, "solve_mixed_beam", lambda *a, **kw: forged)
    result = preview.preview_plan(problem)
    assert result.solution.status == "candidate_rejected"
    assert not result.validated
    assert "purchase_total" in result.validation_issues
