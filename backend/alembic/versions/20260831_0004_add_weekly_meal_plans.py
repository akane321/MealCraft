"""Add persisted weekly meal plans and aggregated grocery items.

Revision ID: 20260831_0004
Revises: 20260831_0003
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0004"
down_revision: str | None = "20260831_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("day_count", sa.Integer(), nullable=False),
        sa.Column("household_size", sa.Integer(), nullable=False),
        sa.Column("pricing_mode", sa.String(length=20), nullable=False),
        sa.Column("budget_per_meal_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("weekly_budget_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("purchase_total_sgd", sa.Numeric(10, 2), nullable=False),
        sa.Column("consumed_total_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("within_weekly_budget", sa.Boolean(), nullable=True),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("day_count = 7", name="meal_plans_day_count_seven"),
        sa.CheckConstraint("household_size > 0", name="meal_plans_household_size_positive"),
        sa.CheckConstraint("pricing_mode IN ('fixture', 'live')", name="meal_plans_pricing_mode_valid"),
        sa.CheckConstraint(
            "budget_per_meal_sgd IS NULL OR budget_per_meal_sgd > 0",
            name="meal_plans_meal_budget_positive",
        ),
        sa.CheckConstraint(
            "weekly_budget_sgd IS NULL OR weekly_budget_sgd > 0",
            name="meal_plans_weekly_budget_positive",
        ),
        sa.CheckConstraint("purchase_total_sgd >= 0", name="meal_plans_purchase_total_nonnegative"),
        sa.CheckConstraint(
            "consumed_total_sgd IS NULL OR consumed_total_sgd >= 0",
            name="meal_plans_consumed_total_nonnegative",
        ),
    )
    op.create_index("meal_plans_start_created_idx", "meal_plans", ["start_date", "created_at"])

    op.create_table(
        "meal_plan_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("recommendation_score", sa.Numeric(5, 1), nullable=False),
        sa.Column("consumed_cost_sgd", sa.Numeric(10, 2), nullable=False),
        sa.Column("purchase_cost_sgd", sa.Numeric(10, 2), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(8, 2), nullable=False),
        sa.Column("protein_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("carbohydrate_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fat_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("sodium_mg", sa.Numeric(8, 2), nullable=False),
        sa.Column("sugar_g", sa.Numeric(8, 2), nullable=False),
        sa.CheckConstraint("day_index BETWEEN 1 AND 7", name="meal_plan_entries_day_index_valid"),
        sa.CheckConstraint("recommendation_score BETWEEN 0 AND 100", name="meal_plan_entries_score_valid"),
        sa.CheckConstraint("consumed_cost_sgd >= 0", name="meal_plan_entries_consumed_cost_nonnegative"),
        sa.CheckConstraint("purchase_cost_sgd >= 0", name="meal_plan_entries_purchase_cost_nonnegative"),
        sa.UniqueConstraint("plan_id", "day_index", name="meal_plan_entries_plan_day_key"),
    )
    op.create_index("meal_plan_entries_plan_id_idx", "meal_plan_entries", ["plan_id"])
    op.create_index("meal_plan_entries_recipe_id_idx", "meal_plan_entries", ["recipe_id"])

    op.create_table(
        "meal_plan_grocery_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingredient_name", sa.String(length=160), nullable=False),
        sa.Column("ingredient_display_name", sa.String(length=160), nullable=False),
        sa.Column("required_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("pantry_deduction", sa.Numeric(12, 3), nullable=False),
        sa.Column("remaining_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("product_external_id", sa.Text(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("product_brand", sa.Text(), nullable=True),
        sa.Column("product_category", sa.Text(), nullable=True),
        sa.Column("product_package_size", sa.Numeric(12, 3), nullable=True),
        sa.Column("product_package_unit", sa.Text(), nullable=True),
        sa.Column("product_price_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("product_image_url", sa.Text(), nullable=True),
        sa.Column("product_source", sa.String(length=20), nullable=True),
        sa.Column("product_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_score", sa.Numeric(5, 3), nullable=True),
        sa.Column("packages_required", sa.Integer(), nullable=False),
        sa.Column("purchase_cost_sgd", sa.Numeric(10, 2), nullable=False),
        sa.Column("consumed_cost_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("excess_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "required_quantity IS NULL OR required_quantity >= 0",
            name="meal_plan_grocery_required_nonnegative",
        ),
        sa.CheckConstraint("pantry_deduction >= 0", name="meal_plan_grocery_pantry_nonnegative"),
        sa.CheckConstraint(
            "remaining_quantity IS NULL OR remaining_quantity >= 0",
            name="meal_plan_grocery_remaining_nonnegative",
        ),
        sa.CheckConstraint("packages_required >= 0", name="meal_plan_grocery_packages_nonnegative"),
        sa.CheckConstraint("purchase_cost_sgd >= 0", name="meal_plan_grocery_purchase_nonnegative"),
        sa.UniqueConstraint("plan_id", "ingredient_name", name="meal_plan_grocery_plan_ingredient_key"),
    )
    op.create_index("meal_plan_grocery_plan_id_idx", "meal_plan_grocery_items", ["plan_id"])


def downgrade() -> None:
    op.drop_index("meal_plan_grocery_plan_id_idx", table_name="meal_plan_grocery_items")
    op.drop_table("meal_plan_grocery_items")
    op.drop_index("meal_plan_entries_recipe_id_idx", table_name="meal_plan_entries")
    op.drop_index("meal_plan_entries_plan_id_idx", table_name="meal_plan_entries")
    op.drop_table("meal_plan_entries")
    op.drop_index("meal_plans_start_created_idx", table_name="meal_plans")
    op.drop_table("meal_plans")
