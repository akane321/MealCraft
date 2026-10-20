"""FORMAT TESTS ONLY: nine imaginary robots, never real household questions."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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
                    "field": "robot_count",
                    "operator": "eq",
                    "value": 9,
                    "unit": "imaginary robots",
                    "scope": "fiction",
                    "evidence": "format only",
                }
            ],
            "expected_fields": {"imaginary_robot_count": 9},
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
            cases.append(case)
    cases[0]["features"] = sorted(checker.FEATURES - {"horizon_14"})
    cases[1]["features"] = ["horizon_14"]
    cases[1]["horizon_days"] = 14
    for case in cases[: len(cases) // 3]:
        case["source"]["kind"] = "forum"
        case["source"]["quotes"] = [
            {
                "turn_index": i,
                "text": text,
                "url": f"https://example.invalid/thread/{case['id']}",
                "collected_on": "2026-01-01",
                "redactions": ["format only"],
            }
            for i, text in enumerate(case["turns"])
        ]
    result = bundle(cases)
    result.update(purpose="freeze_candidate", author_id="SYN_AUTHOR", reviewer_id="SYN_REVIEWER")
    result["quota_manifest"] = {
        "declared_on": "2026-01-01",
        "approved_by": "SYN_COORDINATOR",
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
    with patch.object(Path, "read_text", side_effect=AssertionError("Must not read")):
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
        patch.object(Path, "read_text", side_effect=AssertionError("Must not read")),
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
