"""Link agent sessions to persistent replanning previews.

Revision ID: 20260901_0008
Revises: 20260901_0007
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0008"
down_revision: str | None = "20260901_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("replan_draft", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column("agent_sessions", sa.Column("pending_event_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "agent_sessions_pending_event_id_fkey",
        "agent_sessions",
        "meal_plan_events",
        ["pending_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("agent_sessions_pending_event_id_idx", "agent_sessions", ["pending_event_id"])


def downgrade() -> None:
    op.drop_index("agent_sessions_pending_event_id_idx", table_name="agent_sessions")
    op.drop_constraint("agent_sessions_pending_event_id_fkey", "agent_sessions", type_="foreignkey")
    op.drop_column("agent_sessions", "pending_event_id")
    op.drop_column("agent_sessions", "replan_draft")
