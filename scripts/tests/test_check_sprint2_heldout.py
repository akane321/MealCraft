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


# Review attestation: imaginary robots again. The content keeps its authored, pending review fields; the
# attestation, bound to the exact content bytes, records two reviewers and an AI-executed review truthfully.


def pending_content():
    """The ready fixture as authored: draft purpose, no reviewer, every per-case review still pending."""
    data = ready_format_fixture()
    data.update(purpose="author_draft", reviewer_id=None)
    for case in data["cases"]:
        case["gold"].update(review_status="pending", reviewer_id=None)
        case["source"]["pii_reviewed"] = False
    return data


def content_bytes(data):
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def attestation_for(data, executed_by="ai", second_share=31):
    ids = [case["id"] for case in data["cases"]]
    split = len(ids) - second_share
    return {
        "schema_version": "sprint2-review-attestation-v1",
        "content_sha256": hashlib.sha256(content_bytes(data)).hexdigest(),
        "fields_sha256": data["quota_manifest"]["fields_sha256"],
        "purpose": "freeze_candidate",
        "author_id": data["author_id"],
        "recorded_on": "2026-01-02",
        "reviewers": [
            {"reviewer_id": "SYN_REVIEWER_ONE", "executed_by": executed_by},
            {"reviewer_id": "SYN_REVIEWER_TWO", "executed_by": executed_by},
        ],
        "dictionary_review": {"reviewer_id": "SYN_REVIEWER_TWO", "status": "independently_checked"},
        "cases": {
            case_id: {
                "gold_review": {
                    "reviewer_id": "SYN_REVIEWER_ONE" if index < split else "SYN_REVIEWER_TWO",
                    "status": "independently_checked",
                },
                "anonymisation_review": {"reviewer_id": "SYN_REVIEWER_TWO", "status": "independently_checked"},
            }
            for index, case_id in enumerate(ids)
        },
    }


def check_attested(data, attestation):
    return checker.check(
        data,
        attestation=attestation,
        content_sha256=hashlib.sha256(content_bytes(data)).hexdigest(),
        attestation_sha256="0" * 64,
    )


def test_pending_content_fails_readiness_without_an_attestation():
    errors, _ = checker.check(pending_content())
    assert any("purpose=freeze_candidate" in e for e in errors)
    assert any("independent gold review missing" in e for e in errors)


def test_an_attestation_makes_pending_content_ready_without_editing_it():
    data = pending_content()
    before = content_bytes(data)
    errors, summary = check_attested(data, attestation_for(data))
    assert errors == []
    assert content_bytes(data) == before
    reviewers = summary["attestation"]["reviewers"]
    assert reviewers["SYN_REVIEWER_ONE"]["gold_reviews"] == len(data["cases"]) - 31
    assert reviewers["SYN_REVIEWER_TWO"]["gold_reviews"] == 31
    # An AI-executed review passes but is reported as what it is.
    assert any("anonymisation_review" in item and "AI" in item for item in summary["limitations"])
    assert any("dictionary_review" in item for item in summary["limitations"])


def test_human_reviews_carry_no_limitation():
    data = pending_content()
    errors, summary = check_attested(data, attestation_for(data, executed_by="human"))
    assert errors == [] and summary["limitations"] == []


def test_the_attestation_is_bound_to_the_exact_content_bytes():
    data = pending_content()
    attestation = attestation_for(data)
    attestation["content_sha256"] = "a" * 64
    errors, _ = check_attested(data, attestation)
    assert any("content_sha256 does not match" in e for e in errors)
    attestation = attestation_for(data)
    attestation["fields_sha256"] = "b" * 64
    errors, _ = check_attested(data, attestation)
    assert any("fields_sha256 does not match" in e for e in errors)


def test_every_case_needs_one_entry_and_errors_echo_no_case_id():
    data = pending_content()
    attestation = attestation_for(data)
    removed = data["cases"][5]["id"]
    del attestation["cases"][removed]
    attestation["cases"]["FORMAT_UNKNOWN_ROBOT"] = attestation["cases"][data["cases"][6]["id"]]
    errors, summary = check_attested(data, attestation)
    assert any("1 case(s) have no review entry" in e for e in errors)
    assert any("name no case in the content file" in e for e in errors)
    assert "FORMAT_" not in json.dumps([errors, summary])


def test_reviewers_must_be_independent_and_listed():
    data = pending_content()
    for reviewer in (data["author_id"], data["quota_manifest"]["approved_by"]):
        attestation = attestation_for(data)
        attestation["reviewers"][0]["reviewer_id"] = reviewer
        for entry in attestation["cases"].values():
            if entry["gold_review"]["reviewer_id"] == "SYN_REVIEWER_ONE":
                entry["gold_review"]["reviewer_id"] = reviewer
        errors, _ = check_attested(data, attestation)
        assert any("the author or the quota approver" in e for e in errors), reviewer
    attestation = attestation_for(data)
    attestation["dictionary_review"]["reviewer_id"] = "SYN_NOT_LISTED"
    errors, _ = check_attested(data, attestation)
    assert any("not listed" in e for e in errors)
    attestation = attestation_for(data)
    attestation["reviewers"].append(dict(attestation["reviewers"][0]))
    errors, _ = check_attested(data, attestation)
    assert any("listed twice" in e for e in errors)


def test_a_content_reviewer_that_contradicts_the_attestation_fails():
    data = pending_content()
    data["cases"][0]["gold"]["reviewer_id"] = "SYN_SOMEONE_ELSE"
    errors, _ = check_attested(data, attestation_for(data))
    assert any("different gold reviewer" in e for e in errors)


def test_an_attestation_only_in_readiness_and_with_content_bytes():
    data = pending_content()
    with pytest.raises(ValueError):
        checker.check(data, format_only=True, attestation=attestation_for(data), content_sha256="0" * 64)
    with pytest.raises(ValueError):
        checker.check(data, attestation=attestation_for(data))


def test_attestation_schema_errors_do_not_echo_values():
    data = pending_content()
    attestation = attestation_for(data)
    attestation["reviewers"][0]["executed_by"] = "SECRET_FORMAT_SENTINEL"
    errors, _ = check_attested(data, attestation)
    assert errors and not any("SECRET_FORMAT_SENTINEL" in e for e in errors)


def test_cli_reads_an_attestation_and_refuses_it_with_format_only(tmp_path):
    data = pending_content()
    content = tmp_path / "author-draft.json"
    content.write_bytes(content_bytes(data))
    attested = tmp_path / "attestation.json"
    attested.write_text(json.dumps(attestation_for(data)), encoding="utf-8")
    base = [sys.executable, str(SCRIPT), "--input", str(content), "--attestation", str(attested)]
    run = subprocess.run(base, capture_output=True, text=True)
    report = json.loads(run.stdout)
    assert run.returncode == 0, report["errors"]
    assert report["mode"] == "readiness_with_attestation" and report["checker_version"] == checker.CHECKER_VERSION
    assert report["summary"]["attestation"]["sha256"] == hashlib.sha256(attested.read_bytes()).hexdigest()
    refused = subprocess.run([*base, "--format-only"], capture_output=True, text=True)
    assert refused.returncode == 2 and not refused.stdout


def test_the_content_reviewer_must_be_an_attested_independent_reviewer():
    data = pending_content()
    for reviewer in (data["author_id"], data["quota_manifest"]["approved_by"], "SYN_SOMEONE_ELSE"):
        data["reviewer_id"] = reviewer
        errors, _ = check_attested(data, attestation_for(data))
        assert any("reviewer_id is not an attested reviewer" in e for e in errors), reviewer
    data["reviewer_id"] = "SYN_REVIEWER_ONE"
    assert check_attested(data, attestation_for(data))[0] == []


def test_a_format_demo_is_not_a_release_even_with_an_attestation():
    data = pending_content()
    data["purpose"] = "format_demo"
    errors, _ = check_attested(data, attestation_for(data))
    assert any("format demo" in e for e in errors)


def test_a_human_anonymisation_claim_cannot_be_attested_as_ai():
    data = pending_content()
    data["cases"][0]["source"]["pii_reviewed"] = True
    errors, _ = check_attested(data, attestation_for(data, executed_by="ai"))
    assert any("1 case(s) mark a human anonymisation review" in e for e in errors)
    assert check_attested(data, attestation_for(data, executed_by="human"))[0] == []


def test_upper_case_digests_match_and_reviewer_ids_are_pseudonyms():
    data = pending_content()
    attestation = attestation_for(data)
    attestation["content_sha256"] = attestation["content_sha256"].upper()
    attestation["fields_sha256"] = attestation["fields_sha256"].upper()
    assert check_attested(data, attestation)[0] == []
    attestation = attestation_for(data)
    attestation["reviewers"][0]["reviewer_id"] = "someone@example.invalid"
    errors, _ = check_attested(data, attestation)
    assert errors and not any("example.invalid" in e for e in errors)


def test_repeated_json_keys_are_rejected():
    with pytest.raises(ValueError):
        checker.parse_json(b'{"executed_by": "ai", "executed_by": "human"}')


def test_cli_puts_ai_limitations_at_the_top_level(tmp_path):
    data = pending_content()
    content = tmp_path / "author-draft.json"
    content.write_bytes(content_bytes(data))
    attested = tmp_path / "attestation.json"
    attested.write_text(json.dumps(attestation_for(data)), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(content), "--attestation", str(attested)],
        capture_output=True,
        text=True,
    )
    report = json.loads(run.stdout)
    assert report["passed"] and any("AI" in item for item in report["limitations"])


def test_an_attestation_in_a_protected_directory_is_rejected_before_read():
    with patch.object(Path, "read_bytes", side_effect=AssertionError("Must not read")):
        with pytest.raises(ValueError):
            checker.read_author_bytes(Path("fiction") / "heldout" / "attestation.json")
