"""Add account, household tenancy, operations, and audit foundations.

Revision ID: 20260906_0010
Revises: 20260902_0009
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260906_0010"
down_revision: str | None = "20260902_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("locale", sa.String(length=20), server_default="en-SG", nullable=False),
        sa.Column("timezone", sa.String(length=80), server_default="Asia/Singapore", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="active", nullable=False),
        sa.Column("system_role", sa.String(length=30), server_default="ordinary_user", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_verification', 'active', 'suspended', 'deleted')",
            name="users_status_valid",
        ),
        sa.CheckConstraint(
            "system_role IN ('ordinary_user', 'data_reviewer', 'operator', 'admin')",
            name="users_system_role_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_email"),
    )
    op.create_index("users_status_created_idx", "users", ["status", "created_at", "id"])

    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "failed_login_count >= 0",
            name="user_credentials_failed_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "households",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("households_created_idx", "households", ["created_at", "id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "auth_sessions_user_expiry_idx",
        "auth_sessions",
        ["user_id", "expires_at", "id"],
    )
    op.create_index(
        "auth_sessions_active_expiry_idx",
        "auth_sessions",
        ["revoked_at", "expires_at"],
    )

    op.create_table(
        "household_memberships",
        sa.Column("household_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'member', 'viewer')",
            name="household_memberships_role_valid",
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'removed')",
            name="household_memberships_status_valid",
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("household_id", "user_id"),
    )
    op.create_index(
        "household_memberships_user_status_idx",
        "household_memberships",
        ["user_id", "status", "household_id"],
    )

    op.create_table(
        "operation_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("run_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("triggered_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("input_digest", sa.String(length=64), nullable=True),
        sa.Column("code_commit", sa.String(length=64), nullable=True),
        sa.Column("catalog_version", sa.String(length=120), nullable=True),
        sa.Column("product_snapshot_version", sa.String(length=120), nullable=True),
        sa.Column("policy_version", sa.String(length=120), nullable=True),
        sa.Column("algorithm_version", sa.String(length=120), nullable=True),
        sa.Column("provider_mode", sa.String(length=30), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("artifact_references", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'degraded')",
            name="operation_runs_status_valid",
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id"),
    )
    op.create_index(
        "operation_runs_type_created_idx",
        "operation_runs",
        ["run_type", "created_at", "id"],
    )
    op.create_index(
        "operation_runs_status_created_idx",
        "operation_runs",
        ["status", "created_at", "id"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=True),
        sa.Column("before_digest", sa.String(length=64), nullable=True),
        sa.Column("after_digest", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "audit_events_target_created_idx",
        "audit_events",
        ["target_type", "target_id", "created_at", "id"],
    )
    op.create_index(
        "audit_events_actor_created_idx",
        "audit_events",
        ["actor_user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("audit_events_actor_created_idx", table_name="audit_events")
    op.drop_index("audit_events_target_created_idx", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("operation_runs_status_created_idx", table_name="operation_runs")
    op.drop_index("operation_runs_type_created_idx", table_name="operation_runs")
    op.drop_table("operation_runs")
    op.drop_index("household_memberships_user_status_idx", table_name="household_memberships")
    op.drop_table("household_memberships")
    op.drop_index("auth_sessions_active_expiry_idx", table_name="auth_sessions")
    op.drop_index("auth_sessions_user_expiry_idx", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("households_created_idx", table_name="households")
    op.drop_table("households")
    op.drop_table("user_credentials")
    op.drop_index("users_status_created_idx", table_name="users")
    op.drop_table("users")
