import pytest

from app.evaluation.algorithm_ladder_baseline import (
    ARMS,
    generate,
    implemented_system_ids,
    run_episode,
)
from tests.test_strong_rule_baseline import EPISODE, catalog, resources

EXPECTED_ARMS = (
    "algorithm-rung-0-naive-greedy",
    "algorithm-rung-1-diversity-greedy",
    "algorithm-rung-2-grasp",
    "algorithm-rung-3-local-search",
    "algorithm-rung-3-simulated-annealing",
    "algorithm-current-shared-objective-beam",
    "algorithm-rung-6-cp-sat",
)


def test_only_implemented_algorithm_rungs_have_stable_identifiers():
    assert implemented_system_ids() == EXPECTED_ARMS
    assert [ARMS[system_id].rung for system_id in EXPECTED_ARMS] == [
        "0",
        "1",
        "2",
        "3-local",
        "3-annealing",
        "current-beam",
        "6",
    ]


@pytest.mark.parametrize("system_id", EXPECTED_ARMS)
def test_each_algorithm_arm_is_deterministic_and_has_zero_model_cost(monkeypatch, system_id):
    monkeypatch.setattr("app.evaluation.multidish_runner.load_release_catalog", catalog)

    first = generate(EPISODE, system_id=system_id)
    second = generate(EPISODE, system_id=system_id)

    assert first.response == second.response
    assert first.response is not None
    assert first.response.system_id == system_id
    assert first.response.status == "plan"
    assert first.usage.input_tokens == first.usage.output_tokens == first.usage.total_tokens == 0
    assert first.usage.cost_usd == 0.0


@pytest.mark.parametrize("system_id", EXPECTED_ARMS)
def test_each_arm_uses_shared_mapping_coverage_and_recomputation(monkeypatch, system_id):
    monkeypatch.setattr("app.evaluation.multidish_runner.load_release_catalog", catalog)

    result = run_episode(EPISODE, system_id=system_id, resources=resources())

    assert result.valid_output is True
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.pricing_status == "complete"
    assert result.recomputation.purchase_total_sgd is not None


def test_unknown_algorithm_identifier_is_rejected():
    with pytest.raises(ValueError, match="unknown algorithm baseline arm"):
        generate(EPISODE, system_id="algorithm-rung-4-lns")
