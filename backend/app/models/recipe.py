from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
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

BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("servings > 0", name="recipes_servings_positive"),
        CheckConstraint("prep_time_minutes >= 0", name="recipes_prep_time_nonnegative"),
        CheckConstraint("cook_time_minutes >= 0", name="recipes_cook_time_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    cuisine: Mapped[str] = mapped_column(String(80))
    meal_type: Mapped[str] = mapped_column(String(40), index=True)
    servings: Mapped[int]
    prep_time_minutes: Mapped[int]
    cook_time_minutes: Mapped[int]
    dietary_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    nutrition: Mapped["RecipeNutrition"] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        uselist=False,
    )
    recipe_ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.sort_order",
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeStep.step_number",
    )

    @property
    def total_time_minutes(self) -> int:
        return self.prep_time_minutes + self.cook_time_minutes


class RecipeNutrition(Base):
    __tablename__ = "recipe_nutrition"
    __table_args__ = (
        CheckConstraint("calories_kcal >= 0", name="recipe_nutrition_calories_nonnegative"),
        CheckConstraint("protein_g >= 0", name="recipe_nutrition_protein_nonnegative"),
        CheckConstraint("carbohydrate_g >= 0", name="recipe_nutrition_carbohydrate_nonnegative"),
        CheckConstraint("fat_g >= 0", name="recipe_nutrition_fat_nonnegative"),
        CheckConstraint("sodium_mg >= 0", name="recipe_nutrition_sodium_nonnegative"),
        CheckConstraint("sugar_g >= 0", name="recipe_nutrition_sugar_nonnegative"),
    )

    recipe_id: Mapped[int] = mapped_column(
        BIGINT_ID,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    sodium_mg: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    sugar_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))

    recipe: Mapped[Recipe] = relationship(back_populates="nutrition")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    allergen: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    recipe_ingredients: Mapped[list["RecipeIngredient"]] = relationship(back_populates="ingredient")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_id", "sort_order", name="recipe_ingredients_recipe_sort_key"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="recipe_ingredients_quantity_positive"),
        Index("recipe_ingredients_recipe_id_idx", "recipe_id"),
        Index("recipe_ingredients_ingredient_id_idx", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    recipe_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("recipes.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("ingredients.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    preparation: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sort_order: Mapped[int]

    recipe: Mapped[Recipe] = relationship(back_populates="recipe_ingredients")
    ingredient: Mapped[Ingredient] = relationship(back_populates="recipe_ingredients")


class RecipeStep(Base):
    __tablename__ = "recipe_steps"
    __table_args__ = (
        UniqueConstraint("recipe_id", "step_number", name="recipe_steps_recipe_step_key"),
        CheckConstraint("step_number > 0", name="recipe_steps_step_number_positive"),
        Index("recipe_steps_recipe_id_idx", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    recipe_id: Mapped[int] = mapped_column(BIGINT_ID, ForeignKey("recipes.id", ondelete="CASCADE"))
    step_number: Mapped[int]
    instruction: Mapped[str] = mapped_column(Text)

    recipe: Mapped[Recipe] = relationship(back_populates="steps")
