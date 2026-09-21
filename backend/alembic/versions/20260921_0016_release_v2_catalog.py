"""Hold release v2 recipes next to the curated catalog.

Release v2 (data-engineering/data/release/v2/) carries fields the curated
30-recipe catalog never had: course, difficulty, passive time, a recipe-level
allergen list, the basis of servings and times, source and licence, and a gram
weight for every ingredient line. The curated recipes keep NULL in all of them.

`catalog_imports` records which release was imported and the digest of its
files, so the importer can skip a release it has already loaded.

Revision ID: 20260921_0016
Revises: 20260919_0015
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0016"
down_revision: str | None = "20260919_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch:
        batch.add_column(sa.Column("release_version", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("external_id", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("course", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("meal_types", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("difficulty", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("passive_time_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("time_basis", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("servings_basis", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("allergens", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("source", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("video_url", sa.String(length=500), nullable=True))
        batch.create_index("ix_recipes_release_version", ["release_version"])
        batch.create_unique_constraint("recipes_external_id_key", ["external_id"])
        batch.create_check_constraint(
            "recipes_passive_time_nonnegative", "passive_time_minutes IS NULL OR passive_time_minutes >= 0"
        )
    with op.batch_alter_table("recipe_ingredients") as batch:
        batch.add_column(sa.Column("grams", sa.Numeric(10, 2), nullable=True))
        batch.add_column(sa.Column("original_text", sa.Text(), nullable=True))
    op.create_table(
        "catalog_imports",
        sa.Column("release_version", sa.String(length=20), primary_key=True),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("recipe_count", sa.Integer(), nullable=False),
        sa.Column("ingredient_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("catalog_imports")
    op.execute("DELETE FROM recipes WHERE release_version IS NOT NULL")
    with op.batch_alter_table("recipe_ingredients") as batch:
        batch.drop_column("original_text")
        batch.drop_column("grams")
    with op.batch_alter_table("recipes") as batch:
        batch.drop_constraint("recipes_passive_time_nonnegative", type_="check")
        batch.drop_constraint("recipes_external_id_key", type_="unique")
        batch.drop_index("ix_recipes_release_version")
        for column in (
            "video_url",
            "source",
            "allergens",
            "servings_basis",
            "time_basis",
            "passive_time_minutes",
            "difficulty",
            "meal_types",
            "course",
            "external_id",
            "release_version",
        ):
            batch.drop_column(column)
