"""Add bounded orchestration state to agent sessions.

Revision ID: 20260906_0011
Revises: 20260906_0010
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260906_0011"
down_revision: str | None = "20260906_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("context_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("agent_sessions", sa.Column("last_scope_decision", sa.JSON(), nullable=True))
    op.add_column("agent_sessions", sa.Column("pending_interaction", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_sessions", "pending_interaction")
    op.drop_column("agent_sessions", "last_scope_decision")
    op.drop_column("agent_sessions", "context_version")
