"""Score tutorial Top-1 policies against labelled, frozen YouTube candidates.

    PYTHONPATH=backend python scripts/evaluate_tutorial_ranking.py [REVIEWER] [--heldout]

Developer dishes by default. `--heldout` reads the held-out dishes: run it once, on final labels,
after the policy is frozen, and never tune on what it prints.

A policy returns one video or none. For each dish: good (label 2), weak (1), wrong (0), or none.
None is right when the pool holds no 2 (an unavailable state beats an irrelevant video), a miss otherwise.
"""

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.retrieval.tutorials import TutorialCandidate, rank_tutorial_candidates

ROOT = Path("data/evaluation/tutorials")
Policy = Callable[[dict], str | None]


def pool(dish: dict, form: str) -> list[TutorialCandidate]:
    """The candidates one query form returned, in YouTube's order."""
    found = [c for c in dish["candidates"] if form in c["ranks"]]
    found.sort(key=lambda c: c["ranks"][form])
    return [
        TutorialCandidate(
            **{k: c[k] for k in TutorialCandidate.model_fields if k in c},
            source="youtube",
            fetched_at=datetime.now(UTC),
        )
        for c in found
    ]


def shipped(form: str) -> Policy:
    def choose(dish: dict) -> str | None:
        ranked = rank_tutorial_candidates(
            recipe_title=dish["title"],
            cuisine=dish["cuisine"],
            ingredient_names=dish["ingredients"],
            language="en",
            candidates=pool(dish, form),
        )
        return ranked[0][2].video_id if ranked else None

    return choose


# Measured before ranking v2 replaced the ranker, on the developer dishes with Codex's labels:
#   v1 query + v1 ranking (shipped until v2)   good 5  weak 7  wrong 1  none ok 2  missed 5
#   title query + v1 ranking                   good 10 weak 8  wrong 0  none ok 1  missed 1
POLICIES: dict[str, Policy] = {
    "v1 query + v2 ranking": shipped("v1"),
    "title query + v2 ranking (shipped)": shipped("title"),
}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    split = "heldout" if "--heldout" in sys.argv else "developer"
    reviewer = args[0] if args else "codex"
    labels = json.loads((ROOT / "labels-v1" / f"{reviewer}.json").read_text(encoding="utf-8"))["labels"]
    dishes = [
        d
        for d in json.loads((ROOT / "candidates-v1.json").read_text(encoding="utf-8"))["dishes"]
        if d["split"] == split
    ]
    has_good = sum(1 for d in dishes if 2 in labels.get(d["recipe_id"], {}).values())
    print(f"{split}: {len(dishes)} dishes, labels by {reviewer}; a 2 exists in the pool for {has_good}\n")
    print(f"{'policy':38} {'good':>5} {'weak':>5} {'wrong':>6} {'none ok':>8} {'missed':>7}")
    for name, policy in POLICIES.items():
        tally = {"good": 0, "weak": 0, "wrong": 0, "none ok": 0, "missed": 0}
        for dish in dishes:
            dish_labels = labels.get(dish["recipe_id"], {})
            chosen = policy(dish)
            if chosen is None:
                tally["missed" if 2 in dish_labels.values() else "none ok"] += 1
            else:
                tally[{2: "good", 1: "weak", 0: "wrong"}[dish_labels[chosen]]] += 1
        print(f"{name:38} " + " ".join(f"{tally[k]:>{w}}" for k, w in zip(tally, (5, 5, 6, 8, 7), strict=True)))


if __name__ == "__main__":
    main()
