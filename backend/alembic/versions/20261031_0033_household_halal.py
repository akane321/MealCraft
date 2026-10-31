"""Household halal switch (docs/design/halal.md; Knowledge ADR-0104).

`household_profile_versions.requires_halal` is the whole household's switch, saved with each profile version like
every other limit: true plans only halal dishes and buys meat only from products FairPrice marks Halal. Every
version saved before this is false, which is what it planned as.

It also adds `meal_plan_grocery_items.product_halal_certified` (nullable), so a saved plan keeps FairPrice's Halal
mark on each chosen product; NULL is unknown and every line saved before this stays unknown, never halal.

Downgrade drops both columns; a household that had switched halal on plans ordinary meals again.

Revision ID: 20261031_0033
Revises: 20261029_0032
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261031_0033"
down_revision: str | None = "20261029_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "household_profile_versions",
        sa.Column("requires_halal", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("meal_plan_grocery_items", sa.Column("product_halal_certified", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_plan_grocery_items", "product_halal_certified")
    op.drop_column("household_profile_versions", "requires_halal")
