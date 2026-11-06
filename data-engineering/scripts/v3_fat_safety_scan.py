"""List the recipes whose steps use butter, ghee, lard or bacon fat their ingredient list lacks (issue #426 B).

    python scripts/v3_fat_safety_scan.py [--release DIR]   # prints recipe_id, origin, course, kind, title

Owner rule (2026-11-04): the steps say butter / buttered / ghee, or lard / bacon fat / bacon grease (drippings too),
the list has no line with that fat, and for butter or ghee the recipe is not labelled milk (or is labelled
dairy-free). Each hit is then read by a person. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v3"
NUT = r"(?<!peanut )(?<!apple )(?<!almond )(?<!nut )(?<!cocoa )(?<!cashew )(?<!seed )"
BUTTER = re.compile(rf"{NUT}\b(?:butter|buttered|ghee)\b", re.I)
LARD = re.compile(r"\blard\b|\bbacon (?:fat|grease|drippings)\b", re.I)
LISTED = {"butter": BUTTER, "lard": re.compile(r"\blard\b|\bbacon\b", re.I)}


def hits(recipe: dict) -> list[str]:
    steps = " ".join(step["text"] for step in recipe["instructions"])
    listed = " ".join(f"{line['original_text']} {line['canonical_name']}" for line in recipe["ingredients"])
    dairy_free = "dairy-free" in recipe["dietary_tags"]
    found = []
    if BUTTER.search(steps) and not LISTED["butter"].search(listed):
        if "milk" not in recipe["allergens"] or dairy_free:
            found.append("butter")
    if LARD.search(steps) and not LISTED["lard"].search(listed):
        found.append("lard")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", type=Path, default=RELEASE)
    args = parser.parse_args()
    v22 = {
        json.loads(line)["recipe_id"]
        for line in (args.release.parent / "v2.2" / "recipes.jsonl").open(encoding="utf-8")
    }
    for line in (args.release / "recipes.jsonl").open(encoding="utf-8"):
        recipe = json.loads(line)
        for kind in hits(recipe):
            origin = "v2.2" if recipe["recipe_id"] in v22 else "added"
            print(recipe["recipe_id"], origin, recipe["course"], kind, recipe["title"], sep="\t")


if __name__ == "__main__":
    main()
