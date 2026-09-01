from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
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
from app.models.recipe import BIGINT_ID, Recipe


class MealPlan(Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        CheckConstraint("day_count = 7", name="meal_plans_day_count_seven"),
        CheckConstraint("household_size > 0", name="meal_plans_household_size_positive"),
        CheckConstraint("pricing_mode IN ('fixture', 'live')", name="meal_plans_pricing_mode_valid"),
        CheckConstraint(
            "budget_per_meal_sgd IS NULL OR budget_per_meal_sgd > 0",
            name="meal_plans_meal_budget_positive",
        ),
        CheckConstraint(
            "weekly_budget_sgd IS NULL OR weekly_budget_sgd > 0",
            name="meal_plans_weekly_budget_positive",
        ),
        CheckConstraint("purchase_total_sgd >= 0", name="meal_plans_purchase_total_nonnegative"),
        CheckConstraint(
            "consumed_total_sgd IS NULL OR consumed_total_sgd >= 0",
            name="meal_plans_consumed_total_nonnegative",
        ),
        Index("meal_plans_start_created_idx", "start_date", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    day_count: Mapped[int] = mapped_column(Integer, default=7)
    household_size: Mapped[int] = mapped_column(Integer)
    pricing_mode: Mapped[str] = mapped_column(String(20))
    budget_per_meal_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    weekly_budget_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_total_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    consumed_total_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    within_weekly_budget: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    constraints: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["MealPlanEntry"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="MealPlanEntry.day_index",
    )
    grocery_items: Mapped[list["MealPlanGroceryItem"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="MealPlanGroceryItem.ingredient_name",
    )
    events: Mapped[list["MealPlanEvent"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="MealPlanEvent.id",
    )


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"
    __table_args__ = (
        CheckConstraint("day_index BETWEEN 1 AND 7", name="meal_plan_entries_day_index_valid"),
        CheckConstraint("recommendation_score BETWEEN 0 AND 100", name="meal_plan_entries_score_valid"),
        CheckConstraint("consumed_cost_sgd >= 0", name="meal_plan_entries_consumed_cost_nonnegative"),
        CheckConstraint("purchase_cost_sgd >= 0", name="meal_plan_entries_purchase_cost_nonnegative"),
        CheckConstraint(
            "status IN ('planned', 'completed', 'skipped')",
            name="meal_plan_entries_status_valid",
        ),
        CheckConstraint(
            "(status = 'completed' AND consumed_at IS NOT NULL) "
            "OR (status IN ('planned', 'skipped') AND consumed_at IS NULL)",
            name="meal_plan_entries_consumed_at_consistent",
        ),
        UniqueConstraint("plan_id", "day_index", name="meal_plan_entries_plan_day_key"),
        Index("meal_plan_entries_plan_id_idx", "plan_id"),
        Index("meal_plan_entries_recipe_id_idx", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    plan_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("meal_plans.id", ondelete="CASCADE"))
    recipe_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("recipes.id", ondelete="RESTRICT"))
    day_index: Mapped[int] = mapped_column(Integer)
    planned_date: Mapped[date] = mapped_column(Date)
    recommendation_score: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    consumed_cost_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    purchase_cost_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    sodium_mg: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    sugar_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    status: Mapped[str] = mapped_column(String(20), default="planned", server_default="planned")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[MealPlan] = relationship(back_populates="entries")
    recipe: Mapped[Recipe] = relationship()


class MealPlanGroceryItem(Base):
    __tablename__ = "meal_plan_grocery_items"
    __table_args__ = (
        CheckConstraint(
            "required_quantity IS NULL OR required_quantity >= 0",
            name="meal_plan_grocery_required_nonnegative",
        ),
        CheckConstraint("pantry_deduction >= 0", name="meal_plan_grocery_pantry_nonnegative"),
        CheckConstraint(
            "remaining_quantity IS NULL OR remaining_quantity >= 0",
            name="meal_plan_grocery_remaining_nonnegative",
        ),
        CheckConstraint("packages_required >= 0", name="meal_plan_grocery_packages_nonnegative"),
        CheckConstraint("purchase_cost_sgd >= 0", name="meal_plan_grocery_purchase_nonnegative"),
        UniqueConstraint("plan_id", "ingredient_name", name="meal_plan_grocery_plan_ingredient_key"),
        Index("meal_plan_grocery_plan_id_idx", "plan_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    plan_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("meal_plans.id", ondelete="CASCADE"))
    ingredient_name: Mapped[str] = mapped_column(String(160))
    ingredient_display_name: Mapped[str] = mapped_column(String(160))
    required_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pantry_deduction: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    remaining_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    product_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_package_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    product_package_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_price_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    product_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 3), nullable=True)
    packages_required: Mapped[int] = mapped_column(Integer)
    purchase_cost_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    consumed_cost_sgd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    excess_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[MealPlan] = relationship(back_populates="grocery_items")


class MealPlanEvent(Base):
    __tablename__ = "meal_plan_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('REPLACE_MEAL', 'CANCEL_MEAL', 'LOCK_MEAL', 'ITEM_UNAVAILABLE')",
            name="meal_plan_events_type_valid",
        ),
        CheckConstraint(
            "status IN ('previewed', 'applied')",
            name="meal_plan_events_status_valid",
        ),
        CheckConstraint("base_revision > 0", name="meal_plan_events_base_revision_positive"),
        CheckConstraint(
            "applied_revision IS NULL OR applied_revision > base_revision",
            name="meal_plan_events_applied_revision_valid",
        ),
        Index("meal_plan_events_plan_created_idx", "plan_id", "created_at", "id"),
        Index("meal_plan_events_entry_id_idx", "entry_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    plan_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("meal_plans.id", ondelete="CASCADE"))
    entry_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("meal_plan_entries.id", ondelete="CASCADE"))
    proposed_recipe_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("recipes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="previewed", server_default="previewed")
    base_revision: Mapped[int] = mapped_column(Integer)
    applied_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    unavailable_ingredient: Mapped[str | None] = mapped_column(String(160), nullable=True)
    before_entry: Mapped[dict] = mapped_column(JSON)
    after_entry: Mapped[dict] = mapped_column(JSON)
    after_grocery: Mapped[dict] = mapped_column(JSON)
    after_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    nutrition_delta: Mapped[dict] = mapped_column(JSON)
    grocery_delta: Mapped[list[dict]] = mapped_column(JSON, default=list)
    purchase_total_delta_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[MealPlan] = relationship(back_populates="events")
    entry: Mapped[MealPlanEntry] = relationship()
    proposed_recipe: Mapped[Recipe | None] = relationship()
