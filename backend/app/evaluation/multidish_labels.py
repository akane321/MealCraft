"""Check each multi-dish episode's class against its pool, from catalog facts alone.

No system under test runs here. A feasible episode must admit at least one valid
meal: one eligible dish per required role, distinct, within the meal-time limit.
An infeasible one must admit none. This does not check budgets, which need the
exact solver; a budget label is only as sound as the author's margin, and the
report says so.

    python -m app.evaluation.multidish_labels FILE...
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path

from app.core.paths import repository_root
from app.evaluation.release_catalog import load_release_catalog
from app.evaluation.strict_success import load_tag_implications, meal_minutes, satisfied_tags


def valid_meal_exists(episode: dict) -> tuple[bool, dict[str, int]]:
    catalog = load_release_catalog()
    allergens = {row["normalized_name"]: set(row["allergens"]) for row in catalog.ingredients}
    implications = load_tag_implications(repository_root() / "data/recipes/dietary-tag-implications.json")
    gold = episode["gold"]["applicable_hard_constraints"]
    pool = [catalog.by_slug[slug] for slug in episode["scenario"]["recipe_candidate_slugs"]]

    def eligible(recipe: dict) -> bool:
        names = {line["ingredient"] for line in recipe["ingredients"]}
        if any(set(gold["allergens_absent"]) & allergens.get(name, {"unchecked"}) for name in names):
            return False
        if names & set(gold["excluded_ingredients_absent"]):
            return False
        return set(gold["dietary_tags_required"]) <= satisfied_tags(recipe["dietary_tags"], implications)

    roles = episode["scenario"]["household_profile"]["meal_composition"]
    per_role = {r["role_id"]: [x for x in pool if x["course"] in r["courses"] and eligible(x)] for r in roles}
    limit = gold["max_cooking_time_minutes"]
    required = [r for r in roles if r["required"]]
    optional = [r for r in roles if not r["required"]]
    for chosen in (required + optional, required):
        for meal in product(*[per_role[r["role_id"]] for r in chosen]):
            if len({dish["slug"] for dish in meal}) == len(meal) and (
                limit is None or meal_minutes(list(meal)) <= limit
            ):
                return True, {k: len(v) for k, v in per_role.items()}
    return False, {k: len(v) for k, v in per_role.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    wrong = []
    for path in parser.parse_args().files:
        episode = json.loads(path.read_text(encoding="utf-8"))
        exists, counts = valid_meal_exists(episode)
        label = episode["gold"]["class"]
        print(f"{episode['episode_id']}: {label}; eligible per role {counts}; a valid meal exists: {exists}")
        if (label == "feasible" and not exists) or (
            label == "infeasible" and exists and not episode["gold"]["applicable_hard_constraints"].get("budget_sgd")
        ):
            wrong.append(episode["episode_id"])
    if wrong:
        print("labels the catalog contradicts: " + ", ".join(wrong))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
