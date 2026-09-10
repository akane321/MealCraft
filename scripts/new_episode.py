"""Scaffold a held-out episode so authors spend their time on judgement.

The mechanical parts of an episode - a free id, the meal slots, a candidate
recipe pool, and the product ids that cover every ingredient in that pool - are
tedious and easy to get wrong, and getting them wrong means the packet cannot be
compiled later. Nothing here decides what the episode tests. Every field that
carries meaning is written as a `TODO:` placeholder, and
`scripts/check_heldout_episodes.py` refuses an episode that still contains one.

    python scripts/new_episode.py --category safety_diet --author retrieval --language zh

Standard library only, no container.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SET_DIR = ROOT / "data" / "evaluation" / "heldout" / "v2"
MANIFEST = SET_DIR / "set-manifest.json"
EPISODES = SET_DIR / "episodes"

RECIPES = ROOT / "data" / "recipes" / "recipes.json"
PRODUCTS = ROOT / "data" / "fixtures" / "fairprice-products.json"

TODO = "TODO: "
DEFAULT_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def next_episode_id(category: str) -> str:
    pattern = re.compile(rf"^ho-{re.escape(category)}-(\d+)$")
    used = set()
    if EPISODES.exists():
        for path in EPISODES.glob("*.json"):
            match = pattern.match(path.stem)
            if match:
                used.add(int(match.group(1)))
    number = 1
    while number in used:
        number += 1
    return f"ho-{category}-{number:03d}"


def eligible_authors(manifest: dict, category: str) -> list[str]:
    under_test = set(manifest["categories"][category]["systems_under_test"])
    return [role for role in manifest["roles"] if role not in under_test]


def choose_recipes(count: int, meal_type: str, seed: int | None) -> list[dict]:
    pool = [row for row in load(RECIPES) if row["meal_type"] == meal_type]
    if len(pool) < count:
        raise SystemExit(
            f"Only {len(pool)} '{meal_type}' recipes exist; asked for {count}. "
            "Lower --recipe-count or pick recipes explicitly with --recipes."
        )
    pool.sort(key=lambda row: row["slug"])
    random.Random(seed).shuffle(pool)
    return sorted(pool[:count], key=lambda row: row["slug"])


def named_recipes(slugs: list[str]) -> list[dict]:
    catalog = {row["slug"]: row for row in load(RECIPES)}
    unknown = [slug for slug in slugs if slug not in catalog]
    if unknown:
        raise SystemExit(f"Unknown recipe slug(s): {', '.join(unknown)}")
    return [catalog[slug] for slug in slugs]


def covering_products(recipes: list[dict]) -> tuple[list[str], list[str]]:
    """Every product that supplies an ingredient used by the candidate pool.

    The packet compiler requires full product coverage of the candidate
    ingredients, so an author who picks these by hand tends to discover the gap
    only when compilation fails.
    """
    needed = {item["ingredient"] for recipe in recipes for item in recipe["ingredients"]}
    chosen: list[str] = []
    supplied: set[str] = set()
    for product in sorted(load(PRODUCTS), key=lambda row: row["external_id"]):
        keys = set(product["ingredient_keys"])
        if keys & needed:
            chosen.append(product["external_id"])
            supplied |= keys & needed
    return chosen, sorted(needed - supplied)


def build(args, manifest: dict) -> dict:
    recipes = (
        named_recipes([slug.strip() for slug in args.recipes.split(",") if slug.strip()])
        if args.recipes
        else choose_recipes(args.recipe_count, args.meal_type, args.seed)
    )
    products, uncovered = covering_products(recipes)
    if uncovered:
        print(
            "Warning: no fixture product supplies "
            f"{', '.join(uncovered)}. The packet will not compile until the "
            "catalog covers them; choose different recipes or raise it with the "
            "dataset owner.",
            file=sys.stderr,
        )

    slots = [f"{day}-{args.meal_type if args.meal_type != 'main' else 'dinner'}" for day in DEFAULT_DAYS[: args.days]]

    return {
        "schema_version": "heldout-episode-v1",
        "episode_id": args.episode_id,
        "category": args.category,
        "language": args.language,
        "authored_by": args.author,
        "reviewed_by": None,
        "review_notes": None,
        "scenario": {
            "user_request": TODO + "the household's request, in their own words",
            "conversation_history": [],
            "household_profile": {
                "household_size": args.household_size,
                "allergens": [],
                "excluded_ingredients": [],
                "dietary_preferences": [],
            },
            "pantry": [],
            "planning_horizon": {"start_date": args.start_date, "slots": slots},
            "recipe_candidate_slugs": [row["slug"] for row in recipes],
            "fairprice_product_ids": products,
        },
        "gold": {
            "class": TODO + "feasible | needs_clarification | infeasible",
            "required_clarification_fields": [],
            "forbidden_clarification_fields": [],
            "applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": None,
                "nutrition_bands": [],
            },
            "pantry_ground_truth": {"deductible": [], "not_deductible_unknown_quantity": []},
            "conflict_reason": None,
            "allowed_relaxations": [],
            "required_disclosures": [],
            "replan_invariants": None,
            "author_rationale": TODO
            + "what would a plausible-looking wrong answer be here? If you cannot "
            "say, this episode is not testing anything - pick a different one",
        },
    }


def main() -> int:
    manifest = load(MANIFEST)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", required=True, choices=sorted(manifest["categories"]))
    parser.add_argument("--author", required=True, choices=manifest["roles"])
    parser.add_argument("--language", required=True, choices=["en", "zh", "mixed"])
    parser.add_argument("--episode-id", help="defaults to the next free id for the category")
    parser.add_argument("--recipes", help="comma-separated slugs; omit to draw a pool")
    parser.add_argument("--recipe-count", type=int, default=8)
    parser.add_argument("--meal-type", default="main", choices=["main", "breakfast"])
    parser.add_argument("--days", type=int, default=7, choices=range(1, 8))
    parser.add_argument("--household-size", type=int, default=2)
    parser.add_argument("--start-date", default="2026-09-07")
    parser.add_argument("--seed", type=int, help="fix the candidate draw for reproducibility")
    parser.add_argument("--dry-run", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    allowed = eligible_authors(manifest, args.category)
    if args.author not in allowed:
        under_test = manifest["categories"][args.category]["systems_under_test"]
        print(
            f"'{args.author}' owns a system that '{args.category}' evaluates "
            f"({', '.join(under_test)}), so it cannot author or review these episodes.\n"
            f"Eligible authors: {', '.join(allowed)}",
            file=sys.stderr,
        )
        return 1

    args.episode_id = args.episode_id or next_episode_id(args.category)
    episode = build(args, manifest)
    rendered = json.dumps(episode, ensure_ascii=False, indent=2) + "\n"

    if args.dry_run:
        print(rendered)
        return 0

    EPISODES.mkdir(parents=True, exist_ok=True)
    target = EPISODES / f"{args.episode_id}.json"
    if target.exists():
        print(f"{target.relative_to(ROOT)} already exists; refusing to overwrite.", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")

    print(f"Wrote {target.relative_to(ROOT).as_posix()}")
    print(
        f"  category {args.category}, author {args.author}, language {args.language}\n"
        f"  {len(episode['scenario']['recipe_candidate_slugs'])} candidate recipes, "
        f"{len(episode['scenario']['fairprice_product_ids'])} products covering their ingredients\n"
        "\nFill every TODO, starting with gold.author_rationale, then run:\n"
        "  python scripts/check_heldout_episodes.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
