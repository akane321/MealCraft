"""Add execution status to persisted meal-plan entries.

Revision ID: 20260831_0005
Revises: 20260831_0004
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0005"
down_revision: str | None = "20260831_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meal_plan_entries",
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "meal_plan_entries_status_valid",
        "meal_plan_entries",
        "status IN ('planned', 'completed', 'skipped')",
    )
    op.create_check_constraint(
        "meal_plan_entries_consumed_at_consistent",
        "meal_plan_entries",
        "(status = 'completed' AND consumed_at IS NOT NULL) "
        "OR (status IN ('planned', 'skipped') AND consumed_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "meal_plan_entries_consumed_at_consistent",
        "meal_plan_entries",
        type_="check",
    )
    op.drop_constraint(
        "meal_plan_entries_status_valid",
        "meal_plan_entries",
        type_="check",
    )
    op.drop_column("meal_plan_entries", "consumed_at")
    op.drop_column("meal_plan_entries", "status")
