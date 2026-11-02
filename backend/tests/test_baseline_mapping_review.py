import json

import pytest

from app.evaluation.baseline_mapping_review import (
    accuracy_report,
    generate_review_rows,
    read_review_table,
    wilson_interval,
)


def output(*, matched=220):
    mappings = [
        {
            "original_name": f"matched {index}",
            "quantity_g": index + 1,
            "ingredient_id": "rice",
            "status": "matched",
            "method": "id",
            "needs_review": False,
            "suggestions": [],
            "review_reasons": [],
        }
        for index in range(matched)
    ]
    mappings += [
        {
            "original_name": "ambiguous milk",
            "quantity_g": 100,
            "ingredient_id": None,
            "status": "needs_review",
            "method": "similarity",
            "needs_review": True,
            "suggestions": ["milk", "milk_or_cream"],
            "review_reasons": ["spelling similarity 0.91"],
        },
        {
            "original_name": "mystery leaf",
            "quantity_g": 20,
            "ingredient_id": None,
            "status": "unmatched",
            "method": None,
            "needs_review": False,
            "suggestions": [],
            "review_reasons": ["no catalog ingredient above the similarity floor or as a parent"],
        },
    ]
    return {
        "schema_version": "offline-algorithm-comparison-dev-v1",
        "runs": [
            {
                "status": "completed",
                "system_id": "synthetic-baseline",
                "episode_id": "dev-synthetic-1",
                "repeat": 2,
                "result": {
                    "system_id": "synthetic-baseline",
                    "episode_id": "dev-synthetic-1",
                    "scored": {"dishes": [{"name": "synthetic dish", "mappings": mappings}]},
                },
            }
        ],
    }


def rows(**changes):
    return generate_review_rows(output(**changes), names={"rice": "Rice", "milk": "Milk"}, seed=1234)


def test_includes_all_suspicious_and_samples_at_least_200_matched_rows():
    result = rows()

    statuses = [row["mapping_status"] for row in result]
    assert statuses.count("matched") == 200
    assert statuses.count("needs_review") == 1
    assert statuses.count("unmatched") == 1
    assert next(row for row in result if row["mapping_status"] == "needs_review")["candidate_suggestions"] == [
        {"ingredient_id": "milk", "ingredient_name": "Milk"},
        {"ingredient_id": "milk_or_cream", "ingredient_name": None},
    ]
    suspicious = next(row for row in result if row["mapping_status"] == "needs_review")
    assert suspicious["mapping_method"] == "similarity"
    assert suspicious["review_reason"] == "spelling similarity 0.91"


def test_samples_all_matched_rows_when_fewer_than_200_exist():
    result = rows(matched=12)
    assert len(result) == 14


def test_fixed_seed_order_ids_and_blank_human_fields_are_stable():
    first = rows()
    second = rows()

    assert first == second
    assert len({row["row_id"] for row in first}) == len(first)
    assert all(row["row_id"].startswith("map-") for row in first)
    for row in first:
        assert row["system_id"] == "synthetic-baseline"
        assert row["episode_id"] == "dev-synthetic-1"
        assert row["run_id"] == "repeat-002"
        assert row["decision"] is None
        assert row["corrected_ingredient"] is None
        assert row["notes"] is None
        assert row["personally_reviewed"] is None


def test_wilson_interval_calculation():
    lower, upper = wilson_interval(8, 10)
    assert lower == pytest.approx(0.490162, abs=1e-6)
    assert upper == pytest.approx(0.943318, abs=1e-6)
    assert wilson_interval(0, 0) is None


def reviewed(row, decision, *, corrected=None, safety=None):
    updated = {
        **row,
        "personally_reviewed": True,
        "decision": decision,
        "corrected_ingredient": corrected,
        "safety_error": safety,
    }
    if safety:
        updated["safety_error_type"] = safety
        updated["safety_error"] = True
    return updated


def test_report_separates_accuracy_corrections_safety_and_unreviewed_rows():
    source = rows(matched=3)
    matched = [row for row in source if row["mapping_status"] == "matched"]
    suspicious = [row for row in source if row["mapping_status"] != "matched"]
    completed = [
        reviewed(matched[0], "correct"),
        reviewed(matched[1], "incorrect", corrected="oats"),
        matched[2],
        reviewed(suspicious[0], "incorrect", corrected="milk", safety="allergen_omission"),
        suspicious[1],
    ]

    report = accuracy_report(completed)

    assert report["accuracy"]["ordinary_matched"]["accuracy"] == 0.5
    assert report["accuracy"]["ordinary_matched"]["denominator"] == 2
    assert report["accuracy"]["ordinary_matched"]["unreviewed_excluded"] == 1
    assert report["accuracy"]["suspicious"]["accuracy"] == 0
    assert report["accuracy"]["suspicious"]["denominator"] == 1
    assert report["corrected"] == {"count": 2, "denominator": 3, "rate": 2 / 3}
    assert report["safety_errors"]["allergen_omission"] == 1
    assert report["safety_errors"]["false_allergen_assignment"] == 0
    assert report["counts"] == {"reviewed": 3, "unreviewed": 2, "invalid": 0}


def test_explicitly_invalid_review_row_is_counted_separately():
    row = {**rows(matched=1)[0], "personally_reviewed": False}

    report = accuracy_report([row])

    assert report["counts"] == {"reviewed": 0, "unreviewed": 0, "invalid": 1}
    assert report["accuracy"]["ordinary_matched"]["denominator"] == 0


@pytest.mark.parametrize(
    "change, message",
    [
        ({"mapping_status": "maybe"}, "invalid mapping_status"),
        ({"personally_reviewed": "yes"}, "personally_reviewed must be boolean or null"),
        ({"personally_reviewed": True, "decision": None}, "reviewed row requires a decision"),
        ({"personally_reviewed": None, "decision": "correct"}, "decision requires personally_reviewed=true"),
    ],
)
def test_malformed_review_table_is_rejected(tmp_path, change, message):
    row = {**rows(matched=1)[0], **change}
    path = tmp_path / "review.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_review_table(path)
