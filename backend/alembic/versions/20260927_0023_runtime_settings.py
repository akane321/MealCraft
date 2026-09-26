"""Runtime settings the operations console can override (ADR-0047).

One row per registered key the console has changed; a key without a row uses the server default from
the environment. Every change is also written to audit_events with its before and after values.

RE-CHAIN AT MERGE: this revision is written against 20260926_0021 while another branch adds
20260926_0022 in parallel. When both land, set down_revision to that 0022 revision so Alembic keeps
a single head.

Revision ID: 20260927_0023
Revises: 20260926_0021
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0023"
down_revision: str | None = "20260926_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
