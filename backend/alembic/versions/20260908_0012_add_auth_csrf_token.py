"""Add per-session CSRF token digests and an active-session index.

Revision ID: 20260908_0012
Revises: 20260906_0011
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0012"
down_revision: str | None = "20260906_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable preserves existing sessions during the staged migration. Those
    # sessions remain read-only because CSRF-protected mutations fail closed.
    op.add_column("auth_sessions", sa.Column("csrf_token_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "auth_sessions_user_active_idx",
        "auth_sessions",
        ["user_id", "expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("auth_sessions_user_active_idx", table_name="auth_sessions")
    op.drop_column("auth_sessions", "csrf_token_hash")
