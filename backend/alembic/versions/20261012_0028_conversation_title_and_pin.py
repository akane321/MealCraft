"""A conversation's own title and its pin.

Households rename and pin their conversations (2026-10-12, owner). Both are optional: a conversation without a
title shows its first message, and one without a pin sorts by when it last changed.

Revision ID: 20261012_0028
Revises: 20261003_0027
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0028"
down_revision: str | None = "20261003_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("title", sa.String(length=120), nullable=True))
    op.add_column("agent_sessions", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_sessions", "pinned_at")
    op.drop_column("agent_sessions", "title")
