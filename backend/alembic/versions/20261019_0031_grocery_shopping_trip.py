"""Grocery lines of a plan's second shopping trip, and the perishable mark (layer 08 PR-3).

A plan longer than 7 days shops twice, before day 1 and before day 8 (ADR-0072), so one ingredient can have a
line on each trip. `shopping_trip` is 1 or 2; NULL is the plan's only trip, every existing line. The unique key on
(plan, ingredient, unit) becomes a unique index on (plan, COALESCE(shopping_trip, 1), ingredient, unit), which
keeps one line per ingredient and unit per trip. `perishable` marks a line to use within 3 days of its trip; NULL
is not marked. No data is backfilled.

Downgrade drops both columns and restores the key. It fails while a plan has a second trip's line for an
ingredient its first trip also buys, on purpose: it never deletes a household's list to roll back.

Revision ID: 20261019_0031
Revises: 20261018_0030
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261019_0031"
down_revision: str | None = "20261018_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "meal_plan_grocery_items"
OLD_KEY = "meal_plan_grocery_plan_ingredient_unit_key"
NEW_KEY = "meal_plan_grocery_plan_trip_ingredient_unit_key"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("shopping_trip", sa.SmallInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("perishable", sa.Boolean(), nullable=True))
    op.create_check_constraint(
        "meal_plan_grocery_shopping_trip_valid", TABLE, "shopping_trip IS NULL OR shopping_trip IN (1, 2)"
    )
    op.drop_constraint(OLD_KEY, TABLE, type_="unique")
    op.create_index(
        NEW_KEY,
        TABLE,
        ["plan_id", sa.text("COALESCE(shopping_trip, 1)"), "ingredient_name", "unit"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(NEW_KEY, table_name=TABLE)
    op.create_unique_constraint(OLD_KEY, TABLE, ["plan_id", "ingredient_name", "unit"])
    op.drop_constraint("meal_plan_grocery_shopping_trip_valid", TABLE, type_="check")
    op.drop_column(TABLE, "perishable")
    op.drop_column(TABLE, "shopping_trip")
