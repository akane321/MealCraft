"""Add versioned household profiles and link them to meal plans.

Revision ID: 20260902_0009
Revises: 20260901_0008
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0009"
down_revision: str | None = "20260901_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_profiles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("current_version > 0", name="household_profiles_current_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("household_profiles_updated_idx", "household_profiles", ["updated_at", "id"])

    op.create_table(
        "household_profile_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("planning_household_size", sa.Integer(), nullable=False),
        sa.Column("max_cooking_time_minutes", sa.Integer(), nullable=False),
        sa.Column("budget_per_meal_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("weekly_budget_sgd", sa.Numeric(10, 2), nullable=True),
        sa.Column("allergens", sa.JSON(), nullable=False),
        sa.Column("excluded_ingredients", sa.JSON(), nullable=False),
        sa.Column("dietary_preferences", sa.JSON(), nullable=False),
        sa.Column("health_preferences", sa.JSON(), nullable=False),
        sa.Column("nutrition_targets", sa.JSON(), nullable=False),
        sa.Column("max_sodium_mg_per_meal", sa.Numeric(8, 2), nullable=True),
        sa.Column("available_ingredients", sa.JSON(), nullable=False),
        sa.Column("pricing_mode", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="household_profile_versions_version_positive"),
        sa.CheckConstraint(
            "planning_household_size BETWEEN 1 AND 12",
            name="household_profile_versions_household_size_valid",
        ),
        sa.CheckConstraint(
            "max_cooking_time_minutes BETWEEN 5 AND 240",
            name="household_profile_versions_cooking_time_valid",
        ),
        sa.CheckConstraint(
            "budget_per_meal_sgd IS NULL OR budget_per_meal_sgd > 0",
            name="household_profile_versions_meal_budget_positive",
        ),
        sa.CheckConstraint(
            "weekly_budget_sgd IS NULL OR weekly_budget_sgd > 0",
            name="household_profile_versions_weekly_budget_positive",
        ),
        sa.CheckConstraint(
            "max_sodium_mg_per_meal IS NULL OR max_sodium_mg_per_meal > 0",
            name="household_profile_versions_sodium_positive",
        ),
        sa.CheckConstraint(
            "pricing_mode IN ('fixture', 'live')",
            name="household_profile_versions_pricing_mode_valid",
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["household_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "version", name="household_profile_versions_profile_version_key"),
    )
    op.create_index(
        "household_profile_versions_profile_idx",
        "household_profile_versions",
        ["profile_id", "version"],
    )

    op.add_column("meal_plans", sa.Column("household_profile_id", sa.BigInteger(), nullable=True))
    op.add_column("meal_plans", sa.Column("household_profile_version", sa.Integer(), nullable=True))
    op.add_column("meal_plans", sa.Column("replaces_plan_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "meal_plans_household_profile_version_fkey",
        "meal_plans",
        "household_profile_versions",
        ["household_profile_id", "household_profile_version"],
        ["profile_id", "version"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "meal_plans_replaces_plan_id_fkey",
        "meal_plans",
        "meal_plans",
        ["replaces_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "meal_plans_household_profile_reference_consistent",
        "meal_plans",
        "(household_profile_id IS NULL AND household_profile_version IS NULL) "
        "OR (household_profile_id IS NOT NULL AND household_profile_version IS NOT NULL)",
    )
    op.create_index(
        "meal_plans_household_profile_idx",
        "meal_plans",
        ["household_profile_id", "household_profile_version"],
    )


def downgrade() -> None:
    op.drop_index("meal_plans_household_profile_idx", table_name="meal_plans")
    op.drop_constraint("meal_plans_household_profile_reference_consistent", "meal_plans", type_="check")
    op.drop_constraint("meal_plans_replaces_plan_id_fkey", "meal_plans", type_="foreignkey")
    op.drop_constraint("meal_plans_household_profile_version_fkey", "meal_plans", type_="foreignkey")
    op.drop_column("meal_plans", "replaces_plan_id")
    op.drop_column("meal_plans", "household_profile_version")
    op.drop_column("meal_plans", "household_profile_id")
    op.drop_index("household_profile_versions_profile_idx", table_name="household_profile_versions")
    op.drop_table("household_profile_versions")
    op.drop_index("household_profiles_updated_idx", table_name="household_profiles")
    op.drop_table("household_profiles")
