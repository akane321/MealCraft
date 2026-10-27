from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.evaluation.heldout_report import CaseOutcome, aggregate, render


def outcome(case_ref="c1", system_id="s1", run=1, category="planning", language="en", source="authored", **extra):
    values = {
        "case_ref": case_ref,
        "system_id": system_id,
        "run": run,
        "category": category,
        "language": language,
        "source": source,
        "status": "success",
        "voided": False,
    }
    values.update(extra)
    return CaseOutcome(**values)


def cell(report, system="s1", category="planning", language="en", source="authored"):
    return report["systems"][system]["cells"][f"{category}|{language}|{source}"]


def test_counts_and_rate_treat_unknown_as_not_success():
    records = [
        outcome("c1", status="success"),
        outcome("c2", status="failure"),
        outcome("c3", status="timeout"),
        outcome("c4", status="error"),
        outcome("c5", status="missing"),
    ]
    got = cell(aggregate(records))
    assert (got["declared_n"], got["voided_n"], got["remaining_n"]) == (5, 0, 5)
    assert (got["success_n"], got["failure_n"], got["timeout_n"], got["error_n"], got["missing_n"]) == (1, 1, 1, 1, 1)
    # timeouts, errors and missing outputs stay in the denominator: unknown is never a success.
    assert got["success_rate"] == pytest.approx(0.2)


def test_voided_cases_are_reported_and_leave_the_denominator():
    records = [outcome("c1"), outcome("c2", status="failure", voided=True), outcome("c3", status="failure")]
    got = cell(aggregate(records))
    assert (got["declared_n"], got["voided_n"], got["remaining_n"]) == (3, 1, 2)
    assert got["success_rate"] == pytest.approx(0.5)
    # a voided case's own result does not count as a failure either
    assert got["failure_n"] == 1


def test_all_voided_cases_have_no_success_rate():
    records = [outcome("c1", run=run, voided=True) for run in (1, 2)]
    got = cell(aggregate(records))
    assert (got["declared_n"], got["voided_n"], got["remaining_n"]) == (1, 1, 0)
    assert got["success_n"] == 0
    assert got["success_rate"] is None
    assert got["per_run_success_rate"] == [None, None]


def test_no_outcomes_are_rejected_instead_of_reporting_success():
    with pytest.raises(ValueError, match="no outcomes"):
        aggregate([])


def test_void_must_be_identical_for_every_system():
    records = [
        outcome("c1", system_id="s1", voided=True),
        outcome("c1", system_id="s2", voided=False),
    ]
    with pytest.raises(ValueError, match="void"):
        aggregate(records)


def test_every_system_and_run_must_cover_the_same_cases():
    records = [outcome("c1", system_id="s1"), outcome("c2", system_id="s1"), outcome("c1", system_id="s2")]
    with pytest.raises(ValueError, match="same cases"):
        aggregate(records)


def test_duplicate_record_and_changed_labels_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        aggregate([outcome("c1"), outcome("c1")])
    with pytest.raises(ValueError, match="labels"):
        aggregate([outcome("c1", system_id="s1"), outcome("c1", system_id="s2", language="zh")])


def test_marginals_report_forum_and_authored_separately():
    records = [
        outcome("c1", source="forum", status="success"),
        outcome("c2", source="forum", status="failure"),
        outcome("c3", source="authored", status="success"),
    ]
    report = aggregate(records)
    by_source = report["systems"]["s1"]["by_source"]
    assert by_source["forum"]["success_rate"] == pytest.approx(0.5)
    assert by_source["authored"]["success_rate"] == pytest.approx(1.0)
    assert report["systems"]["s1"]["overall"]["remaining_n"] == 3


def test_repeated_runs_average_the_per_run_rates():
    records = [
        outcome("c1", run=1, status="success"),
        outcome("c2", run=1, status="success"),
        outcome("c1", run=2, status="success"),
        outcome("c2", run=2, status="failure"),
    ]
    got = cell(aggregate(records))
    assert got["runs"] == 2
    assert got["success_rate"] == pytest.approx(0.75)
    assert got["per_run_success_rate"] == [1.0, 0.5]


def test_output_never_contains_case_references():
    records = [outcome("secret-ref-1"), outcome("secret-ref-2", status="failure")]
    text = render(aggregate(records))
    assert "secret-ref" not in text
    assert "case_ref" not in text


def test_unknown_labels_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        outcome(category="cooking")
    with pytest.raises(ValidationError):
        outcome(status="passed")
    with pytest.raises(ValidationError):
        outcome(question_text="a real question")


def test_render_is_byte_stable_and_lf_terminated():
    records = [outcome("c1", system_id="s2"), outcome("c1", system_id="s1")]
    first, second = render(aggregate(records)), render(aggregate(list(reversed(records))))
    assert first == second
    assert first.endswith("\n") and "\r" not in first
    assert list(json.loads(first)["systems"]) == ["s1", "s2"]


# --- the expected manifest: aggregate counts supplied by the sealed side -------------------------------------------


def manifest(**changes):
    from app.evaluation.heldout_report import ExpectedManifest

    values = {"systems": ["s1", "s2"], "runs": 2, "cells": {"planning|en|authored": 2}, "voided": 0}
    values.update(changes)
    return ExpectedManifest(**values)


def full_records(systems=("s1", "s2"), runs=(1, 2), cases=("c1", "c2")):
    return [outcome(c, system_id=s, run=r) for s in systems for r in runs for c in cases]


def test_a_complete_set_passes_the_manifest():
    report = aggregate(full_records(), manifest())
    assert sorted(report["systems"]) == ["s1", "s2"]


def test_a_case_missing_from_every_run_and_system_is_caught():
    # Without the manifest this is invisible: every system and run omits the same case.
    records = full_records(cases=("c1",))
    aggregate(records)
    with pytest.raises(ValueError, match="cells"):
        aggregate(records, manifest())


def test_a_missing_system_or_run_is_caught():
    with pytest.raises(ValueError, match="systems"):
        aggregate(full_records(systems=("s1",)), manifest())
    with pytest.raises(ValueError, match="runs"):
        aggregate(full_records(runs=(1,)), manifest())
    with pytest.raises(ValueError, match="systems"):
        aggregate(full_records(systems=("s1", "s2", "s3")), manifest())


def test_an_unexpected_cell_or_wrong_void_count_is_caught():
    extra = full_records() + [
        outcome("c9", system_id=s, run=r, category="intent") for s in ("s1", "s2") for r in (1, 2)
    ]
    with pytest.raises(ValueError, match="cells"):
        aggregate(extra, manifest())
    voided = [
        outcome(c, system_id=s, run=r, voided=c == "c2") for s in ("s1", "s2") for r in (1, 2) for c in ("c1", "c2")
    ]
    with pytest.raises(ValueError, match="voided"):
        aggregate(voided, manifest(voided=0))
    assert aggregate(voided, manifest(voided=1))


def test_the_manifest_cannot_carry_case_identifiers_or_bad_labels():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        manifest(cells={"cooking|en|authored": 1})
    with pytest.raises(ValidationError):
        manifest(cells={"planning|en|authored": 0})
    with pytest.raises(ValidationError):
        manifest(case_refs=["c1"])
    with pytest.raises(ValidationError):
        manifest(runs=0)


# --- small cells: withheld when too few cases remain (ADR-0100 item 5, proposed) ---------------------------------


def cells_of(spec):
    """spec: {(category, language, source): [statuses...]} -> one outcome per entry, all voided=False."""
    records = []
    for (category, language, source), statuses in spec.items():
        for i, status in enumerate(statuses):
            records.append(
                outcome(
                    f"{category}-{language}-{source}-{i}",
                    category=category,
                    language=language,
                    source=source,
                    status=status,
                )
            )
    return records


BIG = ["success"] * 4 + ["failure"] * 2


def test_without_a_minimum_nothing_is_withheld():
    report = aggregate(cells_of({("planning", "en", "authored"): ["success"], ("intent", "zh", "forum"): BIG}))
    assert "planning|en|authored" in report["systems"]["s1"]["cells"]


def test_a_small_cell_withholds_the_whole_category_breakdown_not_only_itself():
    records = cells_of(
        {
            ("planning", "en", "authored"): ["success", "failure"],  # 2 remaining: below 5
            ("planning", "zh", "authored"): BIG,
            ("intent", "en", "authored"): BIG,
        }
    )
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    # Showing the other planning cells beside the planning total would let a reader subtract the small cell out.
    assert not any(key.startswith("planning|") for key in system["cells"])
    assert "intent|en|authored" in system["cells"]
    assert system["withheld_categories"] == {"planning": "a cell has fewer than 5 remaining cases"}
    assert system["by_category"]["planning"]["remaining_n"] == 8


def test_voided_cases_do_not_count_towards_the_minimum():
    records = [outcome(f"c{i}", voided=i < 3) for i in range(6)]  # 6 declared, 3 voided, 3 remaining
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    assert system["cells"] == {}


def test_a_small_total_is_withheld_too():
    records = cells_of({("planning", "en", "authored"): ["success"] * 3, ("intent", "zh", "forum"): BIG})
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    assert system["by_category"]["planning"] == {"withheld": "fewer than 5 remaining cases"}
    assert system["by_category"]["intent"]["remaining_n"] == 6
    assert "success_rate" in system["overall"]


def test_withheld_output_carries_no_counts_of_the_small_cell():
    records = cells_of({("planning", "en", "authored"): ["success", "success"], ("intent", "zh", "forum"): BIG})
    text = render(aggregate(records, min_cell_n=5))
    assert "planning|en|authored" not in text


def test_the_minimum_must_be_a_positive_whole_number():
    for bad in (0, -1):
        with pytest.raises(ValueError, match="minimum"):
            aggregate(cells_of({("planning", "en", "authored"): BIG}), min_cell_n=bad)
