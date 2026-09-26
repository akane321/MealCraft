"""Draw each multi-dish episode's candidate pool (protocol v2-multidish section 2, v3-meal-day-week).

The pool is drawn, not chosen: a fixed number of eligible release recipes for
every course the household's composition admits (for a v3 episode, every
course any planned meal or its shape change admits), from a seed derived from the
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

from app.data.alternatives import options as alternative_options
from app.evaluation.release_catalog import fixture_products, load_release_catalog

PER_COURSE = 12
POOL_VERSION = "multidish-pool-v1"


def course_uses(episode: dict) -> dict[str, int]:
    """Dish roles a week asks of each course: one per role per day.

    A protocol v3-meal-day-week episode plans several meals (`plan_shape`), and its
    shape change may add roles; both count. A v2-multidish episode's dinner
    composition counts as seven.
    """
    profile = episode["scenario"]["household_profile"]
    shape = profile.get("plan_shape")
    meals = list(shape["meals"].values()) if shape else [profile["meal_composition"]]
    change = (episode["gold"].get("replan_invariants") or {}).get("shape_change")
    if change and change.get("roles"):
        meals.append(change["roles"])
    uses: dict[str, int] = {}
    for roles in meals:
        for role in roles:
            for course in role["courses"]:
                uses[course] = uses.get(course, 0) + 7
    return uses


def draw(episode: dict) -> tuple[list[str], list[str]]:
    catalog = load_release_catalog()
    uses = course_uses(episode)
    week_shape = "plan_shape" in episode["scenario"]["household_profile"]
    seed = int(hashlib.sha256(f"{POOL_VERSION}:{episode['episode_id']}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    slugs: list[str] = []
    for course in sorted(uses):
        eligible = sorted(r["slug"] for r in catalog.recipes if r["course"] == course)
        # Several meals a day ask more of a course than seven dinners: twice its role-days, so a week
        # without repeats is still a choice (v3-meal-day-week). A v2 pool keeps its fixed size.
        size = max(PER_COURSE, 2 * uses[course]) if week_shape else PER_COURSE
        slugs += rng.sample(eligible, min(size, len(eligible)))
    # A dish the household asks for by name is in the pool: the request is the fact, not a choice of pool.
    rules = episode["gold"]["applicable_hard_constraints"].get("repetition_requirements") or {}
    slugs += [
        c["recipe_id"]
        for c in rules.get("recipe_counts") or []
        if c.get("min_uses") and c["recipe_id"] in catalog.by_slug and c["recipe_id"] not in slugs
    ]
    ingredients = {line["ingredient"] for slug in slugs for line in catalog.by_slug[slug]["ingredients"]}
    # A v3 episode plans through the product, which prices a curated ingredient from the fixture file
    # first and buys one option of an "A or B" line (data/ingredients/alternatives.json).
    priced = catalog.products
    if week_shape:
        priced = priced + fixture_products()
        ingredients |= {option for name in ingredients for option in alternative_options().get(name, ())}
    products = sorted(p["external_id"] for p in priced if p["ingredient_id"] in ingredients)
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
