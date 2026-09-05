from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.recipe import BIGINT_ID


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_verification', 'active', 'suspended', 'deleted')",
            name="users_status_valid",
        ),
        CheckConstraint(
            "system_role IN ('ordinary_user', 'data_reviewer', 'operator', 'admin')",
            name="users_system_role_valid",
        ),
        Index("users_status_created_idx", "status", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    locale: Mapped[str] = mapped_column(String(20), default="en-SG", server_default="en-SG")
    timezone: Mapped[str] = mapped_column(
        String(80),
        default="Asia/Singapore",
        server_default="Asia/Singapore",
    )
    status: Mapped[str] = mapped_column(String(30), default="active", server_default="active")
    system_role: Mapped[str] = mapped_column(
        String(30),
        default="ordinary_user",
        server_default="ordinary_user",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    credential: Mapped[UserCredential | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    household_memberships: Mapped[list[HouseholdMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"
    __table_args__ = (CheckConstraint("failed_login_count >= 0", name="user_credentials_failed_count_nonnegative"),)

    user_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="credential")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("auth_sessions_user_expiry_idx", "user_id", "expires_at", "id"),
        Index("auth_sessions_active_expiry_idx", "revoked_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="auth_sessions")


class Household(Base):
    __tablename__ = "households"
    __table_args__ = (Index("households_created_idx", "created_at", "id"),)

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_by_user_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list[HouseholdMembership]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )


class HouseholdMembership(Base):
    __tablename__ = "household_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'editor', 'member', 'viewer')",
            name="household_memberships_role_valid",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'removed')",
            name="household_memberships_status_valid",
        ),
        Index("household_memberships_user_status_idx", "user_id", "status", "household_id"),
    )

    household_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("households.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    household: Mapped[Household] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="household_memberships")


class OperationRun(Base):
    __tablename__ = "operation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'degraded')",
            name="operation_runs_status_valid",
        ),
        Index("operation_runs_type_created_idx", "run_type", "created_at", "id"),
        Index("operation_runs_status_created_idx", "status", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(80), unique=True)
    run_type: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    household_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("households.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_snapshot_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    algorithm_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    artifact_references: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_events_target_created_idx", "target_type", "target_id", "created_at", "id"),
        Index("audit_events_actor_created_idx", "actor_user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
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
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    before_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
