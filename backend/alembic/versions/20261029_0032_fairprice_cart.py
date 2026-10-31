"""FairPrice cart: the product id its cart takes, and what was sent to it (docs/design/fairprice-cart.md).

`product_snapshots.cart_item_id` is FairPrice's internal product id (the listing's `id`), not the `clientItemId`
kept as `external_id`; a cached price check keeps it. NULL is unknown, every row saved before this. `meal_plans.
fairprice_cart` holds what the person's browser extension reported per shopping trip ("1", "2"); NULL is nothing
sent. No data is backfilled.

Downgrade drops both columns; the cart record is only a note of what was sent, so nothing else is lost.

Revision ID: 20261029_0032
Revises: 20261019_0031
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261029_0032"
down_revision: str | None = "20261019_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product_snapshots", sa.Column("cart_item_id", sa.String(length=40), nullable=True))
    op.add_column("meal_plans", sa.Column("fairprice_cart", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_plans", "fairprice_cart")
    op.drop_column("product_snapshots", "cart_item_id")
