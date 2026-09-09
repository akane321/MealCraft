"""Add durable Agent runs, checkpoints, and tool execution receipts.

Revision ID: 20260909_0013
Revises: 20260908_0012
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260909_0013"
down_revision: str | None = "20260908_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("agent_session_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="created", nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=True),
        sa.Column("scope_decision", sa.JSON(), nullable=True),
        sa.Column("checkpoint_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_llm_calls", sa.Integer(), server_default="2", nullable=False),
        sa.Column("used_llm_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), server_default="8", nullable=False),
        sa.Column("used_tool_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retrieval_retries", sa.Integer(), server_default="2", nullable=False),
        sa.Column("used_retrieval_retries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_planning_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("used_planning_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_wall_seconds", sa.Integer(), server_default="120", nullable=False),
        sa.Column("max_api_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("used_api_cost_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("termination_reason_code", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'needs_clarification', 'ready_for_confirmation', 'running', "
            "'preview_ready', 'committed', 'degraded', 'failed', 'cancelled')",
            name="agent_runs_status_valid",
        ),
        sa.CheckConstraint("context_version > 0", name="agent_runs_context_version_positive"),
        sa.CheckConstraint("checkpoint_version >= 0", name="agent_runs_checkpoint_version_nonnegative"),
        sa.CheckConstraint("max_llm_calls >= 0 AND used_llm_calls >= 0", name="agent_runs_llm_budget_nonnegative"),
        sa.CheckConstraint("used_llm_calls <= max_llm_calls", name="agent_runs_llm_budget_within_limit"),
        sa.CheckConstraint("max_tool_calls >= 0 AND used_tool_calls >= 0", name="agent_runs_tool_budget_nonnegative"),
        sa.CheckConstraint("used_tool_calls <= max_tool_calls", name="agent_runs_tool_budget_within_limit"),
        sa.CheckConstraint(
            "max_retrieval_retries >= 0 AND used_retrieval_retries >= 0",
            name="agent_runs_retrieval_budget_nonnegative",
        ),
        sa.CheckConstraint(
            "used_retrieval_retries <= max_retrieval_retries",
            name="agent_runs_retrieval_budget_within_limit",
        ),
        sa.CheckConstraint(
            "max_planning_attempts >= 0 AND used_planning_attempts >= 0",
            name="agent_runs_planning_budget_nonnegative",
        ),
        sa.CheckConstraint(
            "used_planning_attempts <= max_planning_attempts",
            name="agent_runs_planning_budget_within_limit",
        ),
        sa.CheckConstraint("max_wall_seconds > 0", name="agent_runs_wall_budget_positive"),
        sa.CheckConstraint(
            "max_api_cost_usd IS NULL OR max_api_cost_usd >= 0",
            name="agent_runs_api_cost_budget_nonnegative",
        ),
        sa.CheckConstraint("used_api_cost_usd >= 0", name="agent_runs_api_cost_used_nonnegative"),
        sa.CheckConstraint(
            "max_api_cost_usd IS NULL OR used_api_cost_usd <= max_api_cost_usd",
            name="agent_runs_api_cost_within_limit",
        ),
        sa.ForeignKeyConstraint(["agent_session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_session_id", "idempotency_key", name="agent_runs_session_idempotency_key"),
    )
    op.create_index("agent_runs_session_created_idx", "agent_runs", ["agent_session_id", "created_at", "id"])
    op.create_index("agent_runs_status_updated_idx", "agent_runs", ["status", "updated_at", "id"])
    op.create_index("agent_runs_household_created_idx", "agent_runs", ["household_id", "created_at", "id"])
    op.create_index("agent_runs_actor_created_idx", "agent_runs", ["actor_user_id", "created_at", "id"])

    op.create_table(
        "agent_run_checkpoints",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("agent_run_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("state_digest", sa.String(length=64), nullable=False),
        sa.Column("state_payload", sa.JSON(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="agent_run_checkpoints_sequence_positive"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", "sequence", name="agent_run_checkpoints_run_sequence_key"),
    )
    op.create_index(
        "agent_run_checkpoints_run_created_idx",
        "agent_run_checkpoints",
        ["agent_run_id", "created_at", "id"],
    )

    op.create_table(
        "agent_tool_executions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("agent_run_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("effect", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("arguments_digest", sa.String(length=64), nullable=False),
        sa.Column("result_reference", sa.String(length=240), nullable=True),
        sa.Column("provider_mode", sa.String(length=30), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="agent_tool_executions_sequence_positive"),
        sa.CheckConstraint("effect IN ('read', 'preview', 'commit')", name="agent_tool_executions_effect_valid"),
        sa.CheckConstraint("status IN ('succeeded', 'failed')", name="agent_tool_executions_status_valid"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", "sequence", name="agent_tool_executions_run_sequence_key"),
    )
    op.create_index(
        "agent_tool_executions_run_created_idx",
        "agent_tool_executions",
        ["agent_run_id", "created_at", "id"],
    )

    op.add_column("agent_sessions", sa.Column("latest_run_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "agent_sessions_latest_run_id_fkey",
        "agent_sessions",
        "agent_runs",
        ["latest_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("agent_sessions_latest_run_id_idx", "agent_sessions", ["latest_run_id"])


def downgrade() -> None:
    op.drop_index("agent_sessions_latest_run_id_idx", table_name="agent_sessions")
    op.drop_constraint("agent_sessions_latest_run_id_fkey", "agent_sessions", type_="foreignkey")
    op.drop_column("agent_sessions", "latest_run_id")
    op.drop_index("agent_tool_executions_run_created_idx", table_name="agent_tool_executions")
    op.drop_table("agent_tool_executions")
    op.drop_index("agent_run_checkpoints_run_created_idx", table_name="agent_run_checkpoints")
    op.drop_table("agent_run_checkpoints")
    op.drop_index("agent_runs_actor_created_idx", table_name="agent_runs")
    op.drop_index("agent_runs_household_created_idx", table_name="agent_runs")
    op.drop_index("agent_runs_status_updated_idx", table_name="agent_runs")
    op.drop_index("agent_runs_session_created_idx", table_name="agent_runs")
    op.drop_table("agent_runs")
