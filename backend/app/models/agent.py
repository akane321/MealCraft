from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func
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
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="collecting", server_default="collecting")
    parser_provider: Mapped[str] = mapped_column(String(20))
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    clarification_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    acknowledged_unknown_quantities: Mapped[list[str]] = mapped_column(JSON, default=list)
    replan_draft: Mapped[dict] = mapped_column(JSON, default=dict)
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
