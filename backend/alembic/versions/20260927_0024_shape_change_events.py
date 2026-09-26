"""Let a plan event add, drop or recompose a meal over some days (ADR-0046 section 2).

A CHANGE_SHAPE event touches several dishes, so it has no single entry; its proposal
is kept in `shape_change`.

Revision ID: 20260927_0024
Revises: 20260926_0022
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0024"
down_revision: str | None = "20260926_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = "'REPLACE_MEAL', 'CANCEL_MEAL', 'LOCK_MEAL', 'ITEM_UNAVAILABLE'"


def upgrade() -> None:
    op.add_column("meal_plan_events", sa.Column("shape_change", sa.JSON(), nullable=True))
    op.alter_column("meal_plan_events", "entry_id", existing_type=sa.BigInteger(), nullable=True)
    op.drop_constraint("meal_plan_events_type_valid", "meal_plan_events", type_="check")
    op.create_check_constraint(
        "meal_plan_events_type_valid", "meal_plan_events", f"event_type IN ({OLD_TYPES}, 'CHANGE_SHAPE')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM meal_plan_events WHERE event_type = 'CHANGE_SHAPE'")
    op.drop_constraint("meal_plan_events_type_valid", "meal_plan_events", type_="check")
    op.create_check_constraint("meal_plan_events_type_valid", "meal_plan_events", f"event_type IN ({OLD_TYPES})")
    op.alter_column("meal_plan_events", "entry_id", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("meal_plan_events", "shape_change")
