from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.evaluation.heldout_report import CaseOutcome, ExpectedManifest, render
from app.evaluation.heldout_statistics import MetricSpec, compare, mcnemar_exact, wilson_interval


def outcome(case_ref, system_id, run=1, status="success", **changes):
    values = {
        "case_ref": case_ref,
        "system_id": system_id,
        "run": run,
        "category": "planning",
        "language": "en",
        "source": "authored",
        "status": status,
    }
    values.update(changes)
    return CaseOutcome(**values)


def paired(product, baseline):
    records = []
    for index, (product_status, baseline_status) in enumerate(zip(product, baseline, strict=True), 1):
        records.extend(
            [
                outcome(f"c{index}", "product", status=product_status),
                outcome(f"c{index}", "baseline", status=baseline_status),
            ]
        )
    return records


def test_paired_binary_effect_bootstrap_wilson_and_mcnemar():
    report = compare(
        paired(
            ["success", "success", "success", "failure", "missing"],
            ["failure", "failure", "success", "success", "missing"],
        ),
        product_system_id="product",
        bootstrap_samples=500,
    )
    metric = report["comparisons"]["baseline"]["metrics"]["success"]
    assert metric["paired_n"] == 5
    assert metric["product_rate"] == 0.6
    assert metric["baseline_rate"] == 0.4
    assert metric["paired_rate_difference"] == 0.2
    assert len(metric["paired_bootstrap_95_ci"]) == 2
    assert metric["product_wilson_95_ci"] == wilson_interval(3, 5)
    assert metric["mcnemar"] == mcnemar_exact(2, 1)


def test_repeated_runs_are_aggregated_by_episode_before_pairing_and_variation_is_reported():
    records = [
        outcome("c1", "product", 1, "success"),
        outcome("c1", "product", 2, "failure"),
        outcome("c2", "product", 1, "success"),
        outcome("c2", "product", 2, "success"),
        outcome("c1", "baseline", 1, "failure"),
        outcome("c1", "baseline", 2, "failure"),
        outcome("c2", "baseline", 1, "success"),
        outcome("c2", "baseline", 2, "failure"),
    ]
    metric = compare(records, product_system_id="product", bootstrap_samples=100)["comparisons"]["baseline"]["metrics"][
        "success"
    ]
    assert metric["paired_n"] == 2
    assert metric["product_rate"] == 1.0  # c1's two-run mean is 0.5: declared majority rule passes it.
    assert metric["baseline_rate"] == 0.5
    assert metric["product_run_summary"] == {
        "per_run": [1.0, 0.5],
        "mean": 0.75,
        "standard_deviation": 0.25,
    }


def test_declared_binary_and_continuous_metrics_are_paired_without_rescoring():
    records = []
    for case_ref, product_cost, baseline_cost, product_safe, baseline_safe in (
        ("c1", 10.0, 14.0, True, False),
        ("c2", 12.0, 13.0, True, True),
        ("c3", 15.0, 12.0, False, True),
    ):
        records.extend(
            [
                outcome(
                    case_ref,
                    "product",
                    binary_metrics={"hard_valid": product_safe},
                    continuous_metrics={"cost": product_cost},
                ),
                outcome(
                    case_ref,
                    "baseline",
                    binary_metrics={"hard_valid": baseline_safe},
                    continuous_metrics={"cost": baseline_cost},
                ),
            ]
        )
    result = compare(
        records,
        product_system_id="product",
        metrics=[
            MetricSpec(name="hard_valid", kind="binary"),
            MetricSpec(name="cost", kind="continuous", higher_is_better=False),
        ],
        bootstrap_samples=300,
    )["comparisons"]["baseline"]["metrics"]
    assert result["hard_valid"]["paired_rate_difference"] == pytest.approx(0.0)
    assert result["cost"]["mean_difference"] == pytest.approx(2 / 3)
    assert result["cost"]["median_difference"] == pytest.approx(1.0)
    assert result["cost"]["higher_is_better"] is False


def test_missing_timeout_and_error_are_failures_for_declared_binary_metrics():
    records = [
        outcome("c1", "product", status="missing"),
        outcome("c1", "baseline", binary_metrics={"hard_valid": True}),
        outcome("c2", "product", status="timeout"),
        outcome("c2", "baseline", binary_metrics={"violation": False}),
    ]
    higher = compare(
        records[:2],
        product_system_id="product",
        metrics=[MetricSpec(name="hard_valid", kind="binary")],
        bootstrap_samples=10,
    )["comparisons"]["baseline"]["metrics"]["hard_valid"]
    lower = compare(
        records[2:],
        product_system_id="product",
        metrics=[MetricSpec(name="violation", kind="binary", higher_is_better=False)],
        bootstrap_samples=10,
    )["comparisons"]["baseline"]["metrics"]["violation"]
    assert higher["product_rate"] == 0.0
    assert lower["product_rate"] == 0.0


def test_grouped_reporting_is_default_off_and_opt_in_covers_all_supported_dimensions():
    records = paired(["success", "failure"], ["failure", "failure"])
    records[0] = records[0].model_copy(update={"category": "intent", "language": "zh", "source": "forum"})
    records[1] = records[1].model_copy(update={"category": "intent", "language": "zh", "source": "forum"})
    assert "groups" not in compare(records, product_system_id="product", bootstrap_samples=10)
    groups = compare(records, product_system_id="product", bootstrap_samples=10, include_groups=True)["groups"]
    assert set(groups) == {"by_category", "by_language", "by_source", "cells"}
    assert groups["by_language"]["zh"]["baseline"]["metrics"]["success"]["paired_n"] == 1


def test_power_note_uses_the_issue_365_planning_approximation():
    records = paired(["success"] * 60, ["failure"] * 60)
    note = compare(records, product_system_id="product", bootstrap_samples=10)["comparisons"]["baseline"]["power_note"]
    assert note["paired_episodes"] == 60
    assert note["approximate_minimum_detectable_absolute_difference"] == 0.1


def test_seeded_output_is_byte_stable_and_never_discloses_case_refs():
    records = paired(["success", "failure", "success"], ["failure", "success", "failure"])
    first = render(compare(records, product_system_id="product", seed=91, bootstrap_samples=250))
    second = render(compare(reversed(records), product_system_id="product", seed=91, bootstrap_samples=250))
    assert first == second
    assert "case_ref" not in first and "c1" not in first
    assert json.loads(first)["seed"] == 91


def test_invalid_requests_and_statistical_counts_fail_closed():
    records = paired(["success"], ["failure"])
    with pytest.raises(ValueError, match="product"):
        compare(records, product_system_id="absent")
    with pytest.raises(ValueError, match="baseline"):
        compare([outcome("c1", "product")], product_system_id="product")
    with pytest.raises(ValueError, match="positive"):
        compare(records, product_system_id="product", bootstrap_samples=0)
    with pytest.raises(ValueError):
        wilson_interval(2, 1)
    with pytest.raises(ValueError):
        mcnemar_exact(-1, 0)
    with pytest.raises(ValidationError):
        outcome("c1", "product", continuous_metrics={"cost": float("nan")})
    with pytest.raises(ValidationError):
        outcome("c1", "product", binary_metrics={"bad metric name": True})


def test_expected_manifest_can_guard_completeness_before_comparison():
    records = paired(["success"], ["failure"])
    expected = ExpectedManifest(
        systems=["product", "baseline"],
        runs=1,
        cells={"planning|en|authored": 2},
        voided=0,
    )
    with pytest.raises(ValueError, match="cells"):
        compare(records, product_system_id="product", expected=expected, bootstrap_samples=10)
