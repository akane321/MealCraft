import re
from typing import get_args

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.schemas.catalog_tags import FeedbackKind, FeedbackSource, HalalStatus, IngredientHalalStatus, MealRole
from tests.migrations.support import COUNTED_TABLES, MigrationDatabase

PREVIOUS = "20261012_0029"
FOUNDATION = "20261018_0030"

NEW_COLUMNS = {
    "household_profile_versions": {
        "presence_rules",
        "cooking_time_rules",
        "missing_equipment",
        "missing_basics",
        "nutrition_limits",
    },
    "meal_plan_entries": {"servings"},
    "ingredients": {"food_group", "perishable", "basic_seasoning", "halal_status", "nutrition_per_100g", "provenance"},
    "recipes": {
        "meal_role",
        "contains_staple",
        "protein_sources",
        "cooking_methods",
        "flavor_tags",
        "equipment",
        "halal_status",
        "unknown_safety",
        "estimated",
        "owner_household_id",
    },
    "recipe_ingredients": {"provenance"},
    "product_snapshots": {"regular_price_sgd", "halal_certified"},
    "meal_plan_grocery_items": {"retailer", "product_regular_price_sgd"},
}
CHECKED_VALUES = {
    "recipes_meal_role_valid": MealRole,
    "recipes_halal_status_valid": HalalStatus,
    "ingredients_halal_status_valid": IngredientHalalStatus,
    "recipe_feedback_kind_valid": FeedbackKind,
    "recipe_feedback_source_valid": FeedbackSource,
}
# recipe_feedback does not exist before this revision, so it is counted only after the upgrade.
COUNTED = (*COUNTED_TABLES, "recipes", "meal_plan_entries")


def _counts(database: MigrationDatabase) -> dict[str, int]:
    with database.engine.connect() as connection:
        return {table: connection.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one() for table in COUNTED}


def _household_id(connection: Connection) -> int:
    return connection.execute(sa.text("SELECT min(id) FROM households")).scalar_one()


def _add_recipe(connection: Connection, slug: str, extra: str = "", values: str = "") -> int:
    return connection.execute(
        sa.text(
            "INSERT INTO recipes (slug, title, description, cuisine, meal_type, servings, prep_time_minutes, "
            f"cook_time_minutes, dietary_tags{extra}) "
            f"VALUES (:slug, 'Test dish', 'For the migration test', 'Chinese', 'dinner', 2, 10, 20, '[]'{values}) "
            "RETURNING id"
        ),
        {"slug": slug},
    ).scalar_one()


def _add_plan(connection: Connection, recipe_id: int, days: int) -> int:
    plan_id = connection.execute(
        sa.text(
            "INSERT INTO meal_plans (household_id, start_date, end_date, day_count, household_size, pricing_mode, "
            "purchase_total_sgd, constraints, warnings) "
            "VALUES (:household_id, DATE '2026-10-19', DATE '2026-10-19' + (:days - 1), :days, 2, 'fixture', 10, "
            "'{}', '[]') RETURNING id"
        ),
        {"household_id": _household_id(connection), "days": days},
    ).scalar_one()
    for day in range(1, days + 1):
        connection.execute(
            sa.text(
                "INSERT INTO meal_plan_entries (plan_id, recipe_id, day_index, planned_date, recommendation_score, "
                "consumed_cost_sgd, purchase_cost_sgd, calories_kcal, protein_g, carbohydrate_g, fat_g, sodium_mg, "
                "sugar_g, status, is_locked) "
                "VALUES (:plan_id, :recipe_id, :day, DATE '2026-10-18' + :day, 50, 1, 1, 500, 20, 50, 10, 400, 5, "
                "'planned', false)"
            ),
            {"plan_id": plan_id, "recipe_id": recipe_id, "day": day},
        )
    return plan_id


def _seed_week(database: MigrationDatabase) -> int:
    with database.engine.begin() as connection:
        recipe_id = _add_recipe(connection, "migration-test-week")
        _add_plan(connection, recipe_id, 7)
    return recipe_id


def _columns(database: MigrationDatabase, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(database.engine).get_columns(table)}


def _rejected(database: MigrationDatabase, statement: str, parameters: dict | None = None) -> None:
    with pytest.raises(sa.exc.IntegrityError), database.engine.begin() as connection:
        connection.execute(sa.text(statement), parameters or {})


def test_foundation_upgrade_adds_nullable_columns_and_keeps_every_row(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(PREVIOUS)
    recipe_id = _seed_week(migration_database)
    counts_before = _counts(migration_database)

    migration_database.upgrade(FOUNDATION)

    assert migration_database.current_revision() == FOUNDATION
    inspector = sa.inspect(migration_database.engine)
    for table, columns in NEW_COLUMNS.items():
        described = {column["name"]: column for column in inspector.get_columns(table)}
        assert columns <= described.keys(), table
        assert all(described[column]["nullable"] for column in columns), table
    assert _counts(migration_database) == counts_before
    with migration_database.engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM recipe_feedback")).scalar_one() == 0
        # No backfill: every new column of an existing row is NULL.
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM recipes WHERE meal_role IS NOT NULL OR owner_household_id IS NOT NULL")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(sa.text("SELECT count(*) FROM meal_plan_entries WHERE servings IS NULL")).scalar_one()
            == counts_before["meal_plan_entries"]
        )
        definitions = dict(
            connection.execute(
                sa.text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = ANY(:names)"),
                {"names": list(CHECKED_VALUES)},
            ).all()
        )
    for name, values in CHECKED_VALUES.items():
        assert set(re.findall(r"'([^']*)'", definitions[name])) == set(get_args(values)), name

    assert {index["name"] for index in inspector.get_indexes("recipes")} >= {
        "recipes_meal_role_idx",
        "recipes_owner_household_id_idx",
    }
    assert {index["name"] for index in inspector.get_indexes("recipe_feedback")} >= {
        "recipe_feedback_household_created_idx",
        "recipe_feedback_recipe_id_idx",
    }
    owner_key = next(
        key for key in inspector.get_foreign_keys("recipes") if key["name"] == "recipes_owner_household_id_fkey"
    )
    assert owner_key["referred_table"] == "households"
    assert owner_key["options"].get("ondelete") == "RESTRICT"

    with migration_database.engine.begin() as connection:
        _add_plan(connection, recipe_id, 14)
        connection.execute(
            sa.text(
                "INSERT INTO recipe_feedback (household_id, recipe_id, kind, source) "
                "VALUES (:household_id, :recipe_id, 'never_again', 'chat')"
            ),
            {"household_id": _household_id(connection), "recipe_id": recipe_id},
        )
        _add_recipe(connection, "migration-test-tagged", ", meal_role, halal_status", ", 'one_bowl', 'uncertain'")
    _rejected(
        migration_database,
        "INSERT INTO recipes (slug, title, description, cuisine, meal_type, servings, prep_time_minutes, "
        "cook_time_minutes, dietary_tags, meal_role) "
        "VALUES ('migration-test-poultry', 'x', 'x', 'x', 'dinner', 1, 1, 1, '[]', 'poultry')",
    )
    _rejected(
        migration_database,
        "INSERT INTO ingredients (normalized_name, display_name, allergens, halal_status) "
        "VALUES ('migration_test_meat', 'Meat', '[]', 'needs_certification')",
    )
    _rejected(migration_database, "UPDATE meal_plan_entries SET servings = 0")
    _rejected(migration_database, "UPDATE meal_plans SET day_count = 15")
    _rejected(migration_database, "UPDATE recipe_feedback SET kind = 'love'")
    _rejected(migration_database, "UPDATE recipe_feedback SET source = 'email'")


def test_foundation_downgrade_refuses_long_plans_then_restores_and_upgrades_again(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(PREVIOUS)
    recipe_id = _seed_week(migration_database)
    counts_before = _counts(migration_database)
    migration_database.upgrade(FOUNDATION)
    with migration_database.engine.begin() as connection:
        long_plan_id = _add_plan(connection, recipe_id, 14)

    # A 14-day plan blocks the rollback, which never deletes a household's plan to succeed.
    with pytest.raises(sa.exc.IntegrityError):
        migration_database.downgrade(PREVIOUS)
    assert migration_database.current_revision() == FOUNDATION
    assert NEW_COLUMNS["recipes"] <= _columns(migration_database, "recipes")

    with migration_database.engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM meal_plans WHERE id = :id"), {"id": long_plan_id})
    migration_database.downgrade(PREVIOUS)

    assert migration_database.current_revision() == PREVIOUS
    for table, columns in NEW_COLUMNS.items():
        assert not columns & _columns(migration_database, table), table
    assert "recipe_feedback" not in sa.inspect(migration_database.engine).get_table_names()
    assert _counts(migration_database) == counts_before
    with migration_database.engine.connect() as connection:
        names = set(connection.execute(sa.text("SELECT conname FROM pg_constraint")).scalars())
    assert {"meal_plans_day_count_seven", "meal_plan_entries_day_index_valid"} <= names
    assert "meal_plans_day_count_valid" not in names
    _rejected(migration_database, "UPDATE meal_plans SET day_count = 8")
    _rejected(migration_database, "UPDATE meal_plan_entries SET day_index = 8")

    migration_database.upgrade(FOUNDATION)
    assert migration_database.current_revision() == FOUNDATION
    for table, columns in NEW_COLUMNS.items():
        assert columns <= _columns(migration_database, table), table
    assert _counts(migration_database) == counts_before
