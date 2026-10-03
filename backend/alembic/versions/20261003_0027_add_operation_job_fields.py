"""Add durable-job fields to operation runs.

The Operations Console reuses ``operation_runs`` as its PostgreSQL-backed job
queue.  These columns are only the persistence contract; claiming and renewing
leases belongs to the worker repository built on top of it.

Revision ID: 20261003_0027
Revises: 20260928_0026
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0027"
down_revision: str | None = "20260928_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operation_runs",
        sa.Column("job_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column("operation_runs", sa.Column("idempotency_key", sa.String(length=120), nullable=True))
    op.add_column(
        "operation_runs",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "operation_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "operation_runs_attempt_count_nonnegative",
        "operation_runs",
        "attempt_count >= 0",
    )
    op.create_unique_constraint(
        "operation_runs_actor_type_idempotency_key",
        "operation_runs",
        ["triggered_by_user_id", "run_type", "idempotency_key"],
    )
    op.create_index(
        "operation_runs_claimable_idx",
        "operation_runs",
        ["status", "lease_expires_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("operation_runs_claimable_idx", table_name="operation_runs")
    op.drop_constraint(
        "operation_runs_actor_type_idempotency_key",
        "operation_runs",
        type_="unique",
    )
    op.drop_constraint(
        "operation_runs_attempt_count_nonnegative",
        "operation_runs",
        type_="check",
    )
    op.drop_column("operation_runs", "lease_expires_at")
    op.drop_column("operation_runs", "attempt_count")
    op.drop_column("operation_runs", "idempotency_key")
    op.drop_column("operation_runs", "job_payload")
