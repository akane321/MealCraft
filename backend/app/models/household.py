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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.recipe import BIGINT_ID


class HouseholdProfile(Base):
    __tablename__ = "household_profiles"
    __table_args__ = (
        CheckConstraint("current_version > 0", name="household_profiles_current_version_positive"),
        Index("household_profiles_updated_idx", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["HouseholdProfileVersion"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="HouseholdProfileVersion.version",
    )


class HouseholdProfileVersion(Base):
    __tablename__ = "household_profile_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="household_profile_versions_version_positive"),
        CheckConstraint(
            "planning_household_size BETWEEN 1 AND 12",
            name="household_profile_versions_household_size_valid",
        ),
        CheckConstraint(
            "max_cooking_time_minutes BETWEEN 5 AND 240",
            name="household_profile_versions_cooking_time_valid",
        ),
        CheckConstraint(
            "budget_per_meal_sgd IS NULL OR budget_per_meal_sgd > 0",
            name="household_profile_versions_meal_budget_positive",
        ),
        CheckConstraint(
            "weekly_budget_sgd IS NULL OR weekly_budget_sgd > 0",
            name="household_profile_versions_weekly_budget_positive",
        ),
        CheckConstraint(
            "max_sodium_mg_per_meal IS NULL OR max_sodium_mg_per_meal > 0",
            name="household_profile_versions_sodium_positive",
        ),
        CheckConstraint(
            "pricing_mode IN ('fixture', 'live')",
            name="household_profile_versions_pricing_mode_valid",
        ),
        UniqueConstraint("profile_id", "version", name="household_profile_versions_profile_version_key"),
        Index("household_profile_versions_profile_idx", "profile_id", "version"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("household_profiles.id", ondelete="CASCADE"),
    )
    version: Mapped[int] = mapped_column(Integer)
    members: Mapped[list[dict]] = mapped_column(JSON)
    planning_household_size: Mapped[int] = mapped_column(Integer)
    max_cooking_time_minutes: Mapped[int] = mapped_column(Integer)
    budget_per_meal_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    weekly_budget_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    allergens: Mapped[list[str]] = mapped_column(JSON)
    excluded_ingredients: Mapped[list[str]] = mapped_column(JSON)
    dietary_preferences: Mapped[list[str]] = mapped_column(JSON)
    health_preferences: Mapped[list[str]] = mapped_column(JSON)
    nutrition_targets: Mapped[dict] = mapped_column(JSON)
    max_sodium_mg_per_meal: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    available_ingredients: Mapped[list[dict]] = mapped_column(JSON)
    pricing_mode: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[HouseholdProfile] = relationship(back_populates="versions")
