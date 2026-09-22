"""Draw and record the owner's fixed-seed audit of release course labels (ADR-0036 section 7, ADR-0038).

A recipe's course decides which dish role of a meal it may fill, so an
agent-enriched course label is checked on a sample before multi-dish meals are
switched on: ten recipes from each course a meal role admits.

    python scripts/course_audit.py draw            # data/review/course/audit-sample.json
    python scripts/course_audit.py record FILE     # docs/course-v2.1-sampled-audit.json

A verdict line is {"recipe_id", "verdict": accepted|corrected, "course", "note"}:
`course` is the label the reviewer judges right, and is required when corrected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.1" / "recipes.jsonl"
SAMPLE = ROOT / "data" / "review" / "course" / "audit-sample.json"  # redrawable from the seed, so not committed
RESULT = ROOT / "docs" / "course-v2.1-sampled-audit.json"  # the owner's judgement, committed
SEED = 20260924
PER_COURSE = 10
ROLE_COURSES = ("main", "side", "salad", "soup", "breakfast", "dessert", "snack_appetizer", "baked_good")
ALL_COURSES = (*ROLE_COURSES, "sauce_condiment", "drink")


def _rank(recipe_id: str) -> str:
    return hashlib.sha256(f"{SEED}:{recipe_id}".encode()).hexdigest()


def draw() -> None:
    records = [json.loads(line) for line in RELEASE.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = []
    for course in ROLE_COURSES:
        pool = sorted((r for r in records if r["course"] == course), key=lambda r: _rank(r["recipe_id"]))
        for record in pool[:PER_COURSE]:
            items.append(
                {
                    "recipe_id": record["recipe_id"],
                    "course": record["course"],
                    "title": record["title"],
                    "cuisine": record["cuisine"],
                    "meal_types": record["meal_types"],
                    "servings": record["servings"],
                    "course_evidence": record["enrichment"].get("evidence", {}).get("course"),
                    "course_confidence": record["enrichment"].get("confidence", {}).get("course"),
                    "ingredients": [line["original_text"] for line in record["ingredients"]],
                    "instructions": [step["text"] if isinstance(step, dict) else step for step in record["instructions"]],
                }
            )
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seed": SEED, "per_course": PER_COURSE, "courses": list(ALL_COURSES), "items": items}
    SAMPLE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} recipes sampled into {SAMPLE}: {dict(Counter(i['course'] for i in items))}")


def record(path: Path) -> None:
    sheet = json.loads(SAMPLE.read_text(encoding="utf-8"))
    labelled = {item["recipe_id"]: item["course"] for item in sheet["items"]}
    verdicts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = [
        v
        for v in verdicts
        if v.get("recipe_id") not in labelled
        or v.get("verdict") not in {"accepted", "corrected"}
        or (v["verdict"] == "corrected" and v.get("course") not in ALL_COURSES)
    ]
    if bad:
        sys.exit(f"verdicts outside the sample, with an unknown verdict, or a correction without a course: {bad[:3]}")
    by_course: dict[str, dict[str, int]] = {}
    for verdict in verdicts:
        counts = by_course.setdefault(labelled[verdict["recipe_id"]], {"accepted": 0, "corrected": 0})
        counts[verdict["verdict"]] += 1
    corrections = Counter(
        f"{labelled[v['recipe_id']]}->{v['course']}" for v in verdicts if v["verdict"] == "corrected"
    )
    RESULT.write_text(
        json.dumps(
            {
                "seed": sheet["seed"],
                "reviewer": "owner",
                "release": "v2.1",
                "sampled": len(labelled),
                "verdicts_recorded": len(verdicts),
                "by_course": by_course,
                "corrections": dict(sorted(corrections.items())),
                "verdicts": sorted(verdicts, key=lambda v: v["recipe_id"]),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(verdicts)} verdicts recorded: {by_course}; written to {RESULT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("draw")
    commands.add_parser("record").add_argument("verdicts", type=Path)
    args = parser.parse_args()
    draw() if args.command == "draw" else record(args.verdicts)


if __name__ == "__main__":
    main()
