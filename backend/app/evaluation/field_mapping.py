"""Read the product's echoed constraints into the neutral held-out field dictionary (draft, needs independent review).

Input is only `UnifiedOutput.request_fields`, the product's own echo of its constraints. Nothing is inferred from an
answer text, a recipe name or a category. A value the product did not state is reported as not stated, never as a
default; a native value with no counterpart in the dictionary is listed and never converted (a per-meal budget is not a
weekly one, a per-meal sodium cap is not a daily limit with a dinner share, uses per recipe is not repeats).

The dictionary is the public neutral one (`scripts/sprint2-heldout-fields.json`). Fields the sealed set may add beyond
it are not known here. This module does not load a sealed file or score anything.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.recommendation import NO_COOKING_TIME_LIMIT

# The dictionary fields this mapping can produce.
MAPPED_FIELDS = (
    "household_size",
    "start_date",
    "weekly_budget_sgd",
    "allergens",
    "excluded_ingredients",
    "dietary_requirements",
    "halal_required",
    "cooking_time_minutes",
    "meal_types",
)
# Native keys that are read; any other non-empty key is reported as unmapped.
READ_KEYS = {
    "household_size",
    "start_date",
    "weekly_budget_sgd",
    "allergens",
    "excluded_ingredients",
    "dietary_preferences",
    "requires_halal",
    "max_cooking_time_minutes",
    "plan_shape",
}
# Native keys that carry only a default or a non-constraint: never reported as unmapped.
IGNORED_KEYS = {"pricing_mode", "avoid_recipe_ids"}
MEAL_ORDER = ("breakfast", "lunch", "dinner")


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fields: dict[str, Any]
    not_stated: list[str]
    unmapped_native: list[str]
    dictionary_not_produced: list[str]


def _public_dictionary() -> dict:
    path = Path(__file__).resolve().parents[3] / "scripts" / "sprint2-heldout-fields.json"
    return json.loads(path.read_text(encoding="utf-8"))["fields"]


def _empty(value: Any) -> bool:
    return value is None or value == [] or value == {} or value == ""


def map_request_fields(request_fields: Mapping[str, Any]) -> FieldMapping:
    if not isinstance(request_fields, Mapping):
        raise TypeError("pass the product's echoed request fields, never an answer text")
    native = request_fields
    fields: dict[str, Any] = {}

    def put(name: str, value: Any) -> None:
        fields[name] = value

    if native.get("household_size") is not None:
        put("household_size", native["household_size"])
    if native.get("start_date"):
        put("start_date", str(native["start_date"]))
    if native.get("weekly_budget_sgd") is not None:
        put("weekly_budget_sgd", native["weekly_budget_sgd"])
    for source, target in (
        ("allergens", "allergens"),
        ("excluded_ingredients", "excluded_ingredients"),
        ("dietary_preferences", "dietary_requirements"),
    ):
        if native.get(source):
            put(target, list(native[source]))
    if native.get("requires_halal") is True:
        put("halal_required", True)
    cooking = native.get("max_cooking_time_minutes")
    if cooking is not None and cooking != NO_COOKING_TIME_LIMIT:
        put("cooking_time_minutes", cooking)
    shape = native.get("plan_shape")
    if isinstance(shape, Mapping) and shape.get("meals"):
        meals = shape["meals"]
        put("meal_types", [meal for meal in MEAL_ORDER if meal in meals])

    unmapped = sorted(key for key, value in native.items() if key not in READ_KEYS | IGNORED_KEYS and not _empty(value))
    dictionary = _public_dictionary()
    return FieldMapping(
        fields=fields,
        not_stated=sorted(set(MAPPED_FIELDS) - set(fields)),
        unmapped_native=unmapped,
        dictionary_not_produced=sorted(set(dictionary) - set(MAPPED_FIELDS)),
    )
