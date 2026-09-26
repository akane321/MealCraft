"""Store which meals a household plans and each meal's dishes (ADR-0046).

A profile version gains `plan_shape`: meal type -> dish roles. The older single
`meal_composition` stays readable as a dinner-only shape. Null for versions saved before.

Revision ID: 20260926_0022
Revises: 20260926_0021
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260926_0022"
down_revision: str | None = "20260926_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("household_profile_versions", sa.Column("plan_shape", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("household_profile_versions", "plan_shape")
