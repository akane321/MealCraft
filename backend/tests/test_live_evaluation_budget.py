import pytest

from scripts.evaluate_sprint2_live_dev import EvaluationBudget


def test_live_evaluation_budget_stops_starting_calls_at_five_dollars() -> None:
    budget = EvaluationBudget()
    assert budget.can_start_request
    budget.record(4.99)
    assert budget.can_start_request
    budget.record(0.01)
    assert budget.spent_usd == pytest.approx(5.0)
    assert not budget.can_start_request


def test_live_evaluation_budget_rejects_unknown_costs() -> None:
    budget = EvaluationBudget()
    with pytest.raises(ValueError, match="unknown model pricing"):
        budget.record(None)
