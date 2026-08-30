"""Add the recipe catalog and development fixtures.

Revision ID: 20260831_0002
Revises: 20260830_0001
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260831_0002"
down_revision: str | None = "20260830_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    recipes = op.create_table(
        "recipes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cuisine", sa.String(length=80), nullable=False),
        sa.Column("meal_type", sa.String(length=40), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("prep_time_minutes", sa.Integer(), nullable=False),
        sa.Column("cook_time_minutes", sa.Integer(), nullable=False),
        sa.Column("dietary_tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("servings > 0", name="recipes_servings_positive"),
        sa.CheckConstraint("prep_time_minutes >= 0", name="recipes_prep_time_nonnegative"),
        sa.CheckConstraint("cook_time_minutes >= 0", name="recipes_cook_time_nonnegative"),
    )
    op.create_index("ix_recipes_slug", "recipes", ["slug"], unique=True)
    op.create_index("ix_recipes_meal_type", "recipes", ["meal_type"])

    recipe_nutrition = op.create_table(
        "recipe_nutrition",
        sa.Column(
            "recipe_id",
            sa.BigInteger(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("calories_kcal", sa.Numeric(8, 2), nullable=False),
        sa.Column("protein_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("carbohydrate_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fat_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("sodium_mg", sa.Numeric(8, 2), nullable=False),
        sa.Column("sugar_g", sa.Numeric(8, 2), nullable=False),
        sa.CheckConstraint("calories_kcal >= 0", name="recipe_nutrition_calories_nonnegative"),
        sa.CheckConstraint("protein_g >= 0", name="recipe_nutrition_protein_nonnegative"),
        sa.CheckConstraint("carbohydrate_g >= 0", name="recipe_nutrition_carbohydrate_nonnegative"),
        sa.CheckConstraint("fat_g >= 0", name="recipe_nutrition_fat_nonnegative"),
        sa.CheckConstraint("sodium_mg >= 0", name="recipe_nutrition_sodium_nonnegative"),
        sa.CheckConstraint("sugar_g >= 0", name="recipe_nutrition_sugar_nonnegative"),
    )

    ingredients = op.create_table(
        "ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("allergen", sa.String(length=80), nullable=True),
    )
    op.create_index("ix_ingredients_normalized_name", "ingredients", ["normalized_name"], unique=True)
    op.create_index("ix_ingredients_allergen", "ingredients", ["allergen"])

    recipe_ingredients = op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "ingredient_id",
            sa.BigInteger(),
            sa.ForeignKey("ingredients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("preparation", sa.String(length=160), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name="recipe_ingredients_quantity_positive"),
        sa.UniqueConstraint("recipe_id", "sort_order", name="recipe_ingredients_recipe_sort_key"),
    )
    op.create_index("recipe_ingredients_recipe_id_idx", "recipe_ingredients", ["recipe_id"])
    op.create_index("recipe_ingredients_ingredient_id_idx", "recipe_ingredients", ["ingredient_id"])

    recipe_steps = op.create_table(
        "recipe_steps",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("recipe_id", sa.BigInteger(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.CheckConstraint("step_number > 0", name="recipe_steps_step_number_positive"),
        sa.UniqueConstraint("recipe_id", "step_number", name="recipe_steps_recipe_step_key"),
    )
    op.create_index("recipe_steps_recipe_id_idx", "recipe_steps", ["recipe_id"])

    op.bulk_insert(
        recipes,
        [
            {
                "id": 1,
                "slug": "lemon-herb-chicken-rice-bowl",
                "title": "Lemon Herb Chicken Rice Bowl",
                "description": "A balanced chicken and brown rice bowl with vegetables and lemon dressing.",
                "cuisine": "Mediterranean-inspired",
                "meal_type": "main",
                "servings": 2,
                "prep_time_minutes": 15,
                "cook_time_minutes": 25,
                "dietary_tags": ["high-protein", "low-sugar"],
            },
            {
                "id": 2,
                "slug": "tofu-vegetable-soba",
                "title": "Tofu Vegetable Soba",
                "description": "Crisp tofu, soba noodles and colourful vegetables with a light sesame-soy dressing.",
                "cuisine": "Japanese-inspired",
                "meal_type": "main",
                "servings": 2,
                "prep_time_minutes": 20,
                "cook_time_minutes": 20,
                "dietary_tags": ["vegetarian", "dairy-free"],
            },
            {
                "id": 3,
                "slug": "tomato-lentil-stew",
                "title": "Tomato Lentil Stew",
                "description": "A one-pot lentil stew with tomato, spinach and warming spices.",
                "cuisine": "Middle Eastern-inspired",
                "meal_type": "main",
                "servings": 4,
                "prep_time_minutes": 15,
                "cook_time_minutes": 35,
                "dietary_tags": ["vegan", "gluten-free", "high-fibre"],
            },
        ],
    )

    op.bulk_insert(
        recipe_nutrition,
        [
            {
                "recipe_id": 1,
                "calories_kcal": 540,
                "protein_g": 43,
                "carbohydrate_g": 58,
                "fat_g": 16,
                "sodium_mg": 620,
                "sugar_g": 8,
            },
            {
                "recipe_id": 2,
                "calories_kcal": 510,
                "protein_g": 25,
                "carbohydrate_g": 64,
                "fat_g": 18,
                "sodium_mg": 680,
                "sugar_g": 9,
            },
            {
                "recipe_id": 3,
                "calories_kcal": 430,
                "protein_g": 22,
                "carbohydrate_g": 67,
                "fat_g": 9,
                "sodium_mg": 520,
                "sugar_g": 11,
            },
        ],
    )

    op.bulk_insert(
        ingredients,
        [
            {"id": 1, "normalized_name": "chicken_breast", "display_name": "Chicken breast", "allergen": None},
            {"id": 2, "normalized_name": "brown_rice", "display_name": "Brown rice", "allergen": None},
            {"id": 3, "normalized_name": "lemon", "display_name": "Lemon", "allergen": None},
            {"id": 4, "normalized_name": "cucumber", "display_name": "Cucumber", "allergen": None},
            {"id": 5, "normalized_name": "cherry_tomato", "display_name": "Cherry tomatoes", "allergen": None},
            {"id": 6, "normalized_name": "olive_oil", "display_name": "Olive oil", "allergen": None},
            {"id": 7, "normalized_name": "firm_tofu", "display_name": "Firm tofu", "allergen": "soy"},
            {"id": 8, "normalized_name": "soba_noodle", "display_name": "Soba noodles", "allergen": "gluten"},
            {"id": 9, "normalized_name": "broccoli", "display_name": "Broccoli", "allergen": None},
            {"id": 10, "normalized_name": "carrot", "display_name": "Carrot", "allergen": None},
            {"id": 11, "normalized_name": "soy_sauce", "display_name": "Reduced-sodium soy sauce", "allergen": "soy"},
            {"id": 12, "normalized_name": "sesame_oil", "display_name": "Sesame oil", "allergen": "sesame"},
            {"id": 13, "normalized_name": "red_lentil", "display_name": "Red lentils", "allergen": None},
            {
                "id": 14,
                "normalized_name": "canned_tomato",
                "display_name": "No-added-salt canned tomatoes",
                "allergen": None,
            },
            {"id": 15, "normalized_name": "baby_spinach", "display_name": "Baby spinach", "allergen": None},
            {"id": 16, "normalized_name": "yellow_onion", "display_name": "Yellow onion", "allergen": None},
            {"id": 17, "normalized_name": "ground_cumin", "display_name": "Ground cumin", "allergen": None},
            {
                "id": 18,
                "normalized_name": "vegetable_stock",
                "display_name": "Low-sodium vegetable stock",
                "allergen": None,
            },
        ],
    )

    op.bulk_insert(
        recipe_ingredients,
        [
            {
                "recipe_id": 1,
                "ingredient_id": 1,
                "quantity": 300,
                "unit": "g",
                "preparation": "sliced",
                "sort_order": 1,
            },
            {
                "recipe_id": 1,
                "ingredient_id": 2,
                "quantity": 140,
                "unit": "g",
                "preparation": "rinsed",
                "sort_order": 2,
            },
            {
                "recipe_id": 1,
                "ingredient_id": 3,
                "quantity": 1,
                "unit": "whole",
                "preparation": "zested and juiced",
                "sort_order": 3,
            },
            {"recipe_id": 1, "ingredient_id": 4, "quantity": 120, "unit": "g", "preparation": "diced", "sort_order": 4},
            {
                "recipe_id": 1,
                "ingredient_id": 5,
                "quantity": 150,
                "unit": "g",
                "preparation": "halved",
                "sort_order": 5,
            },
            {"recipe_id": 1, "ingredient_id": 6, "quantity": 1, "unit": "tbsp", "preparation": None, "sort_order": 6},
            {
                "recipe_id": 2,
                "ingredient_id": 7,
                "quantity": 300,
                "unit": "g",
                "preparation": "pressed and cubed",
                "sort_order": 1,
            },
            {"recipe_id": 2, "ingredient_id": 8, "quantity": 160, "unit": "g", "preparation": None, "sort_order": 2},
            {
                "recipe_id": 2,
                "ingredient_id": 9,
                "quantity": 180,
                "unit": "g",
                "preparation": "cut into florets",
                "sort_order": 3,
            },
            {
                "recipe_id": 2,
                "ingredient_id": 10,
                "quantity": 1,
                "unit": "whole",
                "preparation": "julienned",
                "sort_order": 4,
            },
            {"recipe_id": 2, "ingredient_id": 11, "quantity": 2, "unit": "tbsp", "preparation": None, "sort_order": 5},
            {"recipe_id": 2, "ingredient_id": 12, "quantity": 1, "unit": "tsp", "preparation": None, "sort_order": 6},
            {
                "recipe_id": 3,
                "ingredient_id": 13,
                "quantity": 240,
                "unit": "g",
                "preparation": "rinsed",
                "sort_order": 1,
            },
            {"recipe_id": 3, "ingredient_id": 14, "quantity": 800, "unit": "g", "preparation": None, "sort_order": 2},
            {"recipe_id": 3, "ingredient_id": 15, "quantity": 150, "unit": "g", "preparation": None, "sort_order": 3},
            {
                "recipe_id": 3,
                "ingredient_id": 16,
                "quantity": 1,
                "unit": "whole",
                "preparation": "diced",
                "sort_order": 4,
            },
            {"recipe_id": 3, "ingredient_id": 17, "quantity": 2, "unit": "tsp", "preparation": None, "sort_order": 5},
            {"recipe_id": 3, "ingredient_id": 18, "quantity": 900, "unit": "ml", "preparation": None, "sort_order": 6},
        ],
    )

    op.bulk_insert(
        recipe_steps,
        [
            {
                "recipe_id": 1,
                "step_number": 1,
                "instruction": "Cook the brown rice according to the packet instructions and keep warm.",
            },
            {
                "recipe_id": 1,
                "step_number": 2,
                "instruction": (
                    "Coat the chicken with half the olive oil, lemon zest and black pepper, "
                    "then pan-sear until cooked through."
                ),
            },
            {
                "recipe_id": 1,
                "step_number": 3,
                "instruction": "Divide the rice, chicken and vegetables between bowls; finish with lemon juice.",
            },
            {
                "recipe_id": 2,
                "step_number": 1,
                "instruction": "Cook the soba noodles until just tender, rinse under cool water and drain well.",
            },
            {
                "recipe_id": 2,
                "step_number": 2,
                "instruction": "Sear the tofu, then add the broccoli and carrot and cook until crisp-tender.",
            },
            {
                "recipe_id": 2,
                "step_number": 3,
                "instruction": "Toss the noodles and vegetables with soy sauce and sesame oil, then serve warm.",
            },
            {
                "recipe_id": 3,
                "step_number": 1,
                "instruction": "Soften the onion in a large pot with a splash of water, then stir in the cumin.",
            },
            {
                "recipe_id": 3,
                "step_number": 2,
                "instruction": "Add the lentils, tomatoes and stock; simmer gently until the lentils are tender.",
            },
            {
                "recipe_id": 3,
                "step_number": 3,
                "instruction": "Fold in the spinach until wilted, adjust the consistency with water and serve.",
            },
        ],
    )

    op.execute("SELECT setval(pg_get_serial_sequence('recipes', 'id'), (SELECT max(id) FROM recipes), true)")
    op.execute("SELECT setval(pg_get_serial_sequence('ingredients', 'id'), (SELECT max(id) FROM ingredients), true)")


def downgrade() -> None:
    op.drop_index("recipe_steps_recipe_id_idx", table_name="recipe_steps")
    op.drop_table("recipe_steps")
    op.drop_index("recipe_ingredients_ingredient_id_idx", table_name="recipe_ingredients")
    op.drop_index("recipe_ingredients_recipe_id_idx", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
    op.drop_index("ix_ingredients_allergen", table_name="ingredients")
    op.drop_index("ix_ingredients_normalized_name", table_name="ingredients")
    op.drop_table("ingredients")
    op.drop_table("recipe_nutrition")
    op.drop_index("ix_recipes_meal_type", table_name="recipes")
    op.drop_index("ix_recipes_slug", table_name="recipes")
    op.drop_table("recipes")
