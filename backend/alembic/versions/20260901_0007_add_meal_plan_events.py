"""Add meal-plan revisions, locks, and persistent replanning events.

Revision ID: 20260901_0007
Revises: 20260901_0006
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0007"
down_revision: str | None = "20260901_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meal_plans",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("is_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "meal_plan_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("proposed_recipe_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="previewed", nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("unavailable_ingredient", sa.String(length=160), nullable=True),
        sa.Column("before_entry", sa.JSON(), nullable=False),
        sa.Column("after_entry", sa.JSON(), nullable=False),
        sa.Column("after_grocery", sa.JSON(), nullable=False),
        sa.Column("after_warnings", sa.JSON(), nullable=False),
        sa.Column("nutrition_delta", sa.JSON(), nullable=False),
        sa.Column("grocery_delta", sa.JSON(), nullable=False),
        sa.Column("purchase_total_delta_sgd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('REPLACE_MEAL', 'CANCEL_MEAL', 'LOCK_MEAL', 'ITEM_UNAVAILABLE')",
            name="meal_plan_events_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('previewed', 'applied')",
            name="meal_plan_events_status_valid",
        ),
        sa.CheckConstraint("base_revision > 0", name="meal_plan_events_base_revision_positive"),
        sa.CheckConstraint(
            "applied_revision IS NULL OR applied_revision > base_revision",
            name="meal_plan_events_applied_revision_valid",
        ),
        sa.ForeignKeyConstraint(["entry_id"], ["meal_plan_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_recipe_id"], ["recipes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "meal_plan_events_plan_created_idx",
        "meal_plan_events",
        ["plan_id", "created_at", "id"],
    )
    op.create_index("meal_plan_events_entry_id_idx", "meal_plan_events", ["entry_id"])


def downgrade() -> None:
    op.drop_index("meal_plan_events_entry_id_idx", table_name="meal_plan_events")
    op.drop_index("meal_plan_events_plan_created_idx", table_name="meal_plan_events")
    op.drop_table("meal_plan_events")
    op.drop_column("meal_plan_entries", "is_locked")
    op.drop_column("meal_plans", "revision")
