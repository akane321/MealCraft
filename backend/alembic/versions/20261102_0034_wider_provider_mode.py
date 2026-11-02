"""Wider provider_mode (docs/design/redmart.md, docs/design/manual-prices.md).

`operation_runs.provider_mode` and `agent_tool_executions.provider_mode` hold the sources a plan priced with, joined
by commas. With RedMart and the prices recorded by hand there are five product sources, and the joined value reaches
45 characters ("cold_storage,fairprice,fixture,manual,redmart"), past String(30). Both widen to String(64).

Downgrade narrows them again, cutting a longer saved value to its first 30 characters.

Revision ID: 20261102_0034
Revises: 20261031_0033
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0034"
down_revision: str | None = "20261031_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("operation_runs", "agent_tool_executions")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table, "provider_mode", existing_type=sa.String(30), type_=sa.String(64), existing_nullable=True
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "provider_mode",
            existing_type=sa.String(64),
            type_=sa.String(30),
            existing_nullable=True,
            postgresql_using="left(provider_mode, 30)",
        )
