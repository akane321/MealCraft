import json

import pytest

from app.core.paths import repository_root
from app.planning.developer_experiments import ExperimentDataset
from app.planning.validation_gate_experiments import compare_validation_gate, run_gate_experiments


def dataset():
    return ExperimentDataset.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/final-gate-developer-v1.json").read_bytes()
    )


def case(name):
    return next(c.problem for c in dataset().cases if c.case_id == name)


def test_gate_blocks_a_better_scoring_over_budget_candidate():
    problem = case("better-score-over-budget")
    before = problem.model_dump_json()
    report = compare_validation_gate(problem)
    off, on = report["conditions"].values()
    assert off["audit"]["status"] == "failed"
    assert off["assignments"][0]["recipe_id"] == "a-large"
    assert on["audit"]["status"] == "passed"
    assert on["assignments"][0]["recipe_id"] == "b-small"
    assert off["audit"]["purchase_total_sgd"] == 2
    assert on["audit"]["purchase_total_sgd"] == 1
    assert problem.model_dump_json() == before
    assert report["persistable"] is False


def test_one_cent_and_unknown_data_never_pass_gate():
    problem = case("one-cent-over")
    report = compare_validation_gate(problem)
    assert report["conditions"]["final_gate_on"]["candidate_index"] is None
    assert report["candidate_checks"][0]["failures"]
    missing = compare_validation_gate(problem.model_copy(update={"products": []}))
    assert missing["conditions"]["final_gate_off"]["audit"]["status"] == "indeterminate"
    assert missing["conditions"]["final_gate_on"]["candidate_index"] is None


def test_allergen_filters_remain_active_without_final_gate():
    report = compare_validation_gate(case("allergen-saturated"))
    assert report["candidate_count"] == 0
    for condition in report["conditions"].values():
        assert condition["selection_status"] == "no_candidate_selected"
        assert condition["audit"] is None


def test_both_conditions_keep_a_valid_pantry_candidate():
    report = compare_validation_gate(case("pantry-heavy"))
    for condition in report["conditions"].values():
        assert condition["audit"]["status"] == "passed"
        assert condition["audit"]["purchase_total_sgd"] == 0


def test_bounded_search_does_not_emit_a_partial_draft():
    report = compare_validation_gate(case("diversity"), max_expansions=1)
    assert report["search"]["exhausted"] is True
    assert report["candidate_count"] == 0
    assert all(c["assignments"] == [] for c in report["conditions"].values())


def test_repeats_preserve_decisions_and_report_is_serializable():
    first = run_gate_experiments(dataset())
    second = run_gate_experiments(dataset())
    for a, b in zip(first["runs"], second["runs"], strict=True):
        assert a["input_sha256"] == b["input_sha256"]
        for key in a["conditions"]:
            a["conditions"][key].pop("audit_seconds")
            b["conditions"][key].pop("audit_seconds")
            assert a["conditions"][key] == b["conditions"][key]
    json.dumps(first, allow_nan=False)


def test_repair_input_is_rejected_rather_than_silently_ignored():
    source = dataset()
    source.cases[0].provider_unavailable = True
    with pytest.raises(ValueError, match="fixed snapshots"):
        run_gate_experiments(source)


@pytest.mark.parametrize("kwargs", [{"width": True}, {"width": 0}, {"max_expansions": 1.5}])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        compare_validation_gate(case("pantry-heavy"), **kwargs)
