"""FORMAT TESTS ONLY: nine imaginary robots, never real household questions."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_sprint2_heldout.py"
SPEC = importlib.util.spec_from_file_location("author_check", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def demo_case(index=0, category="planning", language="en"):
    """Deliberately impossible, non-question text only."""
    text = f"FORMAT DEMO NOT A QUESTION: nine robots on imaginary planet {index}"
    return {
        "id": f"FORMAT_{index}",
        "category": category,
        "language": language,
        "subtype": "meal",
        "features": [],
        "horizon_days": 1,
        "turns": [text],
        "gold": {
            "kind": "plan",
            "disposition": "feasible",
            "hard_constraints": [
                {
                    "field": "household_size",
                    "operator": "eq",
                    "value": 9,
                    "unit": "people",
                    "scope": "household",
                    "evidence": "format only",
                }
            ],
            "expected_fields": {"action": "plan", "household_size": 9},
            "clarification_fields": [],
            "reference_answer": "FORMAT DEMO ONLY",
            "rubric": ["format only"],
            "preserve": ["imaginary robot identity"],
            "proof_basis": "No real facts: format demonstration only",
            "facts_version": "FORMAT_ONLY",
            "review_status": "independently_checked",
            "reviewer_id": "SYN_REVIEWER",
        },
        "source": {"kind": "authored", "quotes": [], "pii_reviewed": True},
    }


def bundle(cases=None):
    result = json.loads(SCRIPT.with_name("sprint2-heldout-template.json").read_text(encoding="utf-8"))
    result["cases"] = cases or []
    return result


def ready_format_fixture():
    cases = []
    for category, count in (("planning", 80), ("intent", 100), ("multi_turn", 6), ("adversarial", 8)):
        names = sorted(x.split(":", 1)[1] for x in checker.SUBTYPES if x.startswith(category + ":"))
        for i in range(count):
            case = demo_case(len(cases), category, "zh" if i % 2 else "en")
            case["subtype"] = names[i % len(names)]
            if category == "multi_turn":
                case["turns"].append(f"FORMAT DEMO: robot edit {len(cases)}")
                case["gold"]["kind"] = "replan"
            elif category == "intent":
                case["gold"]["kind"] = "intent"
                case["gold"]["disposition"] = "answer"
            cases.append(case)
    cases[0]["features"] = sorted(checker.FEATURES - {"horizon_14", "two_trips", "perishable_window"})
    cases[1]["features"] = ["horizon_14", "two_trips", "perishable_window"]
    cases[1]["horizon_days"] = 14
    cases[2]["features"] = ["two_trips", "perishable_window"]
    cases[2]["horizon_days"] = 8
    for case in cases[1:3]:
        case["gold"]["expected_fields"].update(
            shopping_trip_days=[1, 8], budget_basis="per_shopping_trip", perishable_window_days=3
        )
    for case in cases[: len(cases) // 3]:
        case["source"]["kind"] = "forum"
        case["source"]["quotes"] = [
            {
                "turn_index": i,
                "text": text,
                "url": f"https://example.invalid/thread/{case['id']}",
                "collected_on": "2026-01-01",
                "redactions": [],
            }
            for i, text in enumerate(case["turns"])
        ]
    result = bundle(cases)
    result.update(purpose="freeze_candidate", author_id="SYN_AUTHOR", reviewer_id="SYN_REVIEWER")
    result["quota_manifest"] = {
        "declared_on": "2026-01-01",
        "approved_by": "SYN_COORDINATOR",
        "fields_sha256": hashlib.sha256(SCRIPT.with_name("sprint2-heldout-fields.json").read_bytes()).hexdigest(),
        "counts": {c: sum(x["category"] == c for x in cases) for c in checker.CATEGORIES},
        "minimum_chinese": {c: 1 if c != "intent" else 34 for c in checker.CATEGORIES},
        "forum_count": len(cases) // 3,
        "subtype_minima": dict.fromkeys(sorted(checker.SUBTYPES), 1),
        "feature_minima": dict.fromkeys(sorted(checker.FEATURES), 1),
    }
    return result


def test_empty_template_is_not_release():
    assert checker.check(bundle(), format_only=True)[0] == []
    assert checker.check(bundle())[0]


def test_explicit_input_required():
    run = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert run.returncode != 0
    assert "--input" in run.stderr


def test_protected_path_rejected_before_read():
    with patch.object(Path, "read_bytes", side_effect=AssertionError("Must not read")):
        for part in ("heldout", "HELD-OUT", "holdout", "held_out"):
            try:
                checker.load_author_file(Path("fiction") / part / "never.json")
            except ValueError:
                pass
            else:
                raise AssertionError("Protected path accepted")


def test_resolved_alias_rejected_before_read():
    with (
        patch.object(Path, "resolve", return_value=Path("fiction/heldout/never.json")),
        patch.object(Path, "read_bytes", side_effect=AssertionError("Must not read")),
    ):
        try:
            checker.load_author_file(Path("fiction/alias.json"))
        except ValueError:
            pass
        else:
            raise AssertionError("Protected alias accepted")


def test_formal_structure_only_synthetic_fixture():
    errors, summary = checker.check(ready_format_fixture())
    assert errors == []
    assert summary["category_counts"]["planning"] == 80


def test_schema_errors_do_not_echo_request():
    case = demo_case()
    case["turns"] = "SECRET_FORMAT_SENTINEL"
    errors, _ = checker.check(bundle([case]), format_only=True)
    assert errors and "SECRET_FORMAT_SENTINEL" not in json.dumps(errors)


def test_duplicate_requests_and_ids():
    case = demo_case()
    errors, _ = checker.check(bundle([case, copy.deepcopy(case)]), format_only=True)
    assert any("duplicate ID" in x for x in errors)
    assert any("duplicate request" in x for x in errors)


def test_forum_provenance_and_pii():
    case = demo_case()
    case["source"] = {"kind": "forum", "quotes": [], "pii_reviewed": True}
    assert checker.check(bundle([case]), format_only=True)[0]
    case["turns"] = ["FORMAT DEMO NOT A QUESTION: nine robots; contact robot@example.invalid"]
    errors, _ = checker.check(bundle([case]), format_only=True)
    assert any("personal information" in x for x in errors)
    assert "robot@example.invalid" not in json.dumps(errors)


def test_chinese_quota_and_review_enforced():
    data = ready_format_fixture()
    for case in data["cases"]:
        case["language"] = "en"
        case["gold"]["review_status"] = "pending"
    errors, _ = checker.check(data)
    assert any("Chinese" in x for x in errors)
    assert any("independent gold" in x for x in errors)


def test_feature_and_quote_mismatch():
    data = ready_format_fixture()
    data["quota_manifest"]["feature_minima"] = {}
    data["cases"][0]["source"]["quotes"][0]["text"] = "FORMAT DEMO: ten robots"
    errors, _ = checker.check(data)
    assert any("feature_minima" in x for x in errors)
    assert any("quote must equal" in x for x in errors)


def test_read_only_and_nonfinite_json(tmp_path):
    target = tmp_path / "robots-format.json"
    raw = json.dumps(bundle([demo_case()]))
    target.write_text(raw, encoding="utf-8")
    checker.check(checker.load_author_file(target), format_only=True)
    assert target.read_text(encoding="utf-8") == raw
    target.write_text('{"x":NaN}', encoding="utf-8")
    try:
        checker.load_author_file(target)
    except ValueError:
        pass
    else:
        raise AssertionError("NaN accepted")


def test_gold_missing_scope_and_unknown_fields():
    case = demo_case()
    del case["gold"]["hard_constraints"][0]["scope"]
    case["extra"] = "FORMAT DEMO"
    assert checker.check(bundle([case]), format_only=True)[0]


def test_overflow_number_rejected_without_content():
    data = bundle([demo_case()])
    data["cases"][0]["gold"]["hard_constraints"][0]["value"] = float("inf")
    errors, _ = checker.check(data, format_only=True)
    assert errors == ["Non-finite numeric value rejected"]


def test_numeric_public_thread_id_is_not_a_phone_number():
    data = ready_format_fixture()
    data["cases"][0]["source"]["quotes"][0]["url"] = "https://example.invalid/thread/123456789"
    assert checker.check(data)[0] == []


def test_dictionary_rejects_unknown_fields_scopes_types_and_missing_action():
    for change in ("unknown_field", "unknown_scope", "wrong_type", "missing_action", "wrong_unit"):
        case = demo_case()
        if change == "unknown_field":
            case["gold"]["expected_fields"]["fictional_unknown"] = 9
        elif change == "unknown_scope":
            case["gold"]["hard_constraints"][0]["scope"] = "fictional_unknown"
        elif change == "wrong_type":
            case["gold"]["expected_fields"]["household_size"] = "nine imaginary robots"
        elif change == "missing_action":
            del case["gold"]["expected_fields"]["action"]
        else:
            case["gold"]["hard_constraints"][0]["unit"] = "fictional_robot_units"
        assert checker.check(bundle([case]), format_only=True)[0]


def test_dictionary_digest_and_reviewed_extension(tmp_path):
    data = ready_format_fixture()
    dictionary = json.loads(SCRIPT.with_name("sprint2-heldout-fields.json").read_text(encoding="utf-8"))
    dictionary["dictionary_version"] = "FORMAT_ONLY_EXTENSION"
    dictionary["fields"]["fictional_robot_units"] = {"units": ["fictional"], "schema": {"type": "integer"}}
    target = tmp_path / "robot-field-dictionary.json"
    target.write_text(json.dumps(dictionary), encoding="utf-8")
    assert any("SHA-256" in e for e in checker.check(data, fields_path=target)[0])
    data["quota_manifest"]["fields_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    data["cases"][0]["gold"]["expected_fields"]["fictional_robot_units"] = 9
    assert checker.check(data, fields_path=target)[0] == []
    dictionary["fields"]["fictional_robot_units"]["schema"] = {"$ref": "https://example.invalid/never-fetch"}
    target.write_text(json.dumps(dictionary), encoding="utf-8")
    assert any("references" in e for e in checker.check(data, fields_path=target)[0])


def test_handle_screen_and_redaction_markers():
    for handle in ("u/fictional_robot", "@fictional_robot", "/u/fictional_robot", "u/虚构机器人", "@虚构机器人"):
        case = demo_case()
        case["turns"][0] += " " + handle
        assert any("personal information" in e for e in checker.check(bundle([case]), format_only=True)[0])
    data = ready_format_fixture()
    data["cases"][0]["source"]["quotes"][0]["redactions"] = ["fictional robot handle"]
    assert any("redaction notes" in e for e in checker.check(data)[0])
    data["cases"][0]["turns"][0] += " [REDACTED]"
    data["cases"][0]["source"]["quotes"][0]["text"] = data["cases"][0]["turns"][0]
    assert checker.check(data)[0] == []


def test_subtype_and_personnel_independence():
    data = ready_format_fixture()
    data["cases"][0]["gold"]["kind"] = "qa"
    data["cases"][1]["gold"]["reviewer_id"] = data["author_id"]
    data["quota_manifest"]["approved_by"] = data["reviewer_id"]
    errors, _ = checker.check(data)
    assert any("gold.kind mismatch" in e for e in errors)
    assert any("author cannot review" in e for e in errors)
    assert any("approver must differ" in e for e in errors)


def test_catalog_dependent_and_two_trip_rules():
    data = ready_format_fixture()
    data["cases"][0]["gold"]["disposition"] = "catalog_dependent"
    assert checker.check(data)[0] == []
    del data["cases"][1]["gold"]["expected_fields"]["budget_basis"]
    assert any("per-trip budget" in e for e in checker.check(data)[0])
    data["cases"][2]["horizon_days"] = 1
    assert any("At least two planning" in e for e in checker.check(data)[0])


def test_intent_gold_does_not_invent_procurement_defaults():
    case = demo_case(category="intent")
    case.update(subtype="planning", horizon_days=14)
    case["gold"]["kind"] = "intent"
    case["gold"]["disposition"] = "answer"
    assert checker.check(bundle([case]), format_only=True)[0] == []


def test_dictionary_digest_uses_the_same_bytes_as_parsing(tmp_path):
    data = ready_format_fixture()
    target = tmp_path / "robot-dictionary.json"
    raw = SCRIPT.with_name("sprint2-heldout-fields.json").read_bytes()
    target.write_bytes(raw)
    with patch.object(Path, "read_bytes", wraps=Path.read_bytes, autospec=True) as read:
        # A changed file cannot be parsed once and hashed a second time.
        read.side_effect = lambda path: raw if path == target else Path.read_text(path, encoding="utf-8").encode()
        assert checker.check(data, fields_path=target)[0] == []
        assert sum(call.args[0] == target for call in read.call_args_list) == 1


@pytest.mark.parametrize("handle", ["回复@小明", "谢谢@zhangsan", "我是u/abc"])
def test_chinese_adjacent_handle_rejected_without_echo(handle):
    case = demo_case()
    case["turns"][0] += " " + handle
    errors, _ = checker.check(bundle([case]), format_only=True)
    assert any("personal information" in error for error in errors)
    assert handle not in json.dumps(errors, ensure_ascii=False)


@pytest.mark.parametrize(
    ("tag", "days", "valid"),
    [
        ("two_trips", None, False),
        ("two_trips", 1, False),
        ("two_trips", 7, False),
        ("two_trips", 8, True),
        ("perishable_window", None, False),
        ("perishable_window", 7, False),
        ("perishable_window", 14, True),
        ("horizon_1", 1, True),
        ("horizon_1", 14, False),
        ("horizon_14", 1, False),
        ("horizon_14", 14, True),
    ],
)
def test_feature_tags_match_horizon(tag, days, valid):
    # Intent-only placeholders isolate tag consistency from plan procurement facts.
    case = demo_case(category="intent")
    case.update(subtype="planning", horizon_days=days, features=[tag])
    case["gold"].update(kind="intent", disposition="answer")
    errors, _ = checker.check(bundle([case]), format_only=True)
    assert (errors == []) == valid


@pytest.mark.parametrize(
    ("kind", "allowed"),
    [
        ("plan", {"feasible", "infeasible", "catalog_dependent", "clarify"}),
        ("replan", {"feasible", "infeasible", "catalog_dependent", "clarify"}),
        ("intent", {"answer", "clarify", "refuse"}),
        ("qa", {"answer", "clarify", "refuse"}),
        ("refusal", {"refuse"}),
    ],
)
def test_disposition_matches_gold_kind(kind, allowed):
    for disposition in ("feasible", "infeasible", "catalog_dependent", "clarify", "answer", "refuse"):
        case = demo_case()
        if kind == "replan":
            case.update(category="multi_turn", subtype="swap")
            case["turns"].append("FORMAT DEMO: robot edit")
        elif kind in {"intent", "qa", "refusal"}:
            case.update(category="intent", subtype="out_of_scope" if kind == "refusal" else "food_qa")
        case["gold"].update(kind=kind, disposition=disposition, clarification_fields=["FORMAT_ONLY"])
        errors, _ = checker.check(bundle([case]), format_only=True)
        assert (errors == []) == (disposition in allowed), (kind, disposition, errors)


@pytest.mark.parametrize("operator", ["le", "ge"])
def test_ordered_constraints_require_numbers_not_bool_or_containers(operator):
    for field, value, unit, valid in (
        ("household_size", 9, "people", True),
        ("weekly_budget_sgd", 9.5, "SGD", True),
        ("halal_required", True, "none", False),
        ("halal_required", False, "none", False),
        ("allergens", ["FORMAT_ONLY"], "none", False),
        ("budget_basis", "per_shopping_trip", "none", False),
        ("meal_structure", {}, "dishes", False),
    ):
        case = demo_case()
        case["gold"]["hard_constraints"][0].update(field=field, value=value, unit=unit, operator=operator)
        errors, _ = checker.check(bundle([case]), format_only=True)
        assert (errors == []) == valid, (operator, field, errors)
