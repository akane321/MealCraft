"""A week's shopping list holds one line per ingredient and unit.

The weekly grocery estimate keeps lines whose units cannot be added (whole eggs and grams of egg)
apart since release v2.1, but the stored list allowed one line per ingredient, so confirming a
change that needed both failed. The flag of a week whose checkout total passed its weekly budget
after a change is corrected too: it was compared with the ingredient-use cost.

Revision ID: 20260928_0026
Revises: 20260928_0025
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260928_0026"
down_revision: str | None = "20260928_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("meal_plan_grocery_plan_ingredient_key", "meal_plan_grocery_items", type_="unique")
    op.create_unique_constraint(
        "meal_plan_grocery_plan_ingredient_unit_key",
        "meal_plan_grocery_items",
        ["plan_id", "ingredient_name", "unit"],
    )
    op.execute(
        "UPDATE meal_plans SET within_weekly_budget = false "
        "WHERE weekly_budget_sgd IS NOT NULL AND purchase_total_sgd > weekly_budget_sgd"
    )


def downgrade() -> None:
    # Fails while a stored list holds one ingredient in two units; those weeks must be removed first.
    op.drop_constraint("meal_plan_grocery_plan_ingredient_unit_key", "meal_plan_grocery_items", type_="unique")
    op.create_unique_constraint(
        "meal_plan_grocery_plan_ingredient_key",
        "meal_plan_grocery_items",
        ["plan_id", "ingredient_name"],
    )
