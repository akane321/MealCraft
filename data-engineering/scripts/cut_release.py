"""Cut a versioned, release-eligible catalog slice from the full curated
dataset, per docs/schema-v1-freeze.md's four-condition gate:

    1. every ingredient row is normalization_status == "mapped"
    2. every ingredient row has quantity_min is not None
    3. every ingredient row's unit_normalized is in a physically anchored
       dimension (mass / volume / count - not "informal" or "package")
    4. the recipe has servings is not None (either basis)

Streams the (potentially multi-GB, multi-million-row) curated files line by
line - never materializes the full dataset - so this scales the same way
run_full_dataset.py's merge step does.

Run from the project root:

    python scripts/cut_release.py --version v1 --out-dir /path/to/mealcraft/data-engineering/data/release/v1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mealcraft_data.constants import SCHEMA_VERSION, TRANSFORMATION_VERSION  # noqa: E402
from mealcraft_data.utils import utc_now_iso, write_json  # noqa: E402

# "package" and "informal" units (can/jar/bottle/pinch/dash/...) cannot support
# package or shopping arithmetic without a separate, sourced size/weight
# lookup that does not exist yet - see schema-v1-freeze.md condition 3.
RELEASE_UNIT_DIMENSIONS = {"mass", "volume", "count"}


def is_release_eligible(recipe: dict) -> bool:
    if recipe.get("servings") is None:
        return False
    for item in recipe["ingredients"]:
        if item["normalization_status"] != "mapped":
            return False
        if item["quantity_min"] is None:
            return False
        if item.get("unit_dimension") not in RELEASE_UNIT_DIMENSIONS:
            return False
    return True


def git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="release version tag, e.g. v1")
    parser.add_argument("--recipes", type=Path, default=ROOT / "data/curated/recipes.jsonl")
    parser.add_argument("--ingredients", type=Path, default=ROOT / "data/curated/ingredients.jsonl")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, default=ROOT / "reports/run_manifest.json")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()

    total = 0
    eligible = 0
    referenced_ids: set[str] = set()
    servings_basis_counts: Counter[str] = Counter()
    dietary_tag_counts: Counter[str] = Counter()
    out_recipes = args.out_dir / "recipes.jsonl"
    with args.recipes.open("r", encoding="utf-8") as src, out_recipes.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            total += 1
            recipe = json.loads(line)
            if not is_release_eligible(recipe):
                continue
            eligible += 1
            servings_basis_counts[recipe["servings_basis"]] += 1
            for item in recipe["ingredients"]:
                referenced_ids.add(item["canonical_ingredient_id"])
            for tag in recipe.get("dietary_tags") or []:
                dietary_tag_counts[tag] += 1
            dst.write(line + "\n")
    print(f"scanned {total} recipes -> {eligible} release-eligible ({eligible / total * 100:.3f}%)")

    out_ingredients = args.out_dir / "ingredients.jsonl"
    kept_ingredients = 0
    with args.ingredients.open("r", encoding="utf-8") as src, out_ingredients.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record["ingredient_id"] in referenced_ids:
                dst.write(line + "\n")
                kept_ingredients += 1
    print(f"kept {kept_ingredients} / {len(referenced_ids)} referenced canonical ingredients")

    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    manifest = {
        "release_version": args.version,
        "created_at": utc_now_iso(),
        "schema_version": SCHEMA_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "pipeline_git_revision": git_revision(),
        "upstream_source": {
            "dataset": "RecipeNLG Gathered subset",
            "input_sha256": source_manifest.get("input_sha256"),
            "seed": source_manifest.get("seed"),
        },
        "release_gate": {
            "conditions": [
                "every ingredient normalization_status == 'mapped'",
                "every ingredient quantity_min is not None",
                "every ingredient unit_dimension in {mass, volume, count}",
                "recipe servings is not None",
            ],
            "definition_doc": "docs/schema-v1-freeze.md",
        },
        "counts": {
            "upstream_recipes_scanned": total,
            "released_recipes": eligible,
            "released_recipes_pct": round(eligible / total, 6) if total else 0.0,
            "released_ingredients": kept_ingredients,
            "servings_basis": dict(servings_basis_counts),
        },
        "known_gaps": [
            "nutrition.status is not_computed for every released recipe (no reviewed USDA "
            "mapping or quantity-to-mass conversion yet)",
            "allergen labels are deterministic-rule-only; no independently reviewed gold "
            "subset exists yet (see docs/schema-v1-freeze.md)",
            "cuisine/meal_types/methods/equipment/difficulty are empty for every released "
            "recipe; no controlled vocabulary exists yet",
            (
                "dietary_tags are absent for every released recipe; not computed by this pipeline"
                if not dietary_tag_counts
                else "dietary_tags (dairy-free/gluten-free/vegetarian/vegan) are derived "
                f"only, not independently reviewed: {dict(sorted(dietary_tag_counts.items()))} "
                "of released recipes carry a positive tag; a recipe with any unmapped "
                "ingredient carries none, by design (see scripts/derive_dietary_tags.py)"
            ),
            "servings_basis == 'range_lower_bound' rows carry an estimated, not stated, "
            "servings count (see src/servings.py)",
        ],
        "immutability": (
            "This manifest and the files alongside it are a frozen snapshot. Corrections "
            "produce a new release_version; this one is not edited in place."
        ),
    }
    write_json(args.out_dir / "release_manifest.json", manifest)

    report_lines = [
        f"# Data Release {args.version}",
        "",
        f"Generated {manifest['created_at']} from pipeline revision `{manifest['pipeline_git_revision']}`.",
        "",
        "## Scope",
        "",
        f"- Upstream recipes scanned: {total}",
        f"- Released (four-condition eligible): {eligible} ({eligible / total * 100:.3f}%)",
        f"- Released canonical ingredients: {kept_ingredients}",
        f"- Servings basis: {dict(servings_basis_counts)}",
        "",
        "## Release gate",
        "",
        "See `docs/schema-v1-freeze.md`. Every released recipe has every ingredient "
        "mapped, quantified, and unit-anchored (mass/volume/count), and a non-null "
        "servings count.",
        "",
        "## Known gaps",
        "",
        *[f"- {gap}" for gap in manifest["known_gaps"]],
        "",
    ]
    (args.out_dir / "quality_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    elapsed = time.monotonic() - start
    print(f"wrote release {args.version} to {args.out_dir} in {elapsed / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
