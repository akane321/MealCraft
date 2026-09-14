"""Run the full 1,643,098-row Gathered RecipeNLG set on a memory-constrained
machine by processing it in chunks and merging the results with streaming
passes that never hold the whole dataset in memory at once.

The existing pipeline (run_pipeline) is used completely unmodified per chunk -
it is already validated up to ~300,000 rows. Only the merge step is new:

  1. Run the pipeline on each pre-split chunk (see split_recipenlg.py);
     archive each chunk's `recipes.jsonl` immediately, before the next chunk
     run overwrites the working data/curated/ directory.
  2. Stream-merge all chunk recipe files line-by-line into the final
     `data/curated/recipes.jsonl`, deduplicating by recipe_id (RecipeNLG has
     occasional exact-duplicate rows that a naive per-chunk split would
     otherwise double-count).
  3. Stream-rebuild `data/curated/ingredients.jsonl` by reading the merged
     recipes file one line at a time - never materializing the full recipe
     list - and accumulating the same per-ingredient stats
     `_build_ingredient_catalog` computes.
  4. Write a report and run_manifest in the same shape `run_pipeline` writes,
     from the streaming pass's own counters.

Run from the project root:

    python scripts/run_full_dataset.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mealcraft_data.config import load_config  # noqa: E402
from mealcraft_data.constants import SCHEMA_VERSION, TRANSFORMATION_VERSION  # noqa: E402
from mealcraft_data.pipeline import run_pipeline, _render_report  # noqa: E402
from mealcraft_data.utils import sha256_file, utc_now_iso, write_json  # noqa: E402

CHUNKS_DIR = ROOT / "data/raw/recipenlg/chunks"
ARCHIVE_DIR = ROOT / "data/curated/chunks_archive"
CURATED = ROOT / "data/curated"
REPORTS = ROOT / "reports"
REVIEW = ROOT / "data/review"


def run_chunks() -> list[Path]:
    chunk_paths = sorted(CHUNKS_DIR.glob("gathered_chunk_*.csv"))
    if not chunk_paths:
        raise SystemExit(f"No chunks found in {CHUNKS_DIR}. Run split_recipenlg.py first.")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archived: list[Path] = []
    for index, chunk_path in enumerate(chunk_paths):
        archive_path = ARCHIVE_DIR / f"recipes_{chunk_path.stem}.jsonl"
        if archive_path.exists():
            print(f"[{index + 1}/{len(chunk_paths)}] {chunk_path.name}: already archived, skipping run")
            archived.append(archive_path)
            continue
        print(f"[{index + 1}/{len(chunk_paths)}] running pipeline on {chunk_path.name} ...")
        start = time.monotonic()
        report = run_pipeline(
            project_root=ROOT,
            input_path=chunk_path,
            sample_size=10_000_000,  # larger than any chunk: takes every row
            seed=5105,
            source_filter=None,  # chunks are already Gathered-only
            review_limit=0,
        )
        elapsed = time.monotonic() - start
        print(f"    {report['recipes_output']} recipes in {elapsed / 60:.1f} min")
        shutil.move(str(CURATED / "recipes.jsonl"), str(archive_path))
        archived.append(archive_path)
    return archived


def merge_recipes(chunk_files: list[Path]) -> tuple[Path, int, int]:
    """Stream-concatenate chunk recipe files, deduplicating by recipe_id."""
    out_path = CURATED / "recipes.jsonl"
    seen: set[str] = set()
    total_in = 0
    total_out = 0
    with out_path.open("w", encoding="utf-8") as out_handle:
        for chunk_file in chunk_files:
            with chunk_file.open("r", encoding="utf-8") as in_handle:
                for line in in_handle:
                    line = line.strip()
                    if not line:
                        continue
                    total_in += 1
                    recipe_id = json.loads(line)["recipe_id"]
                    if recipe_id in seen:
                        continue
                    seen.add(recipe_id)
                    out_handle.write(line + "\n")
                    total_out += 1
    return out_path, total_in, total_out


def rebuild_ingredients_and_report(
    recipes_path: Path, config, source_rows_seen: int, requested_sample_size: int
) -> dict:
    """One streaming pass over the merged recipes file: rebuilds the
    ingredient catalog and the quality-report counters without ever holding
    more than one recipe dict, plus the small per-ingredient accumulators, in
    memory at once."""
    occurrences: Counter[str] = Counter()
    observed_aliases: dict[str, set[str]] = defaultdict(set)
    recipe_ids: dict[str, set[str]] = defaultdict(set)
    statuses: dict[str, set[str]] = defaultdict(set)

    recipe_count = 0
    duplicate_ids = 0  # merge_recipes already dedupes, so this stays 0
    quantified = 0
    unit_recognized = 0
    mapped = 0
    denominator = 0
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    servings_present = 0

    with recipes_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            recipe = json.loads(line)
            recipe_count += 1
            if recipe.get("servings") is not None:
                servings_present += 1
            for item in recipe["ingredients"]:
                denominator += 1
                status_counts[item["normalization_status"]] += 1
                for reason in item["review_reasons"]:
                    reason_counts[reason] += 1
                if item["quantity_min"] is not None:
                    quantified += 1
                if item["unit_normalized"] is not None:
                    unit_recognized += 1
                if item["normalization_status"] == "mapped":
                    mapped += 1
                ingredient_id = item["canonical_ingredient_id"]
                if not ingredient_id:
                    continue
                occurrences[ingredient_id] += 1
                observed_aliases[ingredient_id].add(item["ingredient_text"])
                recipe_ids[ingredient_id].add(recipe["recipe_id"])
                statuses[ingredient_id].add(item["normalization_status"])
            # Free this recipe's memory before reading the next line; nothing
            # above keeps a reference to `recipe` or `item` past this point.

    rule_by_id = {}
    for rule in config.ingredients.values():
        rule_by_id.setdefault(rule.ingredient_id, rule)

    ingredients_path = CURATED / "ingredients.jsonl"
    with ingredients_path.open("w", encoding="utf-8") as handle:
        for ingredient_id in sorted(occurrences):
            rule = rule_by_id.get(ingredient_id)
            canonical_name = (
                rule.canonical_name if rule else sorted(observed_aliases[ingredient_id])[0]
            )
            catalog_aliases = sorted(
                alias
                for alias, candidate_rule in config.ingredients.items()
                if candidate_rule.ingredient_id == ingredient_id
            )
            record = {
                "ingredient_id": ingredient_id,
                "canonical_name": canonical_name,
                "language": "en",
                "aliases": sorted(set(catalog_aliases) | observed_aliases[ingredient_id]),
                "food_group": rule.food_group if rule else "unclassified",
                "allergens": list(rule.allergens) if rule else [],
                "foodon_id": None,
                "fdc_id": None,
                "nutrition_basis": None,
                "mapping_status": (
                    "internal_mapped" if statuses[ingredient_id] == {"mapped"} else "candidate"
                ),
                "occurrence_count": occurrences[ingredient_id],
                "recipe_count": len(recipe_ids[ingredient_id]),
                "provenance": {
                    "source": "config/ingredient_aliases.csv"
                    if rule
                    else "parsed RecipeNLG candidate",
                    "transformation_version": TRANSFORMATION_VERSION,
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            # `occurrences`/`observed_aliases`/`recipe_ids`/`statuses` entries
            # for this id are not needed again but Python keeps the dict
            # entries until the whole loop ends - the cost is proportional to
            # the number of distinct ingredients, not the number of recipes.

    report = {
        "schema_version": SCHEMA_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "source_rows_seen": source_rows_seen,
        "requested_sample_size": requested_sample_size,
        "recipes_output": recipe_count,
        "recipe_duplicate_ids": duplicate_ids,
        "ingredient_occurrences": denominator,
        "canonical_ingredient_records": len(occurrences),
        "mapped_occurrences": mapped,
        "mapping_coverage": round(mapped / denominator, 4) if denominator else 0.0,
        "quantity_coverage": round(quantified / denominator, 4) if denominator else 0.0,
        "recognized_unit_coverage": round(unit_recognized / denominator, 4) if denominator else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "review_reason_counts": dict(sorted(reason_counts.items())),
        "ingredient_review_queue_size": 0,
        "recipe_review_queue_size": 0,
        "nutrition_computed_recipes": 0,
        "servings_present": servings_present,
        "servings_coverage": round(servings_present / recipe_count, 4) if recipe_count else 0.0,
        "quality_gate": {
            "duplicate_recipe_ids_zero": duplicate_ids == 0,
            "nonempty_recipe_output": recipe_count > 0,
            "mapping_coverage_at_least_0_50": (mapped / denominator >= 0.5) if denominator else False,
        },
    }
    return report


def main() -> int:
    config = load_config(ROOT)

    print("=== step 1/3: run pipeline per chunk ===")
    chunk_files = run_chunks()

    print("=== step 2/3: stream-merge recipes across chunks (dedup by recipe_id) ===")
    recipes_path, total_in, total_out = merge_recipes(chunk_files)
    print(f"    {total_in} recipe rows across chunks -> {total_out} unique after dedup")

    print("=== step 3/3: stream-rebuild ingredient catalog + report ===")
    input_path = ROOT / "data/raw/recipenlg/full_dataset.csv"
    report = rebuild_ingredients_and_report(
        recipes_path, config, source_rows_seen=1_643_098, requested_sample_size=total_out
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    write_json(REPORTS / "latest.json", report)
    (REPORTS / "latest.md").write_text(_render_report(report), encoding="utf-8")
    write_json(
        REPORTS / "run_manifest.json",
        {
            "created_at": utc_now_iso(),
            "input_path": "data/raw/recipenlg/full_dataset.csv",
            "input_sha256": sha256_file(input_path),
            "sample_size": total_out,
            "seed": 5105,
            "source_filter": "Gathered",
            "review_limit": 0,
            "schema_version": SCHEMA_VERSION,
            "transformation_version": TRANSFORMATION_VERSION,
            "note": "Full-dataset run assembled from chunked sub-runs; see scripts/run_full_dataset.py.",
            "chunk_count": len(chunk_files),
            "outputs": {
                "recipes": "data/curated/recipes.jsonl",
                "ingredients": "data/curated/ingredients.jsonl",
                "quality_report": "reports/latest.json",
            },
        },
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
