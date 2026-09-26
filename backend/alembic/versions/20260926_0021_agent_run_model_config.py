"""Record which parser and models produced each agent run.

A run's result depends on the parser (rule-based or a live model), the model name and, for the live
model, the embedding vectors it compares against. Stored per run so a result can be traced back to its
configuration; never a key or a prompt. Null for runs made before this revision.

Revision ID: 20260926_0021
Revises: 20260926_0020
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260926_0021"
down_revision: str | None = "20260926_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "model_config")
