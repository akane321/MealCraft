"""Read the recipe and ingredient tag files and copy them onto catalog rows at import.

The tag files are written by `python -m app.data.recipe_tags` and reviewed as data
(`data-engineering/docs/recipe-tags-v1-sample.json`). The importers apply them in the
overlay order of docs/design/sprint2-schema-foundation.md: the release file first, then
the tag files, then runtime writes. So a recipe or ingredient missing from a tag file
keeps its release value (NULL for every recipe tag), an ingredient row a runtime path wrote
(`provenance` set) keeps any tag value it already holds, and a recipe keeps a tag value a runtime
path wrote (no estimate on the row for it, or one marked `reviewed`).
"""

from __future__ import annotations

import json
from functools import cache

from app.core.paths import repository_root

RECIPE_TAGS = "data/recipes/recipe-tags-v1.json"
INGREDIENT_TAGS = "data/ingredients/ingredient-tags-v1.json"
TAG_FILES = (RECIPE_TAGS, INGREDIENT_TAGS)
RECIPE_TAG_FIELDS = ("meal_role", "contains_staple", "protein_sources", "cooking_methods", "equipment", "flavor_tags")
INGREDIENT_TAG_FIELDS = ("food_group", "perishable", "basic_seasoning")


def _entries(relative: str, key: str) -> dict[str, dict]:
    path = repository_root() / relative
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))[key]


@cache
def recipe_tags() -> dict[str, dict]:
    """Release `external_id` or curated slug -> its tag entry."""
    return _entries(RECIPE_TAGS, "recipes")


@cache
def ingredient_tags() -> dict[str, dict]:
    """Ingredient `normalized_name` -> its tag entry."""
    return _entries(INGREDIENT_TAGS, "ingredients")


def tag_file_bytes() -> bytes:
    """Both tag files, for the release digest; a missing file digests as empty."""
    paths = [repository_root() / name for name in TAG_FILES]
    return b"".join(path.read_bytes() if path.exists() else b"" for path in paths)


def apply_recipe_tags(recipe, key: str) -> None:
    """Set the tag columns and `estimated` from the entry for `key`, or NULL when it has none.

    A value a runtime path wrote wins: one with no estimate on the row (a person or an intake set it, so it is
    not an estimate) or one whose estimate a person marked `reviewed`. Runtime writers mark their writes so.
    """
    entry = recipe_tags().get(key) or {}
    held = dict(recipe.estimated or {})
    estimated = dict(entry.get("estimated") or {})
    for name in RECIPE_TAG_FIELDS:
        value = getattr(recipe, name)
        runtime = value is not None and (name not in held or held[name].get("reviewed"))
        if runtime:
            estimated.pop(name, None)
            if name in held:
                estimated[name] = held[name]
        else:
            setattr(recipe, name, entry.get(name))
    recipe.estimated = estimated or None


def apply_ingredient_tags(row, release_food_group: str | None = None) -> None:
    """Release value, then the tag file; a runtime-written row keeps the values it already has."""
    entry = ingredient_tags().get(row.normalized_name) or {}
    values = {"food_group": release_food_group, "perishable": None, "basic_seasoning": None}
    values.update({name: entry[name] for name in INGREDIENT_TAG_FIELDS if name in entry})
    runtime = row.provenance is not None
    for name, value in values.items():
        if not (runtime and getattr(row, name) is not None):
            setattr(row, name, value)
