"""Order the ingredient review queue by how many recipes each decision unlocks.

The pipeline orders its queue by problem type, so the first rows are
`empty_after_parsing` - fragments like "1 cup" with no ingredient name at all.
Those are the least useful thing a reviewer can spend attention on: resolving one
fixes one line in one recipe, and usually the answer is "this is junk".

A recipe is only usable when *every* ingredient in it resolves. So the question
worth asking is not "which row looks worst" but "which decision unblocks the most
recipes". This orders by that, greedily: repeatedly take the unresolved
ingredient blocking the most otherwise-ready recipes.

Run from the data-engineering directory:

    python build_priority_queue.py

Writes `data/review/ingredient_priority_queue.csv` and prints the payoff curve,
so the reviewer can see what stopping early costs.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd()
RECIPES = ROOT / "data" / "curated" / "recipes.jsonl"
INGREDIENTS = ROOT / "data" / "curated" / "ingredients.jsonl"
OUT = ROOT / "data" / "review" / "ingredient_priority_queue.csv"

USABLE_UNITS = {"g", "kg", "oz", "lb", "ml", "l", "cup", "tbsp", "tsp", "whole", "piece"}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def blockers(recipe: dict) -> set[str] | None:
    """Unresolved canonical ids in a recipe, or None when it can never be usable.

    A recipe with a missing quantity or an unconvertible unit cannot be rescued by
    resolving an ingredient name, so it should not inflate any candidate's score.
    """
    unresolved: set[str] = set()
    for item in recipe["ingredients"]:
        if item.get("quantity_min") is None:
            return None
        if (item.get("unit_normalized") or "").lower() not in USABLE_UNITS:
            return None
        if item["normalization_status"] != "mapped":
            unresolved.add(item["canonical_ingredient_id"])
    return unresolved


def main() -> int:
    recipes = load_jsonl(RECIPES)
    ingredients = {row["ingredient_id"]: row for row in load_jsonl(INGREDIENTS)}

    rescuable = [(r, b) for r in recipes if (b := blockers(r)) is not None]
    ready_now = sum(1 for _, b in rescuable if not b)

    remaining = {id(r): (r, set(b)) for r, b in rescuable if b}
    occurrences = Counter(
        item["canonical_ingredient_id"]
        for r in recipes
        for item in r["ingredients"]
        if item["normalization_status"] != "mapped"
    )

    order: list[tuple[str, int, int]] = []
    unlocked_total = ready_now
    while remaining:
        blocking = Counter()
        for _, (_, pending) in remaining.items():
            for candidate in pending:
                blocking[candidate] += 1
        if not blocking:
            break
        # Ties break on total occurrences, then id, so the queue is reproducible.
        best = max(blocking, key=lambda c: (blocking[c], occurrences[c], c))
        for key in list(remaining):
            _, pending = remaining[key]
            pending.discard(best)
            if not pending:
                unlocked_total += 1
                del remaining[key]
        order.append((best, blocking[best], unlocked_total))

    samples: dict[str, list[str]] = defaultdict(list)
    for r in recipes:
        for item in r["ingredients"]:
            cid = item["canonical_ingredient_id"]
            if item["normalization_status"] != "mapped" and len(samples[cid]) < 3:
                samples[cid].append(item["original_text"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "ingredient_id",
                "parsed_name",
                "recipes_blocked",
                "recipes_usable_after_this_row",
                "occurrences",
                "example_texts",
                "review_decision",
                "reviewed_canonical_name",
                "reviewer_notes",
            ]
        )
        for rank, (cid, blocked, cumulative) in enumerate(order, start=1):
            row = ingredients.get(cid, {})
            writer.writerow(
                [
                    rank,
                    cid,
                    row.get("canonical_name", ""),
                    blocked,
                    cumulative,
                    occurrences[cid],
                    " | ".join(samples.get(cid, [])),
                    "",
                    "",
                    "",
                ]
            )

    print(f"Recipes that survive quantity and unit checks: {len(rescuable)} of {len(recipes)}")
    print(f"Usable with no review at all:                  {ready_now}")
    print(f"Unresolved ingredients in the queue:           {len(order)}")
    print()
    print("Payoff of reviewing the top N rows:")
    for n in (50, 100, 200, 300, 400, 600):
        if n <= len(order):
            print(f"  top {n:>4}  ->  {order[n - 1][2]:>5} usable recipes")
    if order:
        print(f"  all {len(order):>4}  ->  {order[-1][2]:>5} usable recipes")
    print()
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
