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


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"
    __table_args__ = (
        CheckConstraint("day_index BETWEEN 1 AND 7", name="meal_plan_entries_day_index_valid"),
        CheckConstraint("recommendation_score BETWEEN 0 AND 100", name="meal_plan_entries_score_valid"),
        CheckConstraint("consumed_cost_sgd >= 0", name="meal_plan_entries_consumed_cost_nonnegative"),
        CheckConstraint("purchase_cost_sgd >= 0", name="meal_plan_entries_purchase_cost_nonnegative"),
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
