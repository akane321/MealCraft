"""Read the product echoed constraints into the neutral held-out field dictionary (draft, needs review)."""

from __future__ import annotations

import json

import pytest

from app.core.paths import repository_root
from app.evaluation.field_mapping import MAPPED_FIELDS, NO_COOKING_TIME_LIMIT, map_request_fields

DICTIONARY = json.loads((repository_root() / "scripts" / "sprint2-heldout-fields.json").read_text(encoding="utf-8"))[
    "fields"
]


def native(**changes):
    values = {
        "household_size": 2,
        "max_cooking_time_minutes": NO_COOKING_TIME_LIMIT,
        "budget_per_meal_sgd": None,
        "weekly_budget_sgd": None,
        "allergens": [],
        "excluded_ingredients": [],
        "dietary_preferences": [],
        "health_preferences": [],
        "nutrition_targets": {},
        "max_sodium_mg_per_meal": None,
        "available_ingredients": [],
        "pricing_mode": "fixture",
        "plan_shape": None,
        "max_uses_per_recipe": None,
        "avoid_recipe_ids": [],
        "start_date": "2026-10-23",
    }
    values.update(changes)
    return values


def test_stated_values_map_to_the_dictionary_fields():
    got = map_request_fields(
        native(
            weekly_budget_sgd=140.0,
            allergens=["peanut"],
            excluded_ingredients=["pork"],
            dietary_preferences=["vegetarian"],
            requires_halal=True,
            max_cooking_time_minutes=45,
            plan_shape={"meals": {"lunch": [], "breakfast": []}},
        )
    )
    assert got.fields == {
        "household_size": 2,
        "start_date": "2026-10-23",
        "weekly_budget_sgd": 140.0,
        "allergens": ["peanut"],
        "excluded_ingredients": ["pork"],
        "dietary_requirements": ["vegetarian"],
        "halal_required": True,
        "cooking_time_minutes": 45,
        "meal_types": ["breakfast", "lunch"],
    }


def test_a_missing_value_is_not_stated_never_a_default():
    got = map_request_fields(native(household_size=None, start_date=None, requires_halal=False))
    assert got.fields == {}
    # halal is dropped from the echo when false: the mapping says "not stated", it does not invent False.
    assert "halal_required" in got.not_stated
    # the no-limit sentinel and an empty list are not stated values either
    assert {"cooking_time_minutes", "weekly_budget_sgd", "allergens", "household_size"} <= set(got.not_stated)


def test_values_without_a_dictionary_field_are_listed_and_never_converted():
    got = map_request_fields(
        native(
            budget_per_meal_sgd=20.0,
            max_sodium_mg_per_meal=700.0,
            health_preferences=["low-sodium"],
            max_uses_per_recipe=1,
            available_ingredients=[{"name": "egg"}],
        )
    )
    # a per-meal budget is not a weekly one, a per-meal sodium cap is not a daily limit with a share,
    # and uses per recipe is not repeats: none of them is turned into a dictionary value.
    assert "weekly_budget_sgd" not in got.fields and "sodium_limit_mg" not in got.fields
    assert "maximum_repeats" not in got.fields and "pantry" not in got.fields
    assert set(got.unmapped_native) == {
        "budget_per_meal_sgd",
        "max_sodium_mg_per_meal",
        "health_preferences",
        "max_uses_per_recipe",
        "available_ingredients",
    }


def test_everything_it_can_emit_exists_in_the_public_dictionary_with_the_right_type():
    assert set(MAPPED_FIELDS) <= set(DICTIONARY)
    got = map_request_fields(
        native(
            weekly_budget_sgd=1.0,
            allergens=["a"],
            excluded_ingredients=["b"],
            dietary_preferences=["vegan"],
            requires_halal=True,
            max_cooking_time_minutes=30,
            plan_shape={"meals": {"dinner": []}},
        )
    )
    kinds = {"integer": int, "number": (int, float), "string": str, "array": list, "boolean": bool}
    for name, value in got.fields.items():
        expected = DICTIONARY[name]["schema"].get("type")
        if expected:
            assert isinstance(value, kinds[expected]), name


def test_dictionary_fields_it_never_produces_are_listed():
    got = map_request_fields(native())
    assert set(got.dictionary_not_produced) == set(DICTIONARY) - set(MAPPED_FIELDS)
    assert {"members", "attendance", "pantry", "sodium_limit_mg", "action"} <= set(got.dictionary_not_produced)


def test_it_reads_only_the_echoed_fields_and_changes_nothing():
    before = native(allergens=["peanut"])
    copy = json.loads(json.dumps(before))
    map_request_fields(before)
    assert before == copy
    with pytest.raises(TypeError):
        map_request_fields("peanut allergy")  # an answer text is never an input
