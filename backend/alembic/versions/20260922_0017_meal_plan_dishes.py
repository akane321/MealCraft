"""Let a meal plan hold several meals a day and several dishes a meal (ADR-0036).

An entry was one dinner per day, keyed by (plan, day). It becomes one dish,
keyed by (plan, day, meal type, role), cooked at `portion_share` of the
household's servings. Existing entries are that day's dinner main at the whole
meal, which is exactly what they were.

A household profile version gains the meal composition it plans with; NULL is
one dish a meal, as before.

Revision ID: 20260922_0017
Revises: 20260921_0016
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0017"
down_revision: str | None = "20260921_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("meal_plan_entries") as batch:
        batch.add_column(sa.Column("meal_type", sa.String(length=20), nullable=False, server_default="dinner"))
        batch.add_column(sa.Column("role_id", sa.String(length=40), nullable=False, server_default="main"))
        batch.add_column(sa.Column("portion_share", sa.Numeric(4, 3), nullable=False, server_default="1"))
        batch.drop_constraint("meal_plan_entries_plan_day_key", type_="unique")
        batch.create_unique_constraint(
            "meal_plan_entries_plan_dish_key", ["plan_id", "day_index", "meal_type", "role_id"]
        )
        batch.create_check_constraint(
            "meal_plan_entries_meal_type_valid", "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')"
        )
        batch.create_check_constraint(
            "meal_plan_entries_portion_share_valid", "portion_share > 0 AND portion_share <= 1"
        )
    with op.batch_alter_table("household_profile_versions") as batch:
        batch.add_column(sa.Column("meal_composition", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("household_profile_versions") as batch:
        batch.drop_column("meal_composition")
    # Only one dish per day survives the old key: keep each day's dinner main.
    op.execute("DELETE FROM meal_plan_entries WHERE meal_type <> 'dinner' OR role_id <> 'main'")
    with op.batch_alter_table("meal_plan_entries") as batch:
        batch.drop_constraint("meal_plan_entries_portion_share_valid", type_="check")
        batch.drop_constraint("meal_plan_entries_meal_type_valid", type_="check")
        batch.drop_constraint("meal_plan_entries_plan_dish_key", type_="unique")
        batch.create_unique_constraint("meal_plan_entries_plan_day_key", ["plan_id", "day_index"])
        batch.drop_column("portion_share")
        batch.drop_column("role_id")
        batch.drop_column("meal_type")
