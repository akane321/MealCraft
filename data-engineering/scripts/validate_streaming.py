"""Streaming equivalent of mealcraft_data.validation.validate_outputs for
files too large to load into memory at once (the full 1.64M-recipe merge).
Same checks, same error message format; recipes are read and discarded one
line at a time instead of being materialized as a list.

Run from the project root:

    python scripts/validate_streaming.py --recipes data/curated/recipes.jsonl \\
        --ingredients data/curated/ingredients.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _require(record: dict, fields: set[str], context: str) -> list[str]:
    return [f"{context}: missing field '{field}'" for field in sorted(fields - record.keys())]


def validate_streaming(recipe_path: Path, ingredient_path: Path, max_errors: int = 200) -> list[str]:
    errors: list[str] = []
    ingredient_ids: set[str] = set()

    ingredient_required = {"ingredient_id", "canonical_name", "aliases", "mapping_status", "provenance"}
    with ingredient_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            ingredient = json.loads(line)
            context = f"ingredient line {index}"
            errors.extend(_require(ingredient, ingredient_required, context))
            ingredient_id = ingredient.get("ingredient_id")
            if not ingredient_id:
                errors.append(f"{context}: empty ingredient_id")
            elif ingredient_id in ingredient_ids:
                errors.append(f"{context}: duplicate ingredient_id {ingredient_id}")
            else:
                ingredient_ids.add(ingredient_id)

    recipe_required = {
        "recipe_id",
        "schema_version",
        "title",
        "source",
        "ingredients",
        "instructions",
        "nutrition",
        "quality",
        "provenance",
    }
    occurrence_required = {
        "original_text",
        "quantity_min",
        "quantity_max",
        "ingredient_text",
        "canonical_ingredient_id",
        "normalization_status",
        "confidence",
        "review_reasons",
    }
    recipe_ids: set[str] = set()
    count = 0
    with recipe_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            recipe = json.loads(line)
            count += 1
            context = f"recipe line {index}"
            errors.extend(_require(recipe, recipe_required, context))
            recipe_id = recipe.get("recipe_id")
            if not recipe_id:
                errors.append(f"{context}: empty recipe_id")
            elif recipe_id in recipe_ids:
                errors.append(f"{context}: duplicate recipe_id {recipe_id}")
            else:
                recipe_ids.add(recipe_id)
            if not recipe.get("title"):
                errors.append(f"{context}: empty title")
            source = recipe.get("source", {})
            if not source.get("dataset") or not source.get("source_license"):
                errors.append(f"{context}: incomplete source provenance")
            for item_index, item in enumerate(recipe.get("ingredients", []), start=1):
                item_context = f"{context}, ingredient {item_index}"
                errors.extend(_require(item, occurrence_required, item_context))
                ingredient_id = item.get("canonical_ingredient_id")
                if ingredient_id and ingredient_id not in ingredient_ids:
                    errors.append(f"{item_context}: unknown ingredient_id {ingredient_id}")
                low = item.get("quantity_min")
                high = item.get("quantity_max")
                if low is not None and high is not None and low > high:
                    errors.append(f"{item_context}: quantity_min exceeds quantity_max")
                confidence = item.get("confidence")
                if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                    errors.append(f"{item_context}: confidence must be between 0 and 1")
            instructions = recipe.get("instructions", [])
            expected_steps = list(range(1, len(instructions) + 1))
            actual_steps = [step.get("step_number") for step in instructions]
            if actual_steps != expected_steps:
                errors.append(f"{context}: instructions out of order or missing steps")
            if len(errors) > max_errors:
                errors.append(f"... stopped after {max_errors} errors (of {count} recipes scanned so far)")
                return errors
    print(f"scanned {count} recipes, {len(ingredient_ids)} ingredients")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipes", required=True, type=Path)
    parser.add_argument("--ingredients", required=True, type=Path)
    args = parser.parse_args()
    errors = validate_streaming(args.recipes.resolve(), args.ingredients.resolve())
    if errors:
        print(f"Validation failed: {len(errors)} error(s)")
        for error in errors[:50]:
            print(f"- {error}")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
