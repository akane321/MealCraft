"""Task A (part 2) of the enrichment work package: derive recipe-level dietary
tags from each recipe's ingredient list, using the per-ingredient dietary
origin classification built by build_dietary_origin.py.

Streaming: reads/writes recipes.jsonl one line at a time so it works at full
dataset scale within the project's RAM budget, same pattern as
scripts/run_full_dataset.py and scripts/cut_release.py.

Rules (from enrichment-work-package.md, task A):
    dairy-free  : no ingredient with food_group == "dairy", and no ingredient
                  carrying a "milk" allergen tag.
    gluten-free : no ingredient carrying a "gluten" allergen tag.
                  "gluten_candidate" does NOT count as gluten-free (conservative).
    vegetarian  : no ingredient of dietary_origin == "flesh".
                  dairy / eggs / honey (dietary_origin == "secretion") are allowed.
    vegan       : no ingredient of dietary_origin in {"flesh", "secretion"}.

Unknown-value handling (mirrors ADR-0024 section 3's allergen principle,
applied here to dietary tags even though tags themselves are not allergens):
a positive tag is asserted only when every ingredient in the recipe is
`normalization_status == "mapped"`. If any ingredient is `candidate` or
`unresolved`, its dietary origin is unknown, so no positive claim can be made
about vegetarian/vegan/dairy-free/gluten-free for that recipe -- the tag is
left off `dietary_tags`, and `dietary_tags_basis` records WHY (derived_false,
or unknown_ingredient) so a downstream consumer can tell "definitely not X"
apart from "we don't know". This is the same "absence excludes, it does not
admit" rule ADR-0024 states for allergens, applied for the same reason a
false-positive dietary claim is worse than a missed one.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN_CSV = ROOT / "config" / "ingredient_dietary_origin.csv"


def load_origin_table() -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    with ORIGIN_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            table[row["ingredient_id"]] = (row["food_group"], row["dietary_origin"])
    return table


def derive_tags(ingredients: list[dict], origin_table: dict[str, tuple[str, str]]) -> tuple[list[str], dict[str, str]]:
    basis: dict[str, str] = {}
    all_mapped = True
    has_dairy_food_group = False
    has_milk_allergen = False
    has_gluten_allergen = False
    has_flesh = False
    has_secretion = False

    for occ in ingredients:
        if occ.get("normalization_status") != "mapped":
            all_mapped = False
            continue
        cid = occ.get("canonical_ingredient_id")
        food_group, origin = origin_table.get(cid, (None, None))
        allergens = occ.get("allergens") or []
        if food_group == "dairy":
            has_dairy_food_group = True
        if "milk" in allergens:
            has_milk_allergen = True
        if "gluten" in allergens:
            has_gluten_allergen = True
        if origin == "flesh":
            has_flesh = True
        elif origin == "secretion":
            has_secretion = True
        elif origin is None and cid is not None:
            # Mapped ingredient with no origin row: config drift (a canonical
            # ingredient exists that build_dietary_origin.py doesn't know
            # about). Treat conservatively as unknown, not as plant.
            all_mapped = False

    tags: list[str] = []

    if not all_mapped:
        basis["dairy-free"] = "unknown_ingredient"
        basis["gluten-free"] = "unknown_ingredient"
        basis["vegetarian"] = "unknown_ingredient"
        basis["vegan"] = "unknown_ingredient"
        return tags, basis

    is_dairy_free = not has_dairy_food_group and not has_milk_allergen
    is_gluten_free = not has_gluten_allergen
    is_vegetarian = not has_flesh
    is_vegan = not has_flesh and not has_secretion

    if is_dairy_free:
        tags.append("dairy-free")
    basis["dairy-free"] = "derived_true" if is_dairy_free else "derived_false"

    if is_gluten_free:
        tags.append("gluten-free")
    basis["gluten-free"] = "derived_true" if is_gluten_free else "derived_false"

    if is_vegetarian:
        tags.append("vegetarian")
    basis["vegetarian"] = "derived_true" if is_vegetarian else "derived_false"

    if is_vegan:
        tags.append("vegan")
    basis["vegan"] = "derived_true" if is_vegan else "derived_false"

    return tags, basis


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: derive_dietary_tags.py <in_recipes.jsonl> <out_recipes.jsonl>", file=sys.stderr)
        raise SystemExit(2)
    in_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])

    origin_table = load_origin_table()

    counts = {"total": 0, "dairy-free": 0, "gluten-free": 0, "vegetarian": 0, "vegan": 0, "all_unknown": 0}
    with in_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            recipe = json.loads(line)
            tags, basis = derive_tags(recipe.get("ingredients", []), origin_table)
            recipe["dietary_tags"] = tags
            recipe["dietary_tags_basis"] = basis
            fout.write(json.dumps(recipe, ensure_ascii=False) + "\n")

            counts["total"] += 1
            for tag in tags:
                counts[tag] += 1
            if basis["vegan"] == "unknown_ingredient":
                counts["all_unknown"] += 1

    print(json.dumps(counts, indent=2))
    for tag in ("dairy-free", "gluten-free", "vegetarian", "vegan"):
        pct = 100.0 * counts[tag] / counts["total"] if counts["total"] else 0.0
        print(f"{tag}: {counts[tag]}/{counts['total']} ({pct:.2f}%)")
    unk_pct = 100.0 * counts["all_unknown"] / counts["total"] if counts["total"] else 0.0
    print(f"fully unknown (>=1 unmapped ingredient): {counts['all_unknown']}/{counts['total']} ({unk_pct:.2f}%)")


if __name__ == "__main__":
    main()
