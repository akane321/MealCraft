"""Add persistent agent sessions and messages.

Revision ID: 20260901_0006
Revises: 20260831_0005
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0006"
down_revision: str | None = "20260831_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="collecting", nullable=False),
        sa.Column("parser_provider", sa.String(length=20), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=False),
        sa.Column("clarification_questions", sa.JSON(), nullable=False),
        sa.Column("acknowledged_unknown_quantities", sa.JSON(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('collecting', 'ready', 'planned')",
            name="agent_sessions_status_valid",
        ),
        sa.CheckConstraint(
            "parser_provider IN ('fixture', 'openai')",
            name="agent_sessions_parser_provider_valid",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("agent_sessions_updated_id_idx", "agent_sessions", ["updated_at", "id"])
    op.create_index("agent_sessions_plan_id_idx", "agent_sessions", ["plan_id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="agent_messages_role_valid",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "agent_messages_session_created_idx",
        "agent_messages",
        ["session_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("agent_messages_session_created_idx", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("agent_sessions_plan_id_idx", table_name="agent_sessions")
    op.drop_index("agent_sessions_updated_id_idx", table_name="agent_sessions")
    op.drop_table("agent_sessions")
