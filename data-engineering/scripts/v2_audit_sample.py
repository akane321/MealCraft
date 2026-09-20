"""Draw and record the post-hoc sampled audit of enrichment results.

    python scripts/v2_audit_sample.py draw --recipes 40 --ingredients 20
    python scripts/v2_audit_sample.py record < verdicts.jsonl

`ADR-0024` section 2 admits AI enrichment on condition that it is audited by
sampling afterwards. This draws that sample deterministically from the part
outputs, writes a worksheet, and turns the filled-in verdicts into the numbers
the quality report quotes.

The sample is drawn from what has been enriched so far, so it can run before the
whole release is finished; the worksheet records which parts were included.

A verdict line is one JSON object:

    {"item_id": "recipenlg:123", "kind": "recipes", "verdict": "accepted",
     "checked": ["time", "servings", "course", "cuisine"], "note": ""}

`verdict` is `accepted` (every checked field defensible), `corrected` (at least
one field wrong enough to change a plan) or `unverifiable` (no source settles
it). `note` says what was wrong, in a few words.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "enrichment-work"
REVIEW = ROOT / "data" / "review"  # worksheet: bulky and redrawable from the seed, so not committed
AUDIT = ROOT / "docs" / "v2-sampled-audit.json"  # the verdicts are a human judgement, so they are committed
PARTS = ("A", "B", "C")
ID_FIELD = {"recipes": "candidate_id", "ingredients": "ingredient_id"}
DEFAULT_SEED = 20260920


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rank(item_id: str, seed: int) -> str:
    """A stable pseudo-random order: the same seed always draws the same sample."""
    return hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest()


def draw(n_recipes: int, n_ingredients: int, seed: int) -> int:
    sample: dict[str, list[dict]] = {}
    parts_seen: dict[str, list[str]] = {}
    for kind, want in (("recipes", n_recipes), ("ingredients", n_ingredients)):
        pool = []
        included = []
        for part in PARTS:
            folder = WORK / f"part-{part}"
            rows = read_jsonl(folder / f"{kind}.output.jsonl")
            if rows:
                included.append(part)
            inputs = {i[ID_FIELD[kind]]: i for i in read_jsonl(folder / f"{kind}.input.jsonl")}
            for row in rows:
                pool.append({"part": part, "item": row, "input": inputs.get(row[ID_FIELD[kind]], {})})
        chosen = sorted(pool, key=lambda row: rank(row["item"][ID_FIELD[kind]], seed))[:want]
        sample[kind] = chosen
        parts_seen[kind] = included
        print(f"{kind}: {len(pool)} enriched so far in parts {','.join(included) or '-'}, sampled {len(chosen)}")

    REVIEW.mkdir(parents=True, exist_ok=True)
    worksheet = {
        "seed": seed,
        "drawn_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "parts_included": parts_seen,
        "items": {
            kind: [
                {
                    "item_id": row["item"][ID_FIELD[kind]],
                    "part": row["part"],
                    "enriched_by": row["item"].get("enriched_by"),
                    "source_item": row["input"],
                    "result": row["item"],
                }
                for row in rows
            ]
            for kind, rows in sample.items()
        },
    }
    path = REVIEW / "v2_audit_worksheet.json"
    path.write_text(json.dumps(worksheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    print("Check each item against its source, then pipe verdict lines into: v2_audit_sample.py record")
    return 0


def record(verdicts: list[dict]) -> int:
    worksheet = json.loads((REVIEW / "v2_audit_worksheet.json").read_text(encoding="utf-8"))
    known = {kind: {i["item_id"] for i in items} for kind, items in worksheet["items"].items()}
    results: dict[str, collections.Counter] = {kind: collections.Counter() for kind in known}
    findings: list[str] = []
    unknown = 0
    for verdict in verdicts:
        kind = verdict.get("kind")
        if kind not in known or verdict.get("item_id") not in known[kind]:
            unknown += 1
            continue
        results[kind][verdict.get("verdict", "unverifiable")] += 1
        results[kind]["checks"] += len(verdict.get("checked") or [])
        if verdict.get("note"):
            findings.append(f"{verdict['item_id']}: {verdict['note']}")
    if unknown:
        print(f"ignored {unknown} verdict lines for items outside the drawn sample")

    audit = {
        "seed": worksheet["seed"],
        "drawn_at": worksheet["drawn_at"],
        "audited_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "parts_included": worksheet["parts_included"],
        "results": {
            kind: {
                "sampled": len(known[kind]),
                "verdicts_recorded": sum(v for k, v in counts.items() if k != "checks"),
                "checks": counts["checks"],
                "accepted": counts["accepted"],
                "corrected": counts["corrected"],
                "unverifiable": counts["unverifiable"],
            }
            for kind, counts in results.items()
        },
        "findings": findings,
    }
    path = AUDIT
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    for kind, result in audit["results"].items():
        print(f"{kind}: {result['accepted']} accepted, {result['corrected']} corrected of {result['sampled']} sampled")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    drawer = sub.add_parser("draw")
    drawer.add_argument("--recipes", type=int, default=40)
    drawer.add_argument("--ingredients", type=int, default=20)
    drawer.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sub.add_parser("record")
    args = parser.parse_args()
    if args.command == "draw":
        return draw(args.recipes, args.ingredients, args.seed)
    import sys

    return record([json.loads(line) for line in sys.stdin.read().splitlines() if line.strip()])


if __name__ == "__main__":
    raise SystemExit(main())
