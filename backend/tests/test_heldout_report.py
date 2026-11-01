from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.evaluation.heldout_report import STATUSES, CaseOutcome, aggregate, render


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


# --- small cells: withheld when too few cases remain (ADR-0100 item 5) --------------------------------------------


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
SMALL_TOTAL = {"withheld": "fewer than 5 remaining cases"}
CELLS_WITHHELD = {"withheld": "a cell has fewer than 5 remaining cases"}
COUNT_FIELDS = ("declared_n", "voided_n", "remaining_n", *(f"{s}_n" for s in STATUSES))


def withheld_names(totals):
    return [name for name, summary in totals.items() if "withheld" in summary]


def consistent_values(system, keys, target, field):
    """Every value `target` takes over whole-number cell tables, one entry per key, that agree with all the figures
    `system` publishes for `field`. A single value means the published figures give the cell away."""
    position = {"by_category": 0, "by_language": 1, "by_source": 2}
    checks = [(lambda key: True, system["overall"][field])]
    for part, index in position.items():
        for name, summary in system[part].items():
            if field in summary:
                checks.append((lambda key, index=index, name=name: key.split("|")[index] == name, summary[field]))
    for cell_key, summary in system["cells"].items():
        if isinstance(summary, dict) and field in summary:
            checks.append((lambda key, cell_key=cell_key: key == cell_key, summary[field]))

    def tables(total, count):
        if count == 1:
            yield (total,)
            return
        for first in range(total + 1):
            for rest in tables(total - first, count - 1):
                yield (first, *rest)

    values = set()
    for table in tables(system["overall"][field], len(keys)):
        cells = dict(zip(keys, table, strict=True))
        if all(sum(v for key, v in cells.items() if member(key)) == total for member, total in checks):
            values.add(cells[target])
    return values


def reviews_table():
    """The review's invented counts: planning|en|authored 2, planning|zh|authored 30, intent|en|authored 20 and
    intent|zh|authored 20 remaining cases, with every status and some voided cases in every cell."""
    sizes = {
        ("planning", "en"): (2, 3),
        ("planning", "zh"): (30, 1),
        ("intent", "en"): (20, 2),
        ("intent", "zh"): (20, 4),
    }
    records = []
    for (category, language), (remaining, voided) in sizes.items():
        for i in range(remaining + voided):
            records.append(
                outcome(
                    f"{category}-{language}-{i}",
                    category=category,
                    language=language,
                    status=STATUSES[i % len(STATUSES)],
                    voided=i >= remaining,
                )
            )
    return records


def test_without_a_minimum_nothing_is_withheld():
    report = aggregate(cells_of({("planning", "en", "authored"): ["success"], ("intent", "zh", "forum"): BIG}))
    assert "planning|en|authored" in report["systems"]["s1"]["cells"]


def test_a_small_cell_removes_every_cross_cell_and_keeps_only_the_totals():
    records = cells_of(
        {
            ("planning", "en", "authored"): ["success", "failure"],  # 2 remaining: below 5
            ("planning", "zh", "authored"): BIG,
            ("intent", "en", "authored"): BIG,
        }
    )
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    # The other cells beside the totals would let a reader subtract the small cell out, so none is shown.
    assert system["cells"] == CELLS_WITHHELD
    assert system["overall"]["remaining_n"] == 14
    assert system["by_category"]["planning"]["remaining_n"] == 8
    assert system["by_language"]["en"]["remaining_n"] == 8
    assert system["by_source"]["authored"]["remaining_n"] == 14


def test_the_reviews_table_cannot_be_subtracted_back_to_the_small_cell():
    records = reviews_table()
    keys = ["planning|en|authored", "planning|zh|authored", "intent|en|authored", "intent|zh|authored"]
    plain = aggregate(records)["systems"]["s1"]
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    assert system["cells"] == CELLS_WITHHELD
    assert system["by_language"]["en"]["remaining_n"] == 22  # still published, as the review found
    for field in COUNT_FIELDS:
        true_value = plain["cells"]["planning|en|authored"][field]
        # control: with the cells shown the published figures do give the small cell away
        assert consistent_values(plain, keys, "planning|en|authored", field) == {true_value}
        # with the rule, many different small cells fit the published figures, the real one among them
        possible = consistent_values(system, keys, "planning|en|authored", field)
        assert true_value in possible and len(possible) > 1, field


def test_a_status_found_only_in_one_language_does_not_locate_the_small_cell():
    # A baseline that fails every English case: with status counts in the language and category totals, the 2 errors
    # shown for planning would all sit in planning|en, giving its size and its errors back.
    sizes = {("planning", "en"): 2, ("planning", "zh"): 30, ("intent", "en"): 20, ("intent", "zh"): 20}
    records = cells_of(
        {
            (category, language, "authored"): ["error" if language == "en" else "success"] * count
            for (category, language), count in sizes.items()
        }
    )
    keys = ["planning|en|authored", "planning|zh|authored", "intent|en|authored", "intent|zh|authored"]
    plain = aggregate(records)["systems"]["s1"]
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    for part in ("by_category", "by_language", "by_source"):
        assert all(set(summary) == {"remaining_n"} for summary in system[part].values()), part
    for field in ("error_n", "success_n"):
        assert consistent_values(plain, keys, "planning|en|authored", field) == {
            plain["cells"]["planning|en|authored"][field]
        }
        assert len(consistent_values(system, keys, "planning|en|authored", field)) > 1, field


def test_without_a_small_cell_the_report_is_unchanged():
    records = cells_of({("planning", "en", "authored"): BIG, ("intent", "zh", "forum"): BIG})
    assert aggregate(records, min_cell_n=5) == aggregate(records)


def test_one_withheld_total_takes_the_smallest_other_value_of_its_dimension_with_it():
    records = cells_of(
        {
            ("planning", "en", "authored"): ["success", "failure"],  # 2 remaining: below 5
            ("intent", "en", "authored"): ["success"] * 20,
            ("multi_turn", "zh", "authored"): ["success"] * 10,
            ("adversarial", "zh", "authored"): ["success"] * 15,
        }
    )
    system = aggregate(records, min_cell_n=5)["systems"]["s1"]
    by_category = system["by_category"]
    # The overall total minus intent and adversarial would be planning plus multi_turn, not planning alone.
    assert withheld_names(by_category) == ["multi_turn", "planning"]
    assert by_category["planning"] == SMALL_TOTAL
    assert by_category["multi_turn"] != SMALL_TOTAL
    assert by_category["intent"]["remaining_n"] == 20
    assert by_category["adversarial"]["remaining_n"] == 15
    assert system["overall"]["remaining_n"] == 47
    assert withheld_names(system["by_language"]) == []
    assert withheld_names(system["by_source"]) == []


def test_a_tie_for_the_smallest_other_value_goes_to_the_first_name():
    records = cells_of(
        {
            ("planning", "en", "authored"): ["success", "failure"],
            ("intent", "en", "authored"): ["success"] * 10,
            ("multi_turn", "zh", "authored"): ["success"] * 10,
            ("adversarial", "zh", "authored"): ["success"] * 15,
        }
    )
    assert withheld_names(aggregate(records, min_cell_n=5)["systems"]["s1"]["by_category"]) == ["intent", "planning"]


def test_two_withheld_totals_in_one_dimension_need_no_neighbour():
    records = cells_of(
        {
            ("planning", "en", "authored"): ["success", "failure"],
            ("intent", "zh", "authored"): ["success"] * 3,
            ("multi_turn", "en", "authored"): ["success"] * 10,
            ("adversarial", "zh", "authored"): ["success"] * 15,
        }
    )
    by_category = aggregate(records, min_cell_n=5)["systems"]["s1"]["by_category"]
    assert withheld_names(by_category) == ["intent", "planning"]
    assert by_category["multi_turn"]["remaining_n"] == 10


def test_a_small_overall_total_shows_only_withheld():
    records = cells_of({("planning", "en", "authored"): ["success", "success", "failure"]})
    assert aggregate(records, min_cell_n=5)["systems"]["s1"] == {"overall": SMALL_TOTAL}


def test_voided_cases_do_not_count_towards_the_minimum():
    records = [outcome(f"c{i}", voided=i < 3) for i in range(6)]  # 6 declared, 3 voided, 3 remaining
    assert aggregate(records, min_cell_n=5)["systems"]["s1"] == {"overall": SMALL_TOTAL}
    # exactly the minimum is enough: only fewer than it is withheld
    assert cell(aggregate(records, min_cell_n=3))["remaining_n"] == 3


def test_withheld_output_carries_no_counts_of_the_small_cell():
    records = cells_of({("planning", "en", "authored"): ["success", "success"], ("intent", "zh", "forum"): BIG})
    text = render(aggregate(records, min_cell_n=5))
    assert "planning|en|authored" not in text


def test_the_minimum_must_be_a_positive_whole_number():
    for bad in (0, -1, True):
        with pytest.raises(ValueError, match="minimum"):
            aggregate(cells_of({("planning", "en", "authored"): BIG}), min_cell_n=bad)
