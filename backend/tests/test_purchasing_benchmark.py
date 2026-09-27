from dataclasses import replace

import pytest

from app.planning import purchasing_benchmark as benchmark


def test_both_solvers_agree_on_synthetic_cost_and_surplus():
    pytest.importorskip("ortools")
    result = benchmark.benchmark_case(*benchmark.synthetic_cases()[0], repeats=2)
    assert result["comparison"] == "equal_cost_and_surplus"
    for record in result["solvers"].values():
        assert record["stable_results"]
        assert len(record["wall_seconds_samples"]) == 2


def test_cap_is_unresolved_not_infeasible_or_equal():
    result = benchmark.benchmark_case(*benchmark.synthetic_cases()[0], repeats=1, max_combinations=1)
    assert result["comparison"] == "unresolved"
    assert result["solvers"]["enumeration"]["runs"][0][0]["status"] == "limit_exceeded"


def test_forged_solver_cost_fails_independent_validation(monkeypatch):
    original = benchmark.optimize_packages

    def forged(*args, **kwargs):
        return replace(original(*args, **kwargs), purchase_cost_sgd=0)

    monkeypatch.setattr(benchmark, "optimize_packages", forged)
    result = benchmark.benchmark_case(*benchmark.synthetic_cases()[0], repeats=1)
    assert result["comparison"] == "unresolved"
    assert result["solvers"]["enumeration"]["runs"][0][0]["status"] == "invalid_result"


def test_missing_optional_solver_does_not_claim_agreement(monkeypatch):
    def unavailable(*args, **kwargs):
        raise ImportError("test")

    monkeypatch.setattr(benchmark, "solve_packages_cp_sat", unavailable)
    result = benchmark.benchmark_case(*benchmark.synthetic_cases()[0], repeats=1)
    assert result["comparison"] == "unresolved"
    assert result["solvers"]["cp_sat"]["runs"][0][0]["status"] == "unavailable"


@pytest.mark.parametrize("repeats", [0, 21, True])
def test_invalid_repeat_count(repeats):
    with pytest.raises(ValueError, match="repeats"):
        benchmark.benchmark_case(*benchmark.synthetic_cases()[0], repeats=repeats)
