import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.planning.mixed_repair import solve_mixed_with_repair
from app.planning.snapshot_repair import ProductSnapshot, RetrievalUnavailable
from app.planning.workbench import main
from app.schemas.planning_v2 import FinalPlanningProblem
from app.schemas.retrieval import RetrievalTrace


def packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def snapshot(products, version="mixed-refresh-v1", **trace_changes):
    trace = RetrievalTrace(
        requested_source="fairprice",
        provider_used="fixture",
        mode="fixture",
        status="success",
        query="synthetic rice demand",
        fetched_at=datetime(2026, 9, 9, tzinfo=UTC),
        parser_version="fixture-v1",
        candidate_count=len(products),
    )
    return ProductSnapshot(version, tuple(products), trace.model_copy(update=trace_changes))


class Provider:
    def __init__(self, *snapshots):
        self.snapshots = iter(snapshots)
        self.calls = []

    def retrieve(self, demands):
        self.calls.append(demands)
        try:
            return next(self.snapshots)
        except StopIteration as exc:
            raise RetrievalUnavailable() from exc


def test_missing_products_refresh_to_mixed_purchase_and_preserve_request():
    full = packet()
    problem = full.model_copy(update={"products": []})
    before = problem.model_dump_json()
    provider = Provider(snapshot(full.products))
    result = solve_mixed_with_repair(problem, provider)
    assert result.stop_reason == "validated"
    assert result.solution.status == "feasible"
    assert result.solution.shopping.purchase_total_sgd == 3.5
    assert len(result.solution.shopping.lines[0].purchase.allocations) == 2
    assert [(d.ingredient_id, d.quantity, d.unit) for d in provider.calls[0]] == [("rice", 250, "g")]
    assert result.solution.product_snapshot_version == "mixed-refresh-v1"
    assert result.attempts[1].retrieval.mode == "fixture"
    assert problem.model_dump_json() == before


def test_price_refresh_preserves_budget_and_old_snapshot_evidence():
    full = packet()
    problem = full.model_copy(update={"products": [p.model_copy(update={"price_sgd": 10}) for p in full.products]})
    result = solve_mixed_with_repair(problem, Provider(snapshot(full.products)))
    assert result.solution.shopping.purchase_total_sgd == 3.5
    assert problem.purchase_budget_sgd == 3.5
    assert result.attempts[0].products[0].price_sgd == 10
    assert result.attempts[1].products == tuple(full.products)


def test_valid_frozen_plan_does_not_refresh():
    provider = Provider()
    assert solve_mixed_with_repair(packet(), provider).stop_reason == "validated"
    assert provider.calls == []


def test_partial_catalog_replaces_old_products_then_next_snapshot_repairs():
    full = packet()
    problem = full.model_copy(update={"products": [full.products[1].model_copy(update={"price_sgd": 10})]})
    provider = Provider(snapshot([full.products[0]], "one-product"), snapshot(full.products, "both-products"))
    result = solve_mixed_with_repair(problem, provider)
    assert result.stop_reason == "validated"
    assert len(provider.calls) == 2
    assert result.attempts[1].products == (full.products[0],)
    assert result.solution.shopping.purchase_total_sgd == 3.5


def test_repeated_snapshot_and_provider_failure_stop():
    full = packet()
    problem = full.model_copy(update={"products": []})
    assert solve_mixed_with_repair(problem, Provider()).stop_reason == "provider_unavailable"
    provider = Provider(snapshot(full.products, problem.product_snapshot_version))
    assert solve_mixed_with_repair(problem, provider).stop_reason == "snapshot_not_new"
    assert len(provider.calls) == 1


def test_refresh_round_cap_and_full_snapshot_replacement():
    full = packet()
    problem = full.model_copy(update={"products": []})
    provider = Provider(snapshot([], "empty-1"), snapshot([], "empty-2"), snapshot(full.products))
    result = solve_mixed_with_repair(problem, provider, max_rounds=2)
    assert result.stop_reason == "repair_limit"
    assert result.solution.status != "feasible"
    assert len(provider.calls) == 2
    assert len(result.attempts) == 3
    assert all(a.products == () for a in result.attempts)


@pytest.mark.parametrize("reason", ["allergen", "quantity", "package_limit"])
def test_non_product_failure_does_not_trigger_retrieval(reason):
    problem = packet()
    kwargs = {}
    if reason == "allergen":
        problem = problem.model_copy(update={"allergens": problem.recipes[0].allergens})
    elif reason == "quantity":
        recipe = problem.recipes[0].model_copy(deep=True)
        recipe.ingredients[0].quantity = None
        problem = problem.model_copy(update={"recipes": [recipe]})
    else:
        kwargs["max_package_combinations"] = 1
    provider = Provider()
    assert solve_mixed_with_repair(problem, provider, **kwargs).stop_reason == "no_repairable_demand"
    assert provider.calls == []


def test_degraded_packet_is_recorded_without_using_its_prices():
    problem = packet().model_copy(update={"products": []})
    result = solve_mixed_with_repair(problem, Provider(snapshot(packet().products, status="degraded")))
    assert result.stop_reason == "provider_degraded"
    assert result.solution.status == "needs_data"
    assert result.attempts[-1].products == tuple(packet().products)
    assert result.attempts[-1].retrieval.status == "degraded"


@pytest.mark.parametrize("changes", [{"mode": "live"}, {"candidate_count": 999}, {"requested_source": "youtube"}])
def test_invalid_evidence_is_rejected(changes):
    problem = packet().model_copy(update={"products": []})
    with pytest.raises(ValueError):
        solve_mixed_with_repair(problem, Provider(snapshot(packet().products, **changes)))


def test_workbench_runs_mixed_repair_and_serializes_evidence(tmp_path, monkeypatch, capsys):
    full = packet()
    request, options = tmp_path / "problem.json", tmp_path / "snapshots.json"
    request.write_text(full.model_copy(update={"products": []}).model_dump_json(), encoding="utf-8")
    sample = snapshot(full.products)
    options.write_text(
        json.dumps(
            [
                {
                    "version": sample.version,
                    "products": [p.model_dump() for p in sample.products],
                    "trace": sample.trace.model_dump(mode="json"),
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["workbench", "repair", str(request), "--options", str(options), "--mixed-packages"]
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["solution"]["shopping"]["purchase_total_sgd"] == 3.5
    assert result["attempts"][1]["retrieval"]["mode"] == "fixture"
