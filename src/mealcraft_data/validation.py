from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import read_jsonl


def _require(record: dict[str, Any], fields: set[str], context: str) -> list[str]:
    return [f"{context}: missing field '{field}'" for field in sorted(fields - record.keys())]


def validate_outputs(recipe_path: Path, ingredient_path: Path) -> list[str]:
    recipes = read_jsonl(recipe_path)
    ingredients = read_jsonl(ingredient_path)
    errors: list[str] = []
    recipe_ids: set[str] = set()
    ingredient_ids: set[str] = set()

    ingredient_required = {
        "ingredient_id",
        "canonical_name",
        "aliases",
        "mapping_status",
        "provenance",
    }
    for index, ingredient in enumerate(ingredients, start=1):
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
    for index, recipe in enumerate(recipes, start=1):
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
            errors.append(f"{context}: instruction step numbers are not consecutive")
        nutrition = recipe.get("nutrition", {})
        if nutrition.get("status") == "not_computed":
            numeric_fields = (
                "energy_kcal",
                "protein_g",
                "carbohydrate_g",
                "fat_g",
                "sugar_g",
                "sodium_mg",
            )
            if any(nutrition.get(field) is not None for field in numeric_fields):
                errors.append(f"{context}: not_computed nutrition contains numeric values")

    if not recipes:
        errors.append("recipe file contains no records")
    if not ingredients:
        errors.append("ingredient file contains no records")
    return errors

