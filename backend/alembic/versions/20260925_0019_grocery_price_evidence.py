"""Record where each saved shopping-list price came from.

A plan's shopping lines are stored and read back from rows, so the provenance of each price (FairPrice
live, the cache, the reviewed snapshot or the fixture; the query; the parser version; when it was
observed) must be stored with them, or it is lost the moment the plan is saved. Null for lines saved
before this revision.

Revision ID: 20260925_0019
Revises: 20260924_0018
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_0019"
down_revision: str | None = "20260924_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("meal_plan_grocery_items", sa.Column("price_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("meal_plan_grocery_items", "price_evidence")
