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


def composed_dataset():
    from app.planning.validation_gate_experiments import GateDataset

    return GateDataset.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/final-gate-composed-developer-v1.json").read_bytes()
    )


def test_composed_roles_and_portion_shares_are_preserved():
    source = composed_dataset()
    before = source.model_dump_json()
    result = run_gate_experiments(source)
    row = result["runs"][0]
    assert result["protocol"] == "planning-final-gate-dev-v2"
    assert row["configuration"]["engine"] == "meal-beam"
    assert row["configuration"]["engine_limits"]["candidates_per_role"] == 8
    for condition in row["conditions"].values():
        assert condition["audit"]["status"] == "passed"
        assert {a["role_id"] for a in condition["assignments"]} == {"main", "vegetable", "soup"}
        assert {s["ingredient_id"]: s["required_quantity"] for s in condition["shopping"]} == {
            "chicken-base": 240,
            "greens-base": 160,
            "broth-base": 160,
        }
    assert source.model_dump_json() == before


def test_composed_budget_and_missing_data_are_not_hidden():
    rows = {r["case_id"]: r for r in run_gate_experiments(composed_dataset())["runs"]}
    tight = rows["composed-tight-budget"]["conditions"]["final_gate_on"]
    assert tight["audit"]["status"] == "passed"
    assert tight["audit"]["purchase_total_sgd"] <= 5
    assert "soup" not in {a["role_id"] for a in tight["assignments"]}
    missing = rows["composed-missing-products"]["conditions"]
    assert missing["final_gate_off"]["audit"]["status"] == "indeterminate"
    assert missing["final_gate_on"]["candidate_index"] is None
    optional = rows["composed-optional-missing"]["conditions"]["final_gate_on"]
    assert optional["audit"]["status"] == "passed"
    assert len(optional["assignments"]) == 1


def test_composed_exhaustion_keeps_no_partial_meal():
    report = compare_validation_gate(composed_dataset().cases[0].problem, max_expansions=1)
    assert report["search"]["exhausted"]
    assert report["candidate_count"] == 0


def test_gate_schema_supports_both_old_and_composed_inputs():
    from app.planning.validation_gate_experiments import GateDataset

    assert len(GateDataset.model_validate(dataset().model_dump()).cases) == len(dataset().cases)
    # The original five-condition runner keeps its one-dish contract.
    with pytest.raises(ValueError, match="one dish"):
        ExperimentDataset.model_validate(composed_dataset().model_dump())


def test_mixed_single_and_composed_slots_keep_role_identity():
    from datetime import date

    problem = composed_dataset().cases[0].problem.model_copy(deep=True)
    extra = problem.slots[0].model_copy(
        update={"slot_id": "next-day", "planned_date": date(2026, 10, 2), "composition": None}
    )
    problem.slots.append(extra)
    report = compare_validation_gate(problem)
    chosen = report["conditions"]["final_gate_on"]
    assert chosen["audit"]["status"] == "passed"
    assert len([a for a in chosen["assignments"] if a["slot_id"] == "d1"]) == 3
    assert [a["role_id"] for a in chosen["assignments"] if a["slot_id"] == "next-day"] == [None]
