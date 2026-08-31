"""Add cached product snapshots.

Revision ID: 20260831_0003
Revises: 20260831_0002
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0003"
down_revision: str | None = "20260831_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("package_size", sa.Numeric(12, 3), nullable=True),
        sa.Column("package_unit", sa.Text(), nullable=True),
        sa.Column("price_sgd", sa.Numeric(10, 2), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "package_size IS NULL OR package_size > 0",
            name="product_snapshots_package_size_positive",
        ),
        sa.CheckConstraint("price_sgd >= 0", name="product_snapshots_price_nonnegative"),
        sa.CheckConstraint("rank >= 0", name="product_snapshots_rank_nonnegative"),
        sa.UniqueConstraint(
            "source",
            "search_query",
            "external_id",
            name="product_snapshots_source_query_external_key",
        ),
    )
    op.create_index(
        "product_snapshots_source_query_fetched_idx",
        "product_snapshots",
        ["source", "search_query", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("product_snapshots_source_query_fetched_idx", table_name="product_snapshots")
    op.drop_table("product_snapshots")
