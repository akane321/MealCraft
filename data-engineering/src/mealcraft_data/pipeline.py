from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .config import CleaningConfig, load_config
from .constants import RECIPENLG_LICENSE, SCHEMA_VERSION, TRANSFORMATION_VERSION
from .io import iter_recipenlg, reservoir_sample
from .parsing import ParsedIngredient, parse_ingredient
from .servings import extract_servings
from .utils import sha256_file, stable_id, utc_now_iso, write_json, write_jsonl


def _is_note_only(item: ParsedIngredient) -> bool:
    """A source line that carries no food name, quantity or unit is an editorial
    note ("(see note)", "OPTIONAL", "_____"), not an ingredient occurrence."""
    return (
        item.normalization_status == "unresolved"
        and not item.ingredient_text
        and item.quantity_min is None
        and item.unit_normalized is None
    )


def _recipe_record(raw: dict[str, Any], parsed: list[ParsedIngredient]) -> dict[str, Any]:
    recipe_id = stable_id(
        "RCP",
        raw["title"].casefold(),
        json.dumps(raw["ingredients"], ensure_ascii=False, sort_keys=True),
    )
    kept = [item for item in parsed if not _is_note_only(item)]
    dropped_note_lines = len(parsed) - len(kept)
    if kept:  # never drop the last row and leave a recipe with no ingredients
        parsed = kept

    warnings: list[str] = []
    if dropped_note_lines and kept:
        warnings.append("dropped_note_lines")
    if not raw["title"]:
        warnings.append("missing_title")
    if not raw["directions"]:
        warnings.append("missing_instructions")
    if not parsed:
        warnings.append("missing_ingredients")
    if any(item.normalization_status != "mapped" for item in parsed):
        warnings.append("ingredient_mapping_incomplete")
    if any(item.quantity_min is None for item in parsed):
        warnings.append("ingredient_quantity_incomplete")

    servings_result = extract_servings(" ".join(raw["directions"]))
    if servings_result is None:
        warnings.append("servings_not_stated")
    elif servings_result.basis == "range_lower_bound":
        warnings.append("servings_is_range_lower_bound_estimate")
    servings = servings_result.value if servings_result else None
    servings_basis = servings_result.basis if servings_result else None

    completeness_checks = [
        bool(raw["title"]),
        bool(raw["directions"]),
        bool(parsed),
        all(item.normalization_status == "mapped" for item in parsed) if parsed else False,
        all(item.quantity_min is not None for item in parsed) if parsed else False,
        servings is not None,
    ]
    completeness = sum(completeness_checks) / len(completeness_checks)
    needs_review = bool(warnings) or any(item.review_reasons for item in parsed)
    is_fixture = raw["link"].startswith("synthetic://")

    return {
        "recipe_id": recipe_id,
        "schema_version": SCHEMA_VERSION,
        "title": raw["title"],
        "language": "en",
        "source": {
            "dataset": "synthetic_fixture" if is_fixture else "RecipeNLG",
            "subset": raw["source"],
            "source_row": raw["row_number"],
            "source_url": raw["link"] or None,
            "source_license": (
                "Project-authored synthetic fixture" if is_fixture else RECIPENLG_LICENSE
            ),
        },
        "servings": servings,
        "servings_basis": servings_basis,
        "prep_minutes": None,
        "cook_minutes": None,
        "cuisine": None,
        "meal_types": [],
        "dietary_tags": [],
        "methods": [],
        "equipment": [],
        "difficulty": None,
        "ingredients": [item.to_dict() for item in parsed],
        "instructions": [
            {"step_number": index, "text": step}
            for index, step in enumerate(raw["directions"], start=1)
        ],
        "nutrition": {
            "status": "not_computed",
            "basis": "per_serving",
            "energy_kcal": None,
            "protein_g": None,
            "carbohydrate_g": None,
            "fat_g": None,
            "sugar_g": None,
            "sodium_mg": None,
            "source": None,
            "completeness": 0.0,
            "reason": (
                "Servings stated but reliable mass conversion and a reviewed "
                "USDA nutrition mapping are not yet available."
                if servings is not None
                else "Servings are not stated and reliable mass conversion is not yet available."
            ),
        },
        "quality": {
            "completeness": round(completeness, 3),
            "needs_review": needs_review,
            "warnings": sorted(set(warnings)),
        },
        "provenance": {"transformation_version": TRANSFORMATION_VERSION},
    }


def _build_ingredient_catalog(
    recipes: list[dict[str, Any]], config: CleaningConfig
) -> list[dict[str, Any]]:
    occurrences: Counter[str] = Counter()
    observed_aliases: dict[str, set[str]] = defaultdict(set)
    recipe_ids: dict[str, set[str]] = defaultdict(set)
    statuses: dict[str, set[str]] = defaultdict(set)

    for recipe in recipes:
        for item in recipe["ingredients"]:
            ingredient_id = item["canonical_ingredient_id"]
            if not ingredient_id:
                continue
            occurrences[ingredient_id] += 1
            observed_aliases[ingredient_id].add(item["ingredient_text"])
            recipe_ids[ingredient_id].add(recipe["recipe_id"])
            statuses[ingredient_id].add(item["normalization_status"])

    rule_by_id = {}
    for rule in config.ingredients.values():
        rule_by_id.setdefault(rule.ingredient_id, rule)

    result: list[dict[str, Any]] = []
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
        result.append(
            {
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
        )
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_review_queues(
    project_root: Path,
    recipes: list[dict[str, Any]],
    review_limit: int,
) -> tuple[int, int]:
    ingredient_rows: list[dict[str, Any]] = []
    recipe_rows: list[dict[str, Any]] = []
    priority = {
        "empty_ingredient": 0,
        "empty_after_parsing": 0,
        "ambiguous_alternative": 1,
        "unmapped_ingredient": 2,
        "unit_missing_or_unknown": 3,
        "informal_quantity": 4,
        "quantity_range": 5,
        "ner_mismatch": 6,
        "missing_quantity": 7,
    }

    for recipe in recipes:
        if recipe["quality"]["needs_review"]:
            recipe_rows.append(
                {
                    "recipe_id": recipe["recipe_id"],
                    "title": recipe["title"],
                    "completeness": recipe["quality"]["completeness"],
                    "warnings": ";".join(recipe["quality"]["warnings"]),
                    "review_decision": "",
                    "reviewer_notes": "",
                    "reviewer": "",
                    "reviewed_at": "",
                }
            )
        for index, item in enumerate(recipe["ingredients"], start=1):
            if not item["review_reasons"]:
                continue
            reasons = item["review_reasons"]
            ingredient_rows.append(
                {
                    "priority": min(priority.get(reason, 99) for reason in reasons),
                    "recipe_id": recipe["recipe_id"],
                    "recipe_title": recipe["title"],
                    "ingredient_index": index,
                    "original_text": item["original_text"],
                    "parsed_name": item["ingredient_text"],
                    "suggested_ingredient_id": item["canonical_ingredient_id"] or "",
                    "suggested_canonical_name": item["canonical_name"] or "",
                    "confidence": item["confidence"],
                    "review_reasons": ";".join(reasons),
                    "review_decision": "",
                    "reviewed_canonical_name": "",
                    "reviewed_ingredient_id": "",
                    "reviewer_notes": "",
                    "reviewer": "",
                    "reviewed_at": "",
                }
            )

    ingredient_rows.sort(
        key=lambda row: (row["priority"], float(row["confidence"]), row["original_text"])
    )
    ingredient_rows = ingredient_rows[:review_limit]
    recipe_rows.sort(key=lambda row: (float(row["completeness"]), row["recipe_id"]))
    recipe_rows = recipe_rows[:review_limit]

    review_dir = project_root / "data" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(review_dir / "ingredient_review_queue.csv", ingredient_rows)
    _write_csv(review_dir / "recipe_review_queue.csv", recipe_rows)
    return len(ingredient_rows), len(recipe_rows)


def _quality_report(
    recipes: list[dict[str, Any]],
    ingredients: list[dict[str, Any]],
    source_rows_seen: int,
    requested_sample_size: int,
    ingredient_review_count: int,
    recipe_review_count: int,
) -> dict[str, Any]:
    occurrences = [item for recipe in recipes for item in recipe["ingredients"]]
    status_counts = Counter(item["normalization_status"] for item in occurrences)
    reason_counts = Counter(
        reason for item in occurrences for reason in item["review_reasons"]
    )
    mapped = status_counts.get("mapped", 0)
    quantified = sum(item["quantity_min"] is not None for item in occurrences)
    unit_recognized = sum(item["unit_normalized"] is not None for item in occurrences)
    denominator = len(occurrences)
    duplicate_ids = len(recipes) - len({recipe["recipe_id"] for recipe in recipes})

    return {
        "schema_version": SCHEMA_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "source_rows_seen": source_rows_seen,
        "requested_sample_size": requested_sample_size,
        "recipes_output": len(recipes),
        "recipe_duplicate_ids": duplicate_ids,
        "ingredient_occurrences": denominator,
        "canonical_ingredient_records": len(ingredients),
        "mapped_occurrences": mapped,
        "mapping_coverage": round(mapped / denominator, 4) if denominator else 0.0,
        "quantity_coverage": round(quantified / denominator, 4) if denominator else 0.0,
        "recognized_unit_coverage": round(unit_recognized / denominator, 4)
        if denominator
        else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "review_reason_counts": dict(sorted(reason_counts.items())),
        "ingredient_review_queue_size": ingredient_review_count,
        "recipe_review_queue_size": recipe_review_count,
        "nutrition_computed_recipes": 0,
        "quality_gate": {
            "duplicate_recipe_ids_zero": duplicate_ids == 0,
            "nonempty_recipe_output": bool(recipes),
            "mapping_coverage_at_least_0_50": (mapped / denominator >= 0.5)
            if denominator
            else False,
        },
    }


def _render_report(report: dict[str, Any]) -> str:
    gate_lines = "\n".join(
        f"- {'PASS' if passed else 'FAIL'} — `{name}`"
        for name, passed in report["quality_gate"].items()
    )
    reason_lines = "\n".join(
        f"- `{name}`: {count}" for name, count in report["review_reason_counts"].items()
    )
    return f"""# MealCraft Data Quality Report

Generated by `{report['transformation_version']}`.

## Scope

- Source rows examined: {report['source_rows_seen']}
- Requested sample: {report['requested_sample_size']}
- Recipes emitted: {report['recipes_output']}
- Ingredient occurrences: {report['ingredient_occurrences']}
- Canonical/candidate ingredient records: {report['canonical_ingredient_records']}

## Coverage

- Internal mapping coverage: {report['mapping_coverage']:.2%}
- Quantity coverage: {report['quantity_coverage']:.2%}
- Recognized-unit coverage: {report['recognized_unit_coverage']:.2%}
- Nutrition computed: {report['nutrition_computed_recipes']} recipes

`nutrition_computed_recipes = 0` is intentional in this first pass because RecipeNLG does not provide reliable servings and mass conversions for every row.

## Quality gates

{gate_lines}

## Review reasons

{reason_lines or '- None'}

## Human-review queues

- Ingredient rows: {report['ingredient_review_queue_size']}
- Recipe rows: {report['recipe_review_queue_size']}
"""


def run_pipeline(
    project_root: Path,
    input_path: Path,
    sample_size: int,
    seed: int,
    source_filter: str | None,
    review_limit: int,
) -> dict[str, Any]:
    config = load_config(project_root)
    raw_rows, source_rows_seen = reservoir_sample(
        iter_recipenlg(input_path, source_filter=source_filter), sample_size, seed
    )

    staging_rows: list[dict[str, Any]] = []
    recipes: list[dict[str, Any]] = []
    seen_recipe_ids: set[str] = set()
    for raw in raw_rows:
        parsed = [
            parse_ingredient(item, config=config, source_ner=raw["ner"])
            for item in raw["ingredients"]
        ]
        staging_rows.append(
            {"raw": raw, "parsed_ingredients": [item.to_dict() for item in parsed]}
        )
        recipe = _recipe_record(raw, parsed)
        if recipe["recipe_id"] in seen_recipe_ids:
            continue
        seen_recipe_ids.add(recipe["recipe_id"])
        recipes.append(recipe)

    recipes.sort(key=lambda row: row["recipe_id"])
    ingredients = _build_ingredient_catalog(recipes, config)
    write_jsonl(project_root / "data" / "staging" / "recipes.parsed.jsonl", staging_rows)
    write_jsonl(project_root / "data" / "curated" / "recipes.jsonl", recipes)
    write_jsonl(project_root / "data" / "curated" / "ingredients.jsonl", ingredients)

    ingredient_review_count, recipe_review_count = _write_review_queues(
        project_root, recipes, review_limit
    )
    report = _quality_report(
        recipes,
        ingredients,
        source_rows_seen,
        sample_size,
        ingredient_review_count,
        recipe_review_count,
    )
    reports_dir = project_root / "reports"
    write_json(reports_dir / "latest.json", report)
    (reports_dir / "latest.md").write_text(_render_report(report), encoding="utf-8")
    try:
        manifest_input_path = str(input_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        manifest_input_path = str(input_path.resolve())
    write_json(
        reports_dir / "run_manifest.json",
        {
            "created_at": utc_now_iso(),
            "input_path": manifest_input_path,
            "input_sha256": sha256_file(input_path),
            "sample_size": sample_size,
            "seed": seed,
            "source_filter": source_filter,
            "review_limit": review_limit,
            "schema_version": SCHEMA_VERSION,
            "transformation_version": TRANSFORMATION_VERSION,
            "outputs": {
                "recipes": "data/curated/recipes.jsonl",
                "ingredients": "data/curated/ingredients.jsonl",
                "ingredient_review": "data/review/ingredient_review_queue.csv",
                "recipe_review": "data/review/recipe_review_queue.csv",
                "quality_report": "reports/latest.json",
            },
        },
    )
    return report
