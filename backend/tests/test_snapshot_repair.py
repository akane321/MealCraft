from datetime import UTC, datetime
from pathlib import Path

from app.planning.snapshot_repair import ProductSnapshot, RetrievalUnavailable, solve_with_repair
from app.schemas.planning_v2 import FinalPlanningProblem
from app.schemas.retrieval import RetrievalTrace


def packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


class FixtureProvider:
    def __init__(self, products, *, version="repair-1", unavailable=False):
        self.products, self.version, self.unavailable = products, version, unavailable
        self.calls = []

    def retrieve(self, demands):
        self.calls.append(demands)
        if self.unavailable:
            raise RetrievalUnavailable()
        trace = RetrievalTrace(
            requested_source="fairprice",
            provider_used="fixture",
            mode="fixture",
            status="success",
            query="normalized test demand",
            fetched_at=datetime(2026, 9, 7, tzinfo=UTC),
            parser_version="test-v1",
            candidate_count=len(self.products),
        )
        return ProductSnapshot(self.version, tuple(self.products), trace)


def test_missing_products_are_repaired_without_mutating_user_constraints():
    full = packet()
    problem = full.model_copy(update={"products": []})
    original = problem.model_dump_json()
    provider = FixtureProvider(full.products)
    result = solve_with_repair(problem, provider)
    assert result.solution.status == "feasible"
    assert result.stop_reason == "validated"
    assert len(provider.calls) == 1
    assert len(result.attempts) == 2
    assert result.attempts[1].retrieval.mode == "fixture"
    assert result.solution.validation.product_snapshot_version == "repair-1"
    assert problem.model_dump_json() == original
    assert all(d.quantity > 0 for d in provider.calls[0])


def test_provider_failure_has_no_invention_or_retry_storm():
    problem = packet().model_copy(update={"products": []})
    provider = FixtureProvider([], unavailable=True)
    result = solve_with_repair(problem, provider)
    assert result.stop_reason == "provider_unavailable"
    assert result.solution.status == "needs_data"
    assert len(provider.calls) == 1


def test_zero_repair_budget_does_not_call_provider():
    problem = packet().model_copy(update={"products": []})
    provider = FixtureProvider([])
    result = solve_with_repair(problem, provider, max_rounds=0)
    assert result.stop_reason == "repair_limit"
    assert provider.calls == []


def test_repeated_snapshot_cannot_restart_repair():
    problem = packet().model_copy(update={"products": []})
    provider = FixtureProvider([], version=problem.product_snapshot_version)
    result = solve_with_repair(problem, provider)
    assert result.stop_reason == "snapshot_not_new"
    assert len(provider.calls) == 1


def test_new_prices_repair_budget_without_raising_the_user_budget():
    full = packet()
    problem = full.model_copy(update={"purchase_budget_sgd": 1})
    provider = FixtureProvider([p.model_copy(update={"price_sgd": 0.01}) for p in full.products])
    result = solve_with_repair(problem, provider)
    assert result.solution.status == "feasible"
    assert result.solution.validation.purchase_total_sgd <= 1
    assert problem.purchase_budget_sgd == 1
    assert result.attempts[0].products != result.attempts[1].products


def test_fixture_cannot_be_presented_as_live_evidence():
    import pytest

    class MislabelledProvider(FixtureProvider):
        def retrieve(self, demands):
            snapshot = super().retrieve(demands)
            return ProductSnapshot(
                snapshot.version, snapshot.products, snapshot.trace.model_copy(update={"mode": "live"})
            )

    full = packet()
    with pytest.raises(ValueError, match="Fixture evidence"):
        solve_with_repair(full.model_copy(update={"products": []}), MislabelledProvider(full.products))
