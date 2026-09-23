"""Check the ingredient hierarchy, and help whoever is writing it.

Three people write the hierarchy in parallel, one package file each, so the rules
that make it safe have to be checked by a program rather than remembered. The
contract is `docs/design/ingredient-hierarchy.md`.

Standard library only, and no container: run it after every batch you write.

    python scripts/check_ingredient_hierarchy.py                           # errors + progress
    python scripts/check_ingredient_hierarchy.py --require-complete WP2    # also: every WP2 id decided
    python scripts/check_ingredient_hierarchy.py --next WP2 --count 40     # the next ids to decide
    python scripts/check_ingredient_hierarchy.py --show bacon              # evidence for one id
    python scripts/check_ingredient_hierarchy.py --expand pork group:alcohol  # what an exclusion removes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data.ingredient_hierarchy import FILES, empty_groups, load, look_alikes  # noqa: E402


def _recipe_lines(ingredient_id: str, limit: int) -> list[str]:
    """How recipes actually write this ingredient: the evidence a decision should rest on."""
    lines: list[str] = []
    release = ROOT / "data-engineering/data/release/v2.1/recipes.jsonl"
    for raw in release.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        recipe = json.loads(raw)
        for row in recipe["ingredients"]:
            if row["canonical_ingredient_id"][4:].lower() == ingredient_id:
                lines.append(f"{row['original_text']}   <- {recipe['title'][:50]}")
        if len(lines) >= limit:
            return lines[:limit]
    for recipe in json.loads((ROOT / "data/recipes/recipes.json").read_text(encoding="utf-8")):
        for row in recipe["ingredients"]:
            if row["ingredient"] == ingredient_id:
                lines.append(f"{row['quantity']} {row['unit']} {ingredient_id}   <- {recipe['title']} (curated)")
    return lines[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require-complete", choices=sorted(FILES), action="append", default=[])
    parser.add_argument("--next", choices=sorted(FILES))
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--show")
    parser.add_argument("--expand", nargs="+")
    args = parser.parse_args()
    hierarchy = load(ROOT)

    if args.show:
        ingredient = hierarchy.ingredients.get(args.show)
        if ingredient is None:
            print(f"{args.show}: not an ingredient id")
            return 1
        print(f"{ingredient.id}: {ingredient.name!r}, food group {ingredient.food_group}, owner {ingredient.package}")
        print(f"used by {ingredient.occurrences} recipes; decided: {args.show in hierarchy.entries}")
        if args.show in hierarchy.entries:
            print(json.dumps(hierarchy.entries[args.show], ensure_ascii=False, indent=2))
        print("name contains:", ", ".join(look_alikes(args.show, hierarchy.ingredients)) or "-")
        print("belongs to it now:", ", ".join(sorted(hierarchy.expand([args.show]) - {args.show})) or "-")
        print("how recipes write it:")
        for line in _recipe_lines(args.show, 8):
            print("  " + line)
        return 0

    if args.expand:
        unknown = [i for i in args.expand if i not in hierarchy.ingredients and i not in hierarchy.groups]
        if unknown:
            print("unknown ids: " + ", ".join(unknown))
            return 1
        removed = sorted(hierarchy.expand(args.expand) - set(args.expand))
        uses = sum(hierarchy.ingredients[i].occurrences for i in removed if i in hierarchy.ingredients)
        print(f"excluding {', '.join(args.expand)} also excludes {len(removed)} ids ({uses} recipe uses):")
        for ingredient_id in removed:
            print(f"  {ingredient_id}")
        return 0

    if args.next:
        pending = hierarchy.undecided(args.next)
        print(f"{args.next}: {len(pending)} undecided; next {min(args.count, len(pending))}:")
        for ingredient_id in pending[: args.count]:
            ingredient = hierarchy.ingredients[ingredient_id]
            alike = look_alikes(ingredient_id, hierarchy.ingredients)
            print(
                f"  {ingredient_id:28} {ingredient.name!r:32} {ingredient.food_group or 'curated':10} "
                f"{ingredient.occurrences:5} recipes" + (f"   contains: {', '.join(alike)}" if alike else "")
            )
        return 0

    errors = list(hierarchy.errors)
    for package in args.require_complete:
        pending = hierarchy.undecided(package)
        if pending:
            errors.append(f"{package}: {len(pending)} ids undecided, e.g. {', '.join(pending[:5])}")
    if args.require_complete and sorted(args.require_complete) == sorted(FILES):
        errors += [f"group {g} is declared but nothing belongs to it" for g in empty_groups(hierarchy)]
    for error in errors:
        print("error: " + error)
    relations = Counter(p["relation"] for e in hierarchy.entries.values() for p in e.get("parents", []))
    for package in sorted(FILES):
        owned = hierarchy.owned(package)
        print(f"{package} ({FILES[package]}): {len(owned) - len(hierarchy.undecided(package))}/{len(owned)} decided")
    print(f"groups: {len(hierarchy.groups)}; links: {dict(relations) or '-'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
