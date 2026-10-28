"""Create and summarize human review tables for baseline ingredient mappings.

The tool consumes existing baseline-comparison JSON.  It never invokes a model
or changes the mapping algorithm.  Review tables are JSONL so blank human
fields remain JSON nulls rather than ambiguous empty strings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.paths import repository_root
from app.evaluation.release_catalog import load_release_catalog

SCHEMA_VERSION = "baseline-mapping-review-v1"
REPORT_SCHEMA_VERSION = "baseline-mapping-accuracy-v1"
DEFAULT_SEED = 364
DEFAULT_MATCHED_SAMPLE = 200
MAPPING_STATUSES = {"matched", "needs_review", "unmatched"}
DECISIONS = {"correct", "incorrect"}
SAFETY_ERROR_TYPES = {"allergen_omission", "false_allergen_assignment"}


def _stable_id(source: dict[str, Any], occurrence: int) -> str:
    identity = {
        "system_id": source["system_id"],
        "episode_id": source.get("episode_id"),
        "run_id": source.get("run_id"),
        "occurrence": occurrence,
        "original_ingredient_text": source["original_ingredient_text"],
        "quantity_g": source["quantity_g"],
        "mapped_ingredient_id": source.get("mapped_ingredient_id"),
        "mapping_status": source["mapping_status"],
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "map-" + hashlib.sha256(encoded).hexdigest()[:20]


def _completed_results(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    schema = payload.get("schema_version")
    if schema == "baseline-comparison-raw-v1":
        if payload.get("status") != "completed" or not isinstance(payload.get("result"), dict):
            raise ValueError("raw baseline output must have status=completed and a result object")
        result = payload["result"]
        yield {
            "system_id": result.get("system_id"),
            "episode_id": result.get("episode_id"),
            "run_id": f"repeat-{int(payload.get('repeat', 1)):03d}",
            "result": result,
        }
        return
    if schema == "baseline-comparison-v1":
        runs = payload.get("runs")
        if not isinstance(runs, list):
            raise ValueError("comparison output must contain a runs array")
        for run in runs:
            if isinstance(run, dict) and run.get("status") == "completed":
                yield {
                    "system_id": run.get("system_id"),
                    "episode_id": run.get("episode_id"),
                    "run_id": f"repeat-{int(run.get('repeat', 1)):03d}",
                    "result": run,
                }
        return
    raise ValueError(f"unsupported baseline output schema: {schema!r}")


def _source_rows(payload: dict[str, Any], names: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    occurrences: Counter[tuple[Any, ...]] = Counter()
    for run in _completed_results(payload):
        if not isinstance(run["system_id"], str) or not run["system_id"]:
            raise ValueError("completed baseline result is missing system_id")
        mappings = (run["result"].get("coverage") or {}).get("mappings")
        if not isinstance(mappings, list):
            raise ValueError("completed baseline result is missing coverage.mappings")
        for mapping in mappings:
            if not isinstance(mapping, dict) or mapping.get("status") not in MAPPING_STATUSES:
                raise ValueError("mapping row has an invalid status")
            original = mapping.get("original_name")
            quantity = mapping.get("quantity_g")
            if not isinstance(original, str) or not original or not isinstance(quantity, (int, float)) or quantity <= 0:
                raise ValueError("mapping row requires non-empty original_name and positive quantity_g")
            status = mapping["status"]
            ingredient_id = mapping.get("ingredient_id")
            suggestions = mapping.get("suggestions", [])
            if ingredient_id is not None and not isinstance(ingredient_id, str):
                raise ValueError("mapping ingredient_id must be a string or null")
            if not isinstance(suggestions, list) or not all(isinstance(item, str) for item in suggestions):
                raise ValueError("mapping suggestions must be an array of strings")
            key = (run["system_id"], run["episode_id"], run["run_id"], original, quantity, ingredient_id, status)
            occurrence = occurrences[key]
            occurrences[key] += 1
            base = {
                "system_id": run["system_id"],
                "episode_id": run["episode_id"],
                "run_id": run["run_id"],
                "original_ingredient_text": original,
                "quantity_g": float(quantity),
                "mapped_ingredient_id": ingredient_id,
                "mapped_ingredient_name": names.get(ingredient_id) if ingredient_id else None,
                "mapping_method": {"matched": "exact", "needs_review": "candidate_suggestion", "unmatched": "none"}[
                    status
                ],
                "mapping_status": status,
                "review_reason": {
                    "matched": "fixed_seed_matched_sample",
                    "needs_review": "mapping_requires_human_confirmation",
                    "unmatched": "no_mapping_candidate",
                }[status],
                "candidate_suggestions": [
                    {"ingredient_id": item, "ingredient_name": names.get(item)} for item in suggestions
                ],
            }
            rows.append({"row_id": _stable_id(base, occurrence), **base})
    return rows


def generate_review_rows(
    payload: dict[str, Any],
    *,
    names: dict[str, str],
    seed: int = DEFAULT_SEED,
    matched_sample_size: int = DEFAULT_MATCHED_SAMPLE,
) -> list[dict[str, Any]]:
    """Select every suspicious row and a reproducible matched-row sample."""
    if matched_sample_size < DEFAULT_MATCHED_SAMPLE:
        raise ValueError(f"matched sample size must be at least {DEFAULT_MATCHED_SAMPLE}")
    source = _source_rows(payload, names)
    suspicious = [row for row in source if row["mapping_status"] != "matched"]
    matched = [row for row in source if row["mapping_status"] == "matched"]
    sample_count = min(matched_sample_size, len(matched))
    sampled_ids = {row["row_id"] for row in random.Random(seed).sample(matched, sample_count)}
    selected = suspicious + [row for row in matched if row["row_id"] in sampled_ids]
    selected.sort(
        key=lambda row: (row["system_id"], row.get("episode_id") or "", row.get("run_id") or "", row["row_id"])
    )
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "source_mapping_row_count": len(source),
            "source_suspicious_row_count": len(suspicious),
            "sample_seed": seed,
            **row,
            "decision": None,
            "corrected_ingredient": None,
            "notes": None,
            "personally_reviewed": None,
            "safety_error": None,
            "safety_error_type": None,
        }
        for row in selected
    ]


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("Wilson inputs require 0 <= successes <= total")
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return (center - margin, center + margin)


def _validate_review_row(row: Any, line_number: int) -> dict[str, Any]:
    if not isinstance(row, dict) or row.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"line {line_number}: invalid review-table schema")
    required = {
        "row_id",
        "system_id",
        "original_ingredient_text",
        "quantity_g",
        "mapping_method",
        "mapping_status",
        "review_reason",
        "candidate_suggestions",
        "decision",
        "corrected_ingredient",
        "notes",
        "personally_reviewed",
        "safety_error",
        "safety_error_type",
        "source_mapping_row_count",
        "source_suspicious_row_count",
        "sample_seed",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"line {line_number}: missing fields: {', '.join(missing)}")
    if row["mapping_status"] not in MAPPING_STATUSES:
        raise ValueError(f"line {line_number}: invalid mapping_status")
    if row["personally_reviewed"] not in (None, True, False):
        raise ValueError(f"line {line_number}: personally_reviewed must be boolean or null")
    decision = row["decision"]
    if decision not in (None, *DECISIONS):
        raise ValueError(f"line {line_number}: decision must be correct, incorrect, or null")
    if row["personally_reviewed"] is True and decision is None:
        raise ValueError(f"line {line_number}: a reviewed row requires a decision")
    if row["personally_reviewed"] is not True and decision is not None:
        raise ValueError(f"line {line_number}: a decision requires personally_reviewed=true")
    if decision == "incorrect" and not isinstance(row["corrected_ingredient"], str):
        raise ValueError(f"line {line_number}: an incorrect mapping requires corrected_ingredient")
    if row["safety_error"] not in (None, True, False):
        raise ValueError(f"line {line_number}: safety_error must be boolean or null")
    if row["safety_error"] is True and row["safety_error_type"] not in SAFETY_ERROR_TYPES:
        raise ValueError(f"line {line_number}: safety_error_type is required for a safety error")
    if row["safety_error"] is True and (row["personally_reviewed"] is not True or decision != "incorrect"):
        raise ValueError(f"line {line_number}: a safety error requires a reviewed incorrect decision")
    if row["safety_error"] is not True and row["safety_error_type"] is not None:
        raise ValueError(f"line {line_number}: safety_error_type requires safety_error=true")
    return row


def read_review_table(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {line_number}: invalid JSON: {error.msg}") from error
        row = _validate_review_row(row, line_number)
        if row["row_id"] in seen:
            raise ValueError(f"line {line_number}: duplicate row_id {row['row_id']!r}")
        seen.add(row["row_id"])
        rows.append(row)
    if not rows:
        raise ValueError("review table is empty")
    return rows


def accuracy_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = {row["source_mapping_row_count"] for row in rows}
    suspicious_counts = {row["source_suspicious_row_count"] for row in rows}
    if len(source_counts) != 1 or len(suspicious_counts) != 1:
        raise ValueError("review rows disagree on source mapping counts")
    source_count = source_counts.pop()
    source_suspicious_count = suspicious_counts.pop()
    if not isinstance(source_count, int) or source_count < len(rows):
        raise ValueError("source_mapping_row_count is invalid")
    if not isinstance(source_suspicious_count, int) or not 0 <= source_suspicious_count <= source_count:
        raise ValueError("source_suspicious_row_count is invalid")

    def group(status: str) -> dict[str, Any]:
        selected = [row for row in rows if (row["mapping_status"] == "matched") is (status == "ordinary_matched")]
        reviewed = [row for row in selected if row["personally_reviewed"] is True]
        correct = sum(row["decision"] == "correct" for row in reviewed)
        interval = wilson_interval(correct, len(reviewed))
        return {
            "correct": correct,
            "denominator": len(reviewed),
            "accuracy": correct / len(reviewed) if reviewed else None,
            "wilson_95": list(interval) if interval else None,
            "unreviewed_excluded": len(selected) - len(reviewed),
        }

    reviewed = [row for row in rows if row["personally_reviewed"] is True]
    unreviewed = [row for row in rows if row["personally_reviewed"] is None]
    invalid = sum(row["personally_reviewed"] is False for row in rows)
    suspicious = [row for row in rows if row["mapping_status"] != "matched"]
    corrected = [row for row in reviewed if row["decision"] == "incorrect" and row["corrected_ingredient"]]
    safety = [row for row in reviewed if row["safety_error"] is True]
    unmatched = [row for row in rows if row["mapping_status"] == "unmatched"]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "table_rows": len(rows),
        "counts": {"reviewed": len(reviewed), "unreviewed": len(unreviewed), "invalid": invalid},
        "accuracy": {"ordinary_matched": group("ordinary_matched"), "suspicious": group("suspicious")},
        "suspicious": {
            "count": source_suspicious_count,
            "denominator": source_count,
            "proportion": source_suspicious_count / source_count,
            "review_table_count": len(suspicious),
        },
        "corrected": {
            "count": len(corrected),
            "denominator": len(reviewed),
            "rate": len(corrected) / len(reviewed) if reviewed else None,
        },
        "unmatched": {
            "count": len(unmatched),
            "handling": "included in suspicious accuracy only when personally reviewed; unreviewed rows are excluded",
        },
        "safety_errors": {
            "count": len(safety),
            "allergen_omission": sum(row["safety_error_type"] == "allergen_omission" for row in safety),
            "false_allergen_assignment": sum(row["safety_error_type"] == "false_allergen_assignment" for row in safety),
            "row_ids": [row["row_id"] for row in safety],
        },
        "denominator_note": (
            "Accuracy denominators contain only rows with personally_reviewed=true and a valid human decision. "
            "Ordinary matched uses status=matched; suspicious combines needs_review and unmatched."
        ),
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="generate a blank human-review table")
    generate.add_argument("input", type=Path)
    generate.add_argument("output", type=Path)
    generate.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate.add_argument("--matched-sample-size", type=int, default=DEFAULT_MATCHED_SAMPLE)
    report = subparsers.add_parser("report", help="validate a review table and write its accuracy report")
    report.add_argument("input", type=Path)
    report.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "generate":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        release = load_release_catalog(repository_root())
        names = {row["normalized_name"]: row["display_name"] for row in release.ingredients}
        rows = generate_review_rows(payload, names=names, seed=args.seed, matched_sample_size=args.matched_sample_size)
        _write_jsonl(args.output, rows)
        print(f"review table: {len(rows)} rows written to {args.output}")
        return 0

    rows = read_review_table(args.input)
    result = accuracy_report(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"accuracy report: {len(rows)} rows read from {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
