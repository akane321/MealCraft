from dataclasses import replace

import pytest

from app.planning.fixed_menu_refresh import refresh_fixed_menu
from app.planning.mixed_shopping import build_mixed_shopping
from tests.test_mixed_repair import snapshot
from tests.test_mixed_shopping import assignments, packet


@pytest.mark.parametrize("price,status,delta", [(1.99, "feasible", -1), (2.01, "candidate_rejected", 1)])
def test_price_change_preserves_menu_and_reports_exact_cent_budget(price, status, delta):
    problem, selected = packet(), assignments()
    before = build_mixed_shopping(problem, selected)
    original = problem.model_dump_json()
    products = [problem.products[0].model_copy(update={"price_sgd": price}), problem.products[1]]
    result = refresh_fixed_menu(problem, selected, before, snapshot(products))
    assert result["status"] == status
    assert result["recipe_changes"] == []
    assert result["assignments"] == [a.model_dump() for a in selected]
    assert result["purchase_total_delta_cents"] == delta
    assert result["shopping_delta"][0]["purchase_cost_delta_cents"] == delta
    assert result["issues"] == (["purchase_budget"] if delta > 0 else [])
    assert problem.model_dump_json() == original
    assert before.purchase_total_sgd == 3.5


def test_new_snapshot_replaces_old_options_and_does_not_keep_missing_cheap_product():
    problem, selected = packet(), assignments()
    result = refresh_fixed_menu(
        problem, selected, build_mixed_shopping(problem, selected), snapshot(problem.products[:1])
    )
    assert result["status"] == "candidate_rejected"
    assert result["shopping"]["purchase_total_sgd"] == 4
    assert result["shopping"]["lines"][0]["purchase"]["allocations"] == ({"product_id": "150", "packages": 2},)


def test_unavailable_product_can_change_packages_without_changing_recipes():
    problem, selected = packet().model_copy(update={"purchase_budget_sgd": 5}), assignments()
    products = [problem.products[0].model_copy(update={"available": False}), problem.products[1]]
    result = refresh_fixed_menu(problem, selected, build_mixed_shopping(problem, selected), snapshot(products))
    assert result["status"] == "feasible"
    assert result["purchase_total_delta_cents"] == 100
    assert result["shopping"]["lines"][0]["purchase"]["allocations"] == ({"product_id": "100", "packages": 3},)
    assert result["recipe_changes"] == []


def test_product_identity_change_is_reported_even_at_identical_cost():
    problem, selected = packet(), assignments()
    products = [p.model_copy(update={"product_id": f"new-{p.product_id}"}) for p in problem.products]
    result = refresh_fixed_menu(problem, selected, build_mixed_shopping(problem, selected), snapshot(products))
    assert result["status"] == "feasible"
    assert result["purchase_total_delta_cents"] == 0
    assert len(result["shopping_delta"]) == 1


@pytest.mark.parametrize("case", ["missing", "degraded", "same_version", "bad_count", "subcent", "limit"])
def test_incomplete_refresh_does_not_expose_partial_basket(case):
    problem, selected = packet(), assignments()
    new = snapshot(problem.products)
    limit = 100000
    if case == "missing":
        new = snapshot([])
    elif case == "degraded":
        new = snapshot(problem.products, status="degraded")
    elif case == "same_version":
        new = snapshot(problem.products, version=problem.product_snapshot_version)
    elif case == "bad_count":
        new = snapshot(problem.products, candidate_count=99)
    elif case == "subcent":
        new = snapshot([p.model_copy(update={"price_sgd": 1.001}) for p in problem.products])
    else:
        limit = 1
    result = refresh_fixed_menu(problem, selected, build_mixed_shopping(problem, selected), new, max_combinations=limit)
    assert result["status"] in {"needs_data", "limit_exceeded"}
    assert "shopping" not in result
    assert "purchase_total_delta_cents" not in result


def test_forged_before_and_after_are_rechecked(monkeypatch):
    from app.planning import fixed_menu_refresh

    problem, selected = packet(), assignments()
    before = build_mixed_shopping(problem, selected)
    forged = replace(before, purchase_total_sgd=0)
    assert refresh_fixed_menu(problem, selected, forged, snapshot(problem.products))["issues"] == [
        "previous:purchase_total"
    ]
    monkeypatch.setattr(fixed_menu_refresh, "build_mixed_shopping", lambda *args, **kwargs: forged)
    assert refresh_fixed_menu(problem, selected, before, snapshot(problem.products))["issues"] == ["purchase_total"]


def test_composed_meal_preserves_all_roles_shares_and_source_objects():
    from tests.test_planning_meal_composition import meal
    from tests.test_planning_meal_composition import problem as composed_problem

    problem = composed_problem()
    selected = meal(("main", "chicken"), ("vegetable", "greens"), ("soup", "broth"))
    original = problem.model_dump_json()
    before = build_mixed_shopping(problem, selected)
    new = snapshot([p.model_copy(update={"price_sgd": 2}) for p in problem.products])
    result = refresh_fixed_menu(problem, selected, before, new)
    assert result["status"] == "feasible"
    assert result["assignments"] == [a.model_dump() for a in selected]
    assert {line["ingredient_id"]: line["required_quantity"] for line in result["shopping"]["lines"]} == {
        "chicken-base": 240,
        "greens-base": 160,
        "broth-base": 160,
    }
    assert problem.model_dump_json() == original
    saved_cost = result["shopping"]["purchase_total_sgd"]
    new.products[0].price_sgd = 999
    new.trace.query = "changed"
    assert result["shopping"]["purchase_total_sgd"] == saved_cost
    assert result["retrieval"]["query"] != "changed"
