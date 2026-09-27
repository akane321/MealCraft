import pytest

from app.planning.purchasing_comparison import compare_purchasing
from tests.test_mixed_shopping import assignments, packet


def test_fixed_menu_comparison_keeps_pantry_once_and_budget():
    problem = packet()
    before = problem.model_dump_json()
    result = compare_purchasing(problem, assignments())
    assert result["status"] == "compared"
    assert result["whole_horizon"]["purchase_total_sgd"] == 3.5
    assert result["per_slot"]["purchase_total_sgd"] == 3.5
    assert result["per_slot"]["lines"][0]["pantry_deduction"] == 50
    assert result["baseline_solver_calls"] == 2
    assert result["whole_horizon_solver_calls"] == 1
    assert problem.model_dump_json() == before


def test_consolidation_saves_money_but_can_increase_surplus():
    problem = packet()
    problem = problem.model_copy(
        update={
            "pantry": [],
            "products": [
                problem.products[0].model_copy(update={"package_quantity": 500, "price_sgd": 3}),
                problem.products[1].model_copy(update={"package_quantity": 150, "price_sgd": 2}),
            ],
            "purchase_budget_sgd": 3,
        }
    )
    result = compare_purchasing(problem, assignments())
    assert result["status"] == "compared"
    assert result["saving_sgd"] == 1
    assert result["whole_horizon"]["status"] == "feasible"
    assert result["per_slot"]["status"] == "over_budget"
    assert result["whole_horizon"]["lines"][0]["purchase"]["surplus_quantity"] == 200
    assert result["per_slot"]["lines"][0]["purchase"]["surplus_quantity"] == 0


@pytest.mark.parametrize("budget,status", [(3.49, "over_budget"), (3.5, "feasible")])
def test_cent_boundary(budget, status):
    result = compare_purchasing(packet().model_copy(update={"purchase_budget_sgd": budget}), assignments())
    assert result["whole_horizon"]["status"] == status


def test_unresolved_inputs_do_not_claim_savings():
    for problem, selected, limit in [
        (packet(), assignments()[:1], 100000),
        (packet(), assignments(), 1),
        (packet().model_copy(update={"purchase_budget_sgd": 3.499}), assignments(), 100000),
        (packet().model_copy(update={"products": []}), assignments(), 100000),
    ]:
        result = compare_purchasing(problem, selected, max_combinations=limit)
        assert result["status"] == "unresolved"
        assert "saving_sgd" not in result


def test_unknown_pantry_and_reproducibility():
    problem = packet()
    problem = problem.model_copy(update={"pantry": [problem.pantry[0].model_copy(update={"quantity": None})]})
    first = compare_purchasing(problem, assignments())
    second = compare_purchasing(problem, assignments())
    assert first["per_slot"]["lines"][0]["pantry_deduction"] == 0
    first.pop("elapsed_seconds")
    second.pop("elapsed_seconds")
    assert first == second


def test_rechecks_forged_whole_horizon_total(monkeypatch):
    from dataclasses import replace

    from app.planning import purchasing_comparison
    from app.planning.mixed_shopping import build_mixed_shopping

    forged = replace(build_mixed_shopping(packet(), assignments()), purchase_total_sgd=0)
    monkeypatch.setattr(purchasing_comparison, "build_mixed_shopping", lambda *a, **k: forged)
    result = compare_purchasing(packet(), assignments())
    assert result["status"] == "unresolved"
    assert "purchase_total" in result["issues"]


def test_nonfinite_input_returns_no_comparison():
    result = compare_purchasing(packet().model_copy(update={"purchase_budget_sgd": float("nan")}), assignments())
    assert result == {"status": "unresolved", "issues": ["nonfinite_input"]}


def test_multi_dish_portions_share_a_slot_checkout():
    from tests.test_planning_meal_composition import meal, problem

    selected = meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth"))
    result = compare_purchasing(problem(), selected)
    assert result["status"] == "compared"
    assert result["saving_sgd"] == 0
    for basket in ("per_slot", "whole_horizon"):
        assert {line["ingredient_id"]: line["required_quantity"] for line in result[basket]["lines"]} == {
            "chicken-base": 240,
            "greens-base": 160,
            "broth-base": 160,
        }


def test_pantry_with_incompatible_unit_is_not_deducted():
    problem = packet()
    problem = problem.model_copy(update={"pantry": [problem.pantry[0].model_copy(update={"unit": "ml"})]})
    result = compare_purchasing(problem, assignments())
    assert result["status"] == "compared"
    assert result["per_slot"]["lines"][0]["pantry_deduction"] == 0
