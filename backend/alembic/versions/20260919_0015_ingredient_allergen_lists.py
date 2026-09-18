"""Store every checked allergen an ingredient contains, not at most one.

A single nullable column could not say that soy sauce contains soy and gluten,
and it could not tell "checked, none" from "never checked". The list holds each
allergen from the checked vocabulary (data/ingredients/allergen-vocabulary.json)
the ingredient contains; the catalog import rewrites it on every run.

Revision ID: 20260919_0015
Revises: 20260916_0014
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0015"
down_revision: str | None = "20260916_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ingredients = sa.table(
    "ingredients",
    sa.column("id", sa.BigInteger()),
    sa.column("allergen", sa.String()),
    sa.column("allergens", sa.JSON()),
)


def upgrade() -> None:
    op.add_column("ingredients", sa.Column("allergens", sa.JSON(), nullable=True))
    bind = op.get_bind()
    for row in bind.execute(sa.select(ingredients.c.id, ingredients.c.allergen)).all():
        bind.execute(
            ingredients.update()
            .where(ingredients.c.id == row.id)
            .values(allergens=[row.allergen] if row.allergen else [])
        )
    with op.batch_alter_table("ingredients") as batch:
        batch.alter_column("allergens", existing_type=sa.JSON(), nullable=False)
        batch.drop_index("ix_ingredients_allergen")
        batch.drop_column("allergen")


def downgrade() -> None:
    op.add_column("ingredients", sa.Column("allergen", sa.String(length=80), nullable=True))
    bind = op.get_bind()
    # Lossy by nature: an ingredient with several allergens keeps only one.
    for row in bind.execute(sa.select(ingredients.c.id, ingredients.c.allergens)).all():
        values = sorted(row.allergens or [])
        bind.execute(
            ingredients.update().where(ingredients.c.id == row.id).values(allergen=values[0] if values else None)
        )
    with op.batch_alter_table("ingredients") as batch:
        batch.create_index("ix_ingredients_allergen", ["allergen"])
        batch.drop_column("allergens")
