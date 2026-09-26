"""Catalog edits from the operations console (ADR-0047 Data).

recipes.withdrawn_at / withdrawn_reason: a recipe withdrawn from the console stays browsable and is never
planned, like the reviewed list in data/recipes/withdrawn.json. catalog_overrides: console edits over the
file-based knowledge (ingredient aliases and Chinese names, the FairPrice product mapping), one row per
edited ingredient and kind; the files stay the baseline. Every change is also written to audit_events.

It follows 20260927_0023 (runtime settings), the last revision on main when it landed.

Revision ID: 20260928_0025
Revises: 20260927_0023
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260928_0025"
down_revision: str | None = "20260927_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recipes", sa.Column("withdrawn_reason", sa.Text(), nullable=True))
    op.create_table(
        "catalog_overrides",
        sa.Column("kind", sa.String(length=40), primary_key=True),
        sa.Column("key", sa.String(length=160), primary_key=True),
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
    op.drop_table("catalog_overrides")
    op.drop_column("recipes", "withdrawn_reason")
    op.drop_column("recipes", "withdrawn_at")
