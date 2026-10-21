"""Check one explicitly supplied author draft; never discover or run a test set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

CATEGORIES = ("planning", "intent", "multi_turn", "adversarial")
SUBTYPES = {
    "planning:meal",
    "planning:day",
    "planning:week",
    "intent:planning",
    "intent:food_qa",
    "intent:out_of_scope",
    "intent:injection",
    "intent:preference",
    "multi_turn:swap",
    "multi_turn:meal_shape",
    "multi_turn:budget_replan",
    "adversarial:infeasible",
    "adversarial:contradiction",
    "adversarial:hidden_allergen",
    "adversarial:local_name",
}
FEATURES = {
    "full_table",
    "shared_dishes",
    "member_rules",
    "attendance",
    "halal",
    "basic_seasonings",
    "sodium_limit",
    "horizon_1",
    "horizon_14",
    "two_trips",
    "perishable_window",
}
PROTECTED_PARTS = {"heldout", "held-out", "held_out", "holdout", "hold-out", "hold_out"}
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+\d[\d ()-]{6,}\d|\d{8,})(?!\w)")
PROFILE = re.compile(r"https?://[^\s/]+/(?:u|user|users|profile|profiles)/", re.I)
HANDLE = re.compile(r"(?<![A-Za-z0-9_/])(?:/?u/[\w-]+|@\w[\w.-]*)", re.I)
KINDS = {
    "planning": {"plan"},
    "multi_turn": {"replan"},
    "intent:planning": {"intent"},
    "intent:food_qa": {"intent", "qa"},
    "intent:out_of_scope": {"intent", "refusal"},
    "intent:injection": {"intent", "refusal"},
    "intent:preference": {"intent"},
    "adversarial:infeasible": {"plan", "replan"},
    "adversarial:contradiction": {"plan", "replan", "intent"},
    "adversarial:hidden_allergen": {"plan", "intent", "qa"},
    "adversarial:local_name": {"plan", "intent", "qa"},
}
DISPOSITIONS = {
    "plan": {"feasible", "infeasible", "catalog_dependent", "clarify"},
    "replan": {"feasible", "infeasible", "catalog_dependent", "clarify"},
    "intent": {"answer", "clarify", "refuse"},
    "qa": {"answer", "clarify", "refuse"},
    "refusal": {"refuse"},
}


def reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


def read_author_bytes(path: Path) -> bytes:
    # Check both the supplied path and resolved destination, before reading bytes.
    for candidate in (path.absolute(), path.resolve()):
        if PROTECTED_PARTS.intersection(part.casefold() for part in candidate.parts):
            raise ValueError("Protected directory rejected before read")
    return path.read_bytes()


def load_author_file(path: Path) -> dict:
    return json.loads(read_author_bytes(path).decode("utf-8-sig"), parse_constant=reject_constant)


def finite_numbers(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_numbers(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_numbers(item) for item in value)
    return True


def string_leaves(value, path=()):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from string_leaves(item, (*path, index))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from string_leaves(item, (*path, key))


def check(data: dict, *, format_only: bool = False, fields_path: Path | None = None) -> tuple[list[str], dict]:
    if not finite_numbers(data):
        return ["Non-finite numeric value rejected"], {}
    schema = json.loads(Path(__file__).with_name("sprint2-heldout.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in validator.iter_errors(data):
        # Never echo error.message: it can contain a private request or gold label.
        location = "/".join(str(p) if isinstance(p, int) else "field" for p in error.absolute_path)
        errors.append(f"schema:{error.validator} at /{location}")
    if errors:
        return errors, {}
    fields_path = fields_path or Path(__file__).with_name("sprint2-heldout-fields.json")
    raw_dictionary = read_author_bytes(fields_path)
    dictionary = json.loads(raw_dictionary.decode("utf-8-sig"), parse_constant=reject_constant)
    digest = hashlib.sha256(raw_dictionary).hexdigest()
    if (
        not isinstance(dictionary, dict)
        or not isinstance(dictionary.get("fields"), dict)
        or not isinstance(dictionary.get("scopes"), dict)
    ):
        return ["Invalid field dictionary structure"], {}
    if "action" not in dictionary["fields"] or not dictionary["scopes"]:
        return ["Dictionary needs action and named scopes"], {}
    # Dictionary extensions are inline schemas, never references that can fetch URLs.
    if any(key in {"$ref", "$dynamicRef"} for path, _text in string_leaves(dictionary) for key in path):
        return ["Dictionary references are forbidden; inline field types"], {}
    for definition in dictionary["fields"].values():
        if (
            not isinstance(definition, dict)
            or not isinstance(definition.get("units"), list)
            or not definition["units"]
            or "schema" not in definition
        ):
            return ["Dictionary field needs inline schema and nonempty units"], {}
        Draft202012Validator.check_schema(definition["schema"])
    expected_validator = Draft202012Validator(
        {
            "type": "object",
            "required": ["action"],
            "additionalProperties": False,
            "properties": {key: definition["schema"] for key, definition in dictionary["fields"].items()},
        },
        format_checker=FormatChecker(),
    )
    recorded_digest = data["quota_manifest"]["fields_sha256"]
    if recorded_digest != digest and (recorded_digest is not None or not format_only):
        errors.append("Field dictionary SHA-256 missing or mismatched")
    cases = data["cases"]
    counts = Counter(c["category"] for c in cases)
    chinese = Counter(c["category"] for c in cases if c["language"] == "zh")
    forums = sum(c["source"]["kind"] == "forum" for c in cases)
    summary = {
        "schema_version": data["schema_version"],
        "case_count": len(cases),
        "category_counts": dict(counts),
        "chinese_counts": dict(chinese),
        "forum_count": forums,
    }
    seen = set()
    seen_turns = set()
    for index, case in enumerate(cases):
        prefix = f"case[{index}]"
        if case["id"] in seen:
            errors.append(f"{prefix}: duplicate ID")
        seen.add(case["id"])
        normalized = tuple(" ".join(turn.split()).casefold() for turn in case["turns"])
        if normalized in seen_turns:
            errors.append(f"{prefix}: duplicate request sequence")
        seen_turns.add(normalized)
        for field_path, text in string_leaves(case):
            # Stable source IDs/dates are not phone numbers. Their privacy still
            # needs human review; never erase provenance to satisfy a regex.
            if field_path[-1] in {"id", "url", "collected_on", "facts_version"}:
                continue
            if EMAIL.search(text) or PHONE.search(text) or PROFILE.search(text) or HANDLE.search(text):
                errors.append(f"{prefix}: possible personal information; human review required")
                break
        source = case["source"]
        if source["kind"] == "authored" and source["quotes"]:
            errors.append(f"{prefix}: authored case must not claim forum provenance")
        if source["kind"] == "forum":
            indices = [q["turn_index"] for q in source["quotes"]]
            if sorted(indices) != list(range(len(case["turns"]))):
                errors.append(f"{prefix}: every forum user turn needs exactly one real quote")
            for quote in source["quotes"]:
                turn = quote["turn_index"]
                if turn >= len(case["turns"]) or quote["text"] != case["turns"][turn]:
                    errors.append(f"{prefix}: redacted quote must equal its user turn")
                url = urlsplit(quote["url"])
                if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
                    errors.append(f"{prefix}: invalid public source URL")
                if url.query or url.fragment:
                    errors.append(f"{prefix}: use canonical public URL without tracking query or fragment")
                if PROFILE.search(quote["url"]):
                    errors.append(f"{prefix}: use a thread/comment source, not a personal profile")
                if bool(quote["redactions"]) != ("[REDACTED]" in quote["text"]):
                    errors.append(f"{prefix}: redaction notes and [REDACTED] marker must correspond")
        gold = case["gold"]
        if any(expected_validator.iter_errors(gold["expected_fields"])):
            errors.append(f"{prefix}: expected_fields violate the frozen dictionary")
        for constraint in gold["hard_constraints"]:
            if constraint["operator"] in {"le", "ge"} and (
                isinstance(constraint["value"], bool) or not isinstance(constraint["value"], (int, float))
            ):
                errors.append(f"{prefix}: le/ge require a numeric value, not boolean or structured data")
            definition = dictionary["fields"].get(constraint["field"])
            if definition is None or constraint["scope"] not in dictionary["scopes"]:
                errors.append(f"{prefix}: constraint field/scope missing from dictionary")
            elif constraint["unit"] not in definition["units"] or not Draft202012Validator(
                definition["schema"], format_checker=FormatChecker()
            ).is_valid(constraint["value"]):
                errors.append(f"{prefix}: constraint unit/value violate dictionary")
            if constraint["scope"] == "member" and not constraint.get("target_member_ids"):
                errors.append(f"{prefix}: member-scoped constraint needs target_member_ids")
        kind_key = (
            case["category"]
            if case["category"] in {"planning", "multi_turn"}
            else f"{case['category']}:{case['subtype']}"
        )
        if gold["kind"] not in KINDS.get(kind_key, set()):
            errors.append(f"{prefix}: subtype and gold.kind mismatch")
        if gold["disposition"] not in DISPOSITIONS[gold["kind"]]:
            errors.append(f"{prefix}: gold.kind and disposition mismatch")
        if gold["reviewer_id"] is not None and gold["reviewer_id"] == data["author_id"]:
            errors.append(f"{prefix}: author cannot review own gold")
        if f"{case['category']}:{case['subtype']}" not in SUBTYPES:
            errors.append(f"{prefix}: unknown category/subtype combination")
        if case["category"] == "planning" and gold["kind"] != "plan":
            errors.append(f"{prefix}: planning category needs plan gold")
        if case["category"] == "multi_turn" and len(case["turns"]) < 2:
            errors.append(f"{prefix}: multi_turn needs at least two user turns")
        if gold["disposition"] == "clarify" and not gold["clarification_fields"]:
            errors.append(f"{prefix}: clarification needs named missing/ambiguous fields")
        if gold["kind"] in {"intent", "replan"} and not gold["expected_fields"]:
            errors.append(f"{prefix}: structured expected fields required")
        if gold["kind"] == "qa" and (not gold["reference_answer"] or not gold["rubric"]):
            errors.append(f"{prefix}: QA needs reference answer and scoring rubric")
        if gold["kind"] in {"plan", "replan"} and gold["disposition"] in {
            "feasible",
            "infeasible",
            "catalog_dependent",
        }:
            if not gold["hard_constraints"] or case["horizon_days"] is None:
                errors.append(f"{prefix}: planning gold needs constraints and explicit horizon")
        if case["category"] == "multi_turn" and not gold["preserve"]:
            errors.append(f"{prefix}: declare what edits must preserve, or explicitly declare none")
        days = case["horizon_days"]
        if {"two_trips", "perishable_window"}.intersection(case["features"]) and (days is None or days <= 7):
            errors.append(f"{prefix}: two_trips/perishable_window require horizon_days > 7")
        for boundary in (1, 14):
            if f"horizon_{boundary}" in case["features"] and days != boundary:
                errors.append(f"{prefix}: horizon_{boundary} tag requires horizon_days == {boundary}")
        if gold["kind"] in {"plan", "replan"} and case["horizon_days"] is not None and case["horizon_days"] > 7:
            if not {"two_trips", "perishable_window"}.issubset(case["features"]):
                errors.append(f"{prefix}: long horizon needs two-trip and freshness coverage")
            if (
                gold["expected_fields"].get("shopping_trip_days") != [1, 8]
                or gold["expected_fields"].get("budget_basis") != "per_shopping_trip"
                or gold["expected_fields"].get("perishable_window_days") != 3
            ):
                errors.append(f"{prefix}: long horizon needs explicit two-trip, per-trip budget and 3-day window facts")
        if not format_only:
            if not source["pii_reviewed"]:
                errors.append(f"{prefix}: human anonymisation review missing")
            if gold["review_status"] != "independently_checked" or gold["reviewer_id"] != data["reviewer_id"]:
                errors.append(f"{prefix}: independent gold review missing")
    if format_only:
        return sorted(set(errors)), summary
    if data["purpose"] != "freeze_candidate":
        errors.append("Formal readiness requires purpose=freeze_candidate; drafts/demos are not a release")
    if not data["author_id"] or not data["reviewer_id"] or data["author_id"] == data["reviewer_id"]:
        errors.append("Distinct author and independent reviewer IDs are required")
    manifest = data["quota_manifest"]
    if not manifest["declared_on"] or not manifest["approved_by"]:
        errors.append("Quota declaration date and approver are required")
    if manifest["approved_by"] in {data["author_id"], data["reviewer_id"]}:
        errors.append("Quota approver must differ from author and reviewer")
    if sum(c["category"] == "planning" and c["horizon_days"] is not None and c["horizon_days"] > 7 for c in cases) < 2:
        errors.append("At least two planning cases must cover 8-14 days")
    for category in CATEGORIES:
        required = manifest["counts"][category]
        minimum = manifest["minimum_chinese"][category]
        floor = 80 if category == "planning" else 100 if category == "intent" else 1
        if required is None or required < floor or counts[category] != required:
            errors.append(f"quota:{category}: exact declared count missing or unmet (minimum {floor})")
        if minimum is None or minimum < 1 or chinese[category] < minimum:
            errors.append(f"language:{category}: predeclared Chinese coverage missing or unmet")
    if chinese["intent"] * 3 < counts["intent"]:
        errors.append("language:intent: Chinese must be at least one third")
    if any(not any(c["language"] == "en" and c["category"] == cat for c in cases) for cat in CATEGORIES):
        errors.append("Each category needs English coverage as well as Chinese coverage")
    target = manifest["forum_count"]
    if target is None or target not in {len(cases) // 3, math.ceil(len(cases) / 3)} or forums != target:
        errors.append("forum: declare and meet one-third count rounded down or up before authoring")
    subtypes = Counter(f"{c['category']}:{c['subtype']}" for c in cases)
    features = Counter(feature for c in cases for feature in c["features"])
    for name, required_names, actual in (
        ("subtype_minima", SUBTYPES, subtypes),
        ("feature_minima", FEATURES, features),
    ):
        minima = manifest[name]
        if not required_names.issubset(minima):
            errors.append(f"{name}: required coverage not predeclared")
        for label, minimum in minima.items():
            if actual[label] < minimum:
                # Labels are author-controlled; do not echo them into developer logs.
                errors.append(f"{name}: a declared minimum is unmet")
    for days in (1, 14):
        if not any(c["horizon_days"] == days and f"horizon_{days}" in c["features"] for c in cases):
            errors.append(f"horizon:{days}: actual boundary case missing")
    return sorted(set(errors)), summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Explicit author-owned JSON, outside protected directories"
    )
    parser.add_argument("--format-only", action="store_true", help="No freeze-readiness claim")
    parser.add_argument(
        "--fields", type=Path, help="Author-owned field dictionary; defaults to the adjacent dictionary"
    )
    args = parser.parse_args()
    try:
        errors, summary = check(load_author_file(args.input), format_only=args.format_only, fields_path=args.fields)
    except (OSError, ValueError, RecursionError, SchemaError):
        print("Input rejected (path, encoding or JSON); no input content logged", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "mode": "format_only_not_freeze_ready" if args.format_only else "readiness",
                "passed": not errors,
                "summary": summary,
                "errors": errors,
            },
            indent=2,
        )
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
