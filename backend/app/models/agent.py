from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.recipe import BIGINT_ID


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting', 'ready', 'planned')",
            name="agent_sessions_status_valid",
        ),
        CheckConstraint(
            "parser_provider IN ('fixture', 'openai')",
            name="agent_sessions_parser_provider_valid",
        ),
        Index("agent_sessions_updated_id_idx", "updated_at", "id"),
        Index("agent_sessions_plan_id_idx", "plan_id"),
        Index("agent_sessions_pending_event_id_idx", "pending_event_id"),
        Index("agent_sessions_latest_run_id_idx", "latest_run_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="collecting", server_default="collecting")
    parser_provider: Mapped[str] = mapped_column(String(20))
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    clarification_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    acknowledged_unknown_quantities: Mapped[list[str]] = mapped_column(JSON, default=list)
    replan_draft: Mapped[dict] = mapped_column(JSON, default=dict)
    context_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_scope_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pending_interaction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latest_run_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("agent_runs.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    plan_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("meal_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    pending_event_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("meal_plan_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.id",
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="AgentRun.agent_session_id",
        order_by="AgentRun.id",
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="agent_messages_role_valid",
        ),
        Index("agent_messages_session_created_idx", "session_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[AgentSession] = relationship(back_populates="messages")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'needs_clarification', 'ready_for_confirmation', 'running', "
            "'preview_ready', 'committed', 'degraded', 'failed', 'cancelled')",
            name="agent_runs_status_valid",
        ),
        CheckConstraint("context_version > 0", name="agent_runs_context_version_positive"),
        CheckConstraint("checkpoint_version >= 0", name="agent_runs_checkpoint_version_nonnegative"),
        CheckConstraint("max_llm_calls >= 0 AND used_llm_calls >= 0", name="agent_runs_llm_budget_nonnegative"),
        CheckConstraint("used_llm_calls <= max_llm_calls", name="agent_runs_llm_budget_within_limit"),
        CheckConstraint("max_tool_calls >= 0 AND used_tool_calls >= 0", name="agent_runs_tool_budget_nonnegative"),
        CheckConstraint("used_tool_calls <= max_tool_calls", name="agent_runs_tool_budget_within_limit"),
        CheckConstraint(
            "max_retrieval_retries >= 0 AND used_retrieval_retries >= 0",
            name="agent_runs_retrieval_budget_nonnegative",
        ),
        CheckConstraint(
            "used_retrieval_retries <= max_retrieval_retries",
            name="agent_runs_retrieval_budget_within_limit",
        ),
        CheckConstraint(
            "max_planning_attempts >= 0 AND used_planning_attempts >= 0",
            name="agent_runs_planning_budget_nonnegative",
        ),
        CheckConstraint(
            "used_planning_attempts <= max_planning_attempts",
            name="agent_runs_planning_budget_within_limit",
        ),
        CheckConstraint("max_wall_seconds > 0", name="agent_runs_wall_budget_positive"),
        CheckConstraint(
            "max_api_cost_usd IS NULL OR max_api_cost_usd >= 0",
            name="agent_runs_api_cost_budget_nonnegative",
        ),
        CheckConstraint("used_api_cost_usd >= 0", name="agent_runs_api_cost_used_nonnegative"),
        CheckConstraint(
            "max_api_cost_usd IS NULL OR used_api_cost_usd <= max_api_cost_usd",
            name="agent_runs_api_cost_within_limit",
        ),
        UniqueConstraint("agent_session_id", "idempotency_key", name="agent_runs_session_idempotency_key"),
        Index("agent_runs_session_created_idx", "agent_session_id", "created_at", "id"),
        Index("agent_runs_status_updated_idx", "status", "updated_at", "id"),
        Index("agent_runs_household_created_idx", "household_id", "created_at", "id"),
        Index("agent_runs_actor_created_idx", "actor_user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    agent_session_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    household_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("households.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120))
    intent: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="created", server_default="created")
    input_digest: Mapped[str] = mapped_column(String(64))
    context_version: Mapped[int] = mapped_column(Integer)
    plan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_llm_calls: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    used_llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    used_tool_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_retrieval_retries: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    used_retrieval_retries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_planning_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    used_planning_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_wall_seconds: Mapped[int] = mapped_column(Integer, default=120, server_default="120")
    max_api_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    used_api_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), server_default="0")
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    termination_reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    session: Mapped[AgentSession] = relationship(back_populates="runs", foreign_keys=[agent_session_id])
    checkpoints: Mapped[list["AgentRunCheckpoint"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRunCheckpoint.sequence",
    )
    tool_executions: Mapped[list["AgentToolExecution"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentToolExecution.sequence",
    )


class AgentRunCheckpoint(Base):
    __tablename__ = "agent_run_checkpoints"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="agent_run_checkpoints_sequence_positive"),
        UniqueConstraint("agent_run_id", "sequence", name="agent_run_checkpoints_run_sequence_key"),
        Index("agent_run_checkpoints_run_created_idx", "agent_run_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("agent_runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40))
    state_digest: Mapped[str] = mapped_column(String(64))
    state_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_references: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[AgentRun] = relationship(back_populates="checkpoints")


class AgentToolExecution(Base):
    __tablename__ = "agent_tool_executions"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="agent_tool_executions_sequence_positive"),
        CheckConstraint("effect IN ('read', 'preview', 'commit')", name="agent_tool_executions_effect_valid"),
        CheckConstraint("status IN ('succeeded', 'failed')", name="agent_tool_executions_status_valid"),
        UniqueConstraint("agent_run_id", "sequence", name="agent_tool_executions_run_sequence_key"),
        Index("agent_tool_executions_run_created_idx", "agent_run_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("agent_runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(120))
    effect: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    arguments_digest: Mapped[str] = mapped_column(String(64))
    result_reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    provider_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[AgentRun] = relationship(back_populates="tool_executions")
