import importlib.util
import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import CheckConstraint

from app.db.base import Base
from app.schemas.catalog_tags import (
    RETAILERS,
    EquipmentNeeds,
    FeedbackKind,
    FeedbackSource,
    FieldEstimate,
    HalalStatus,
    IngredientHalalStatus,
    IngredientLineProvenance,
    MealRole,
    RecipeEstimates,
    Retailer,
    RetailerChoice,
)
from app.schemas.household_rules import (
    CookingTimeRule,
    NutritionLimit,
    PlanningPreferences,
    PresenceRule,
)

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261018_0030_sprint2_foundation.py"

# Each CHECK constraint that lists values, and the Literal that owns the list.
CHECKED_VALUES = {
    ("recipes", "recipes_meal_role_valid"): MealRole,
    ("recipes", "recipes_halal_status_valid"): HalalStatus,
    ("ingredients", "ingredients_halal_status_valid"): IngredientHalalStatus,
    ("recipe_feedback", "recipe_feedback_kind_valid"): FeedbackKind,
    ("recipe_feedback", "recipe_feedback_source_valid"): FeedbackSource,
}


def _quoted(sql: str) -> set[str]:
    return set(re.findall(r"'([^']*)'", sql))


def _model_check(table: str, name: str) -> str:
    constraint = next(
        item
        for item in Base.metadata.tables[table].constraints
        if isinstance(item, CheckConstraint) and item.name == name
    )
    return str(constraint.sqltext)


@pytest.mark.parametrize(("table", "name"), list(CHECKED_VALUES))
def test_each_check_constraint_lists_exactly_its_enum(table: str, name: str) -> None:
    assert _quoted(_model_check(table, name)) == set(get_args(CHECKED_VALUES[(table, name)]))


def test_the_migration_freezes_the_same_value_lists() -> None:
    spec = importlib.util.spec_from_file_location("sprint2_foundation", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert _quoted(migration.MEAL_ROLE_CHECK) == set(get_args(MealRole))
    assert _quoted(migration.RECIPE_HALAL_CHECK) == set(get_args(HalalStatus))
    assert _quoted(migration.INGREDIENT_HALAL_CHECK) == set(get_args(IngredientHalalStatus))
    assert migration.MEAL_ROLE_CHECK == _model_check("recipes", "recipes_meal_role_valid")
    assert migration.RECIPE_HALAL_CHECK == _model_check("recipes", "recipes_halal_status_valid")
    assert migration.INGREDIENT_HALAL_CHECK == _model_check("ingredients", "ingredients_halal_status_valid")


def test_rules_forbid_unknown_keys_and_values() -> None:
    rule = {
        "source_text": "The kids have lunch at school on weekdays",
        "restatement": "Mon-Fri lunch: kids away",
        "member_name": "Kid",
        "present": False,
        "weekdays": ["monday", "friday"],
        "meal_types": ["lunch"],
    }
    assert PresenceRule.model_validate(rule).weekdays == ["monday", "friday"]
    with pytest.raises(ValidationError):
        PresenceRule.model_validate({**rule, "dates": ["2026-10-19"]})
    with pytest.raises(ValidationError):
        PresenceRule.model_validate({**rule, "weekdays": ["someday"]})
    with pytest.raises(ValidationError):
        CookingTimeRule.model_validate({**rule, "max_minutes": 30})  # member_name/present are not its keys
    assert NutritionLimit(nutrient="sodium_mg").max_value is None
    with pytest.raises(ValidationError):
        NutritionLimit.model_validate({"nutrient": "fibre_g"})
    assert PlanningPreferences() == PlanningPreferences.model_validate(
        {"repeat_allowed_meals": [], "flavor_boosts": [], "more_vegetables": False, "lighter": False}
    )
    with pytest.raises(ValidationError):
        PlanningPreferences.model_validate({"flavor_boosts": [{"flavor": "smoky"}]})


def test_recipe_tags_validate_their_values() -> None:
    assert TypeAdapter(EquipmentNeeds).validate_python([["oven", "air_fryer"], ["blender"]])
    with pytest.raises(ValidationError):
        TypeAdapter(EquipmentNeeds).validate_python([[]])
    with pytest.raises(ValidationError):
        TypeAdapter(MealRole).validate_python("poultry")
    estimates = TypeAdapter(RecipeEstimates).validate_python({"meal_role": {"method": "llm", "batch": "b1"}})
    assert estimates["meal_role"] == FieldEstimate(method="llm", batch="b1")
    with pytest.raises(ValidationError):  # safety labels are never estimated
        TypeAdapter(RecipeEstimates).validate_python({"halal_status": {"method": "llm", "batch": "b1"}})
    with pytest.raises(ValidationError):
        IngredientLineProvenance.model_validate({"match": "guess"})


def test_a_retailer_is_a_registered_slug() -> None:
    adapter = TypeAdapter(Retailer)
    assert [adapter.validate_python(slug) for slug in RETAILERS] == list(RETAILERS)
    for bad in ("FairPrice", "unknown_mart", "fair price", ""):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    assert RetailerChoice(ingredient="soy_sauce", retailer="giant").product_external_id is None
    with pytest.raises(ValidationError):
        RetailerChoice.model_validate({"ingredient": "soy_sauce", "retailer": "giant", "price": 1})
