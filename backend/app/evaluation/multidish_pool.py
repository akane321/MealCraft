"""Draw each multi-dish episode's candidate pool (protocol v2-multidish section 2).

The pool is drawn, not chosen: a fixed number of eligible release recipes for
every course the household's composition admits, from a seed derived from the
episode id. It contains dishes that break the episode's constraints, so
filtering is part of the task. An author who chose the pool would know the
answer.

    python -m app.evaluation.multidish_pool FILE...          # write the pools into the episodes
    python -m app.evaluation.multidish_pool --check FILE...  # fail if a pool was edited by hand
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from app.evaluation.release_catalog import load_release_catalog

PER_COURSE = 12
POOL_VERSION = "multidish-pool-v1"


def draw(episode: dict) -> tuple[list[str], list[str]]:
    catalog = load_release_catalog()
    composition = episode["scenario"]["household_profile"]["meal_composition"]
    courses = sorted({course for role in composition for course in role["courses"]})
    seed = int(hashlib.sha256(f"{POOL_VERSION}:{episode['episode_id']}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    slugs: list[str] = []
    for course in courses:
        eligible = sorted(r["slug"] for r in catalog.recipes if r["course"] == course)
        slugs += rng.sample(eligible, min(PER_COURSE, len(eligible)))
    # A dish the household asks for by name is in the pool: the request is the fact, not a choice of pool.
    rules = episode["gold"]["applicable_hard_constraints"].get("repetition_requirements") or {}
    slugs += [
        c["recipe_id"]
        for c in rules.get("recipe_counts") or []
        if c.get("min_uses") and c["recipe_id"] in catalog.by_slug and c["recipe_id"] not in slugs
    ]
    ingredients = {line["ingredient"] for slug in slugs for line in catalog.by_slug[slug]["ingredients"]}
    products = sorted(p["external_id"] for p in catalog.products if p["ingredient_id"] in ingredients)
    return sorted(slugs), products


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    stale = []
    for path in args.files:
        episode = json.loads(path.read_text(encoding="utf-8"))
        slugs, products = draw(episode)
        scenario = episode["scenario"]
        if args.check:
            if scenario.get("recipe_candidate_slugs") != slugs or scenario.get("fairprice_product_ids") != products:
                stale.append(str(path))
            continue
        scenario["recipe_candidate_slugs"], scenario["fairprice_product_ids"] = slugs, products
        path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if stale:
        print("candidate pools differ from the draw:\n  " + "\n  ".join(stale))
        return 1
    print(f"{len(args.files)} episode pools {'checked' if args.check else 'drawn'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
