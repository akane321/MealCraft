"""Give a combined ingredient ("beef or turkey") the options it allows.

A recipe line that allows either of two ingredients is one combined ingredient in
release v2.1. The planner can keep such a recipe for a household that cannot eat
one option only if it knows the other: each option's name, display name and
allergens, copied here by the release import from data/ingredients/alternatives.json.
Null for every ordinary ingredient.

Revision ID: 20260924_0018
Revises: 20260922_0017
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0018"
down_revision: str | None = "20260922_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingredients", sa.Column("alternatives", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingredients", "alternatives")
