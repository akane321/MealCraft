import json

import pytest

from app.core.paths import repository_root
from app.planning.developer_experiments import ExperimentDataset, run_experiments

FIXTURE = repository_root() / "data/fixtures/planning-v2/ablation-developer-v1.json"


def dataset():
    return ExperimentDataset.model_validate_json(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def report():
    return run_experiments(dataset(), repeats=2)


def row(report, case, preset="beam"):
    return next(r for r in report["runs"] if r["case_id"] == case and r["preset"] == preset)


def test_stress_outcomes_and_failed_checks_are_recorded(report):
    over = row(report, "one-cent-over")
    assert over["audit"]["status"] == "failed"
    assert over["audit"]["purchase_total_sgd"] == 1
    assert over["failures"]
    assert over["status"] != "infeasible"
    assert row(report, "allergen-saturated")["solution"]["assignments"] == []
    pantry = row(report, "pantry-heavy")
    assert pantry["audit"]["status"] == "passed"
    assert pantry["solution"]["shopping"][0]["pantry_deduction"] == 100
    assert pantry["audit"]["purchase_total_sgd"] == 0
    missing = row(report, "provider-unavailable")
    assert missing["stop_reason"] == "provider_unavailable"
    assert missing["audit"]["status"] == "indeterminate"


def test_repair_comparison_uses_same_input_and_audits_new_prices(report):
    on = row(report, "price-change")
    off = row(report, "price-change", "repair_off")
    assert on["input_sha256"] == off["input_sha256"]
    assert on["audit"]["status"] == "passed"
    assert on["audit"]["product_snapshot_version"] == "price-2"
    assert on["audit"]["purchase_total_sgd"] == 0.99
    assert off["audit"]["status"] == "failed"
    assert len(on["attempts"]) == 2
    assert len(off["attempts"]) == 1


def test_weights_change_only_soft_terms_and_hard_caps_remain(report):
    base = row(report, "diversity")["effective_weights"]
    for preset, key in [("variety_off", "diversity_penalty"), ("overlap_off", "overlap_reward_weight")]:
        changed = row(report, "diversity", preset)
        assert changed["effective_weights"] == dict(base, **{key: 0})
        assert changed["audit"]["status"] == "passed"
    assert row(report, "one-cent-over", "overlap_off")["status"] == "not_applicable"


def test_repeats_reproduce_decisions_and_do_not_mutate_input(report):
    source = dataset()
    before = source.model_dump_json()
    run_experiments(source)
    assert source.model_dump_json() == before
    for r in report["runs"]:
        if r.get("repeat") == 1:
            first = row(report, r["case_id"], r["preset"])
            assert r["solution_sha256"] == first["solution_sha256"]
            assert r["audit"] == first["audit"]
    assert sum(report["category_counts"].values()) == len(source.cases)
    assert report["evidence"] == "developer_diagnostic"
    json.dumps(report, allow_nan=False)


def test_search_limit_is_not_reported_as_infeasible():
    result = run_experiments(dataset(), max_expansions=1)
    assert row(result, "diversity")["status"] == "candidate_rejected"
    assert row(result, "diversity")["solution"]["assignments"] == []


@pytest.mark.parametrize(
    "kwargs", [{"repeats": True}, {"repeats": 0}, {"width": 0}, {"repair_rounds": -1}, {"max_expansions": 1.5}]
)
def test_invalid_run_settings(kwargs):
    with pytest.raises(ValueError):
        run_experiments(dataset(), **kwargs)


def test_heldout_label_and_duplicate_cases_are_rejected():
    data = dataset().model_dump(mode="json")
    data["source"] = "heldout"
    with pytest.raises(ValueError):
        ExperimentDataset.model_validate(data)
    data["source"] = "developer"
    data["cases"].append(data["cases"][0])
    with pytest.raises(ValueError, match="unique"):
        ExperimentDataset.model_validate(data)
