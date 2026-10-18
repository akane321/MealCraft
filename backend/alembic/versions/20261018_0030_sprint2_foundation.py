"""The Sprint 2 schema foundation: every column and table the Sprint 2 layers need, with no behaviour change.

Every new column is nullable and nothing reads or writes it yet; NULL is today's behaviour. Plan length
constraints are widened from 7 days to 1-14; requests still ask for 7. recipe_feedback is a new append-only
table. No data is backfilled. The contract is docs/design/sprint2-schema-foundation.md.

Downgrade removes all of it and restores day_count = 7 and day_index 1-7. It fails while a plan longer than
7 days exists, on purpose: it never deletes a household's plans to roll back.

Revision ID: 20261018_0030
Revises: 20261012_0029
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261018_0030"
down_revision: str | None = "20261012_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

# Frozen copies of the value lists in app/schemas/catalog_tags.py, as migrations must be.
MEAL_ROLE_CHECK = (
    "meal_role IS NULL OR meal_role IN ('protein_main', 'vegetable', 'soup', 'staple', 'one_bowl', "
    "'breakfast', 'salad', 'snack', 'dessert', 'sauce', 'drink')"
)
RECIPE_HALAL_CHECK = (
    "halal_status IS NULL OR halal_status IN ('halal', 'needs_certification', 'not_halal', 'uncertain')"
)
INGREDIENT_HALAL_CHECK = "halal_status IS NULL OR halal_status IN ('halal', 'not_halal', 'uncertain')"

PROFILE_COLUMNS = ("presence_rules", "cooking_time_rules", "missing_equipment", "missing_basics", "nutrition_limits")
RECIPE_JSON_COLUMNS = ("protein_sources", "cooking_methods", "flavor_tags", "equipment", "unknown_safety", "estimated")


def upgrade() -> None:
    # 1. Plans of 1 to 14 days.
    op.drop_constraint("meal_plans_day_count_seven", "meal_plans", type_="check")
    op.create_check_constraint("meal_plans_day_count_valid", "meal_plans", "day_count BETWEEN 1 AND 14")
    op.drop_constraint("meal_plan_entries_day_index_valid", "meal_plan_entries", type_="check")
    op.create_check_constraint("meal_plan_entries_day_index_valid", "meal_plan_entries", "day_index BETWEEN 1 AND 14")

    # 2. Servings a dish is cooked for.
    op.add_column("meal_plan_entries", sa.Column("servings", sa.Numeric(6, 3), nullable=True))
    op.create_check_constraint(
        "meal_plan_entries_servings_positive", "meal_plan_entries", "servings IS NULL OR servings > 0"
    )

    # 3. Household rules.
    for column in PROFILE_COLUMNS:
        op.add_column("household_profile_versions", sa.Column(column, sa.JSON(), nullable=True))

    # 4. Ingredient facts.
    op.add_column("ingredients", sa.Column("food_group", sa.String(length=80), nullable=True))
    op.add_column("ingredients", sa.Column("perishable", sa.Boolean(), nullable=True))
    op.add_column("ingredients", sa.Column("basic_seasoning", sa.Boolean(), nullable=True))
    op.add_column("ingredients", sa.Column("halal_status", sa.String(length=20), nullable=True))
    op.add_column("ingredients", sa.Column("nutrition_per_100g", sa.JSON(), nullable=True))
    op.add_column("ingredients", sa.Column("provenance", sa.JSON(), nullable=True))
    op.create_check_constraint("ingredients_halal_status_valid", "ingredients", INGREDIENT_HALAL_CHECK)

    # 5. Recipe tags and the provisional-recipe owner.
    op.add_column("recipes", sa.Column("meal_role", sa.String(length=20), nullable=True))
    op.add_column("recipes", sa.Column("contains_staple", sa.Boolean(), nullable=True))
    op.add_column("recipes", sa.Column("halal_status", sa.String(length=20), nullable=True))
    for column in RECIPE_JSON_COLUMNS:
        op.add_column("recipes", sa.Column(column, sa.JSON(), nullable=True))
    op.add_column("recipes", sa.Column("owner_household_id", BIGINT_ID, nullable=True))
    op.create_check_constraint("recipes_meal_role_valid", "recipes", MEAL_ROLE_CHECK)
    op.create_check_constraint("recipes_halal_status_valid", "recipes", RECIPE_HALAL_CHECK)
    op.create_index("recipes_meal_role_idx", "recipes", ["meal_role"])
    op.create_index("recipes_owner_household_id_idx", "recipes", ["owner_household_id"])
    op.create_foreign_key(
        "recipes_owner_household_id_fkey",
        "recipes",
        "households",
        ["owner_household_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 6. Ingredient-line provenance.
    op.add_column("recipe_ingredients", sa.Column("provenance", sa.JSON(), nullable=True))

    # 7. Product prices before promotion, and halal certification.
    op.add_column("product_snapshots", sa.Column("regular_price_sgd", sa.Numeric(10, 2), nullable=True))
    op.add_column("product_snapshots", sa.Column("halal_certified", sa.Boolean(), nullable=True))
    op.create_check_constraint(
        "product_snapshots_regular_price_nonnegative",
        "product_snapshots",
        "regular_price_sgd IS NULL OR regular_price_sgd >= 0",
    )

    # 8. Shopping lines grouped by store.
    op.add_column("meal_plan_grocery_items", sa.Column("retailer", sa.String(length=40), nullable=True))
    op.add_column("meal_plan_grocery_items", sa.Column("product_regular_price_sgd", sa.Numeric(10, 2), nullable=True))
    op.create_check_constraint(
        "meal_plan_grocery_regular_price_nonnegative",
        "meal_plan_grocery_items",
        "product_regular_price_sgd IS NULL OR product_regular_price_sgd >= 0",
    )

    # 9. Household feedback on recipes.
    op.create_table(
        "recipe_feedback",
        sa.Column("id", BIGINT_ID, sa.Identity(), nullable=False),
        sa.Column("household_id", BIGINT_ID, nullable=False),
        sa.Column("recipe_id", BIGINT_ID, nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('like', 'dislike', 'never_again')", name="recipe_feedback_kind_valid"),
        sa.CheckConstraint("source IN ('button', 'chat')", name="recipe_feedback_source_valid"),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name="recipe_feedback_household_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"], ["recipes.id"], name="recipe_feedback_recipe_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="recipe_feedback_pkey"),
    )
    op.create_index("recipe_feedback_household_created_idx", "recipe_feedback", ["household_id", "created_at", "id"])
    op.create_index("recipe_feedback_recipe_id_idx", "recipe_feedback", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("recipe_feedback_recipe_id_idx", table_name="recipe_feedback")
    op.drop_index("recipe_feedback_household_created_idx", table_name="recipe_feedback")
    op.drop_table("recipe_feedback")

    op.drop_constraint("meal_plan_grocery_regular_price_nonnegative", "meal_plan_grocery_items", type_="check")
    op.drop_column("meal_plan_grocery_items", "product_regular_price_sgd")
    op.drop_column("meal_plan_grocery_items", "retailer")

    op.drop_constraint("product_snapshots_regular_price_nonnegative", "product_snapshots", type_="check")
    op.drop_column("product_snapshots", "halal_certified")
    op.drop_column("product_snapshots", "regular_price_sgd")

    op.drop_column("recipe_ingredients", "provenance")

    op.drop_constraint("recipes_owner_household_id_fkey", "recipes", type_="foreignkey")
    op.drop_index("recipes_owner_household_id_idx", table_name="recipes")
    op.drop_index("recipes_meal_role_idx", table_name="recipes")
    op.drop_constraint("recipes_halal_status_valid", "recipes", type_="check")
    op.drop_constraint("recipes_meal_role_valid", "recipes", type_="check")
    op.drop_column("recipes", "owner_household_id")
    for column in reversed(RECIPE_JSON_COLUMNS):
        op.drop_column("recipes", column)
    op.drop_column("recipes", "halal_status")
    op.drop_column("recipes", "contains_staple")
    op.drop_column("recipes", "meal_role")

    op.drop_constraint("ingredients_halal_status_valid", "ingredients", type_="check")
    for column in ("provenance", "nutrition_per_100g", "halal_status", "basic_seasoning", "perishable", "food_group"):
        op.drop_column("ingredients", column)

    for column in reversed(PROFILE_COLUMNS):
        op.drop_column("household_profile_versions", column)

    op.drop_constraint("meal_plan_entries_servings_positive", "meal_plan_entries", type_="check")
    op.drop_column("meal_plan_entries", "servings")

    # Fails while a longer plan exists, rather than deleting it.
    op.drop_constraint("meal_plan_entries_day_index_valid", "meal_plan_entries", type_="check")
    op.create_check_constraint("meal_plan_entries_day_index_valid", "meal_plan_entries", "day_index BETWEEN 1 AND 7")
    op.drop_constraint("meal_plans_day_count_valid", "meal_plans", type_="check")
    op.create_check_constraint("meal_plans_day_count_seven", "meal_plans", "day_count = 7")
