import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep

SUPPORTED_UNITS = {"g", "kg", "ml", "l", "tbsp", "tsp", "whole", "pc", "pcs"}


class IngredientRecord(BaseModel):
    normalized_name: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    display_name: str = Field(min_length=1, max_length=160)
    allergen: str | None = Field(default=None, max_length=80)


class NutritionRecord(BaseModel):
    calories_kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    sodium_mg: float = Field(ge=0)
    sugar_g: float = Field(ge=0)


class RecipeIngredientRecord(BaseModel):
    ingredient: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    quantity: float = Field(gt=0)
    unit: str
    preparation: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_unit(self) -> "RecipeIngredientRecord":
        if self.unit not in SUPPORTED_UNITS:
            raise ValueError(f"unsupported unit: {self.unit}")
        return self


class RecipeRecord(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    cuisine: str = Field(min_length=1, max_length=80)
    meal_type: str = Field(default="main", min_length=1, max_length=40)
    servings: int = Field(gt=0)
    prep_time_minutes: int = Field(ge=0)
    cook_time_minutes: int = Field(ge=0)
    dietary_tags: list[str] = Field(default_factory=list)
    nutrition: NutritionRecord
    ingredients: list[RecipeIngredientRecord] = Field(min_length=2)
    steps: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_recipe(self) -> "RecipeRecord":
        ingredient_names = [item.ingredient for item in self.ingredients]
        if len(ingredient_names) != len(set(ingredient_names)):
            raise ValueError(f"recipe {self.slug} contains a duplicate ingredient")
        if any(not step.strip() for step in self.steps):
            raise ValueError(f"recipe {self.slug} contains a blank step")
        return self


class Catalog(BaseModel):
    ingredients: list[IngredientRecord]
    recipes: list[RecipeRecord]

    @model_validator(mode="after")
    def validate_references(self) -> "Catalog":
        ingredient_names = [item.normalized_name for item in self.ingredients]
        recipe_slugs = [item.slug for item in self.recipes]
        if len(ingredient_names) != len(set(ingredient_names)):
            raise ValueError("ingredient normalized_name values must be unique")
        if len(recipe_slugs) != len(set(recipe_slugs)):
            raise ValueError("recipe slug values must be unique")
        known = set(ingredient_names)
        missing = sorted({item.ingredient for recipe in self.recipes for item in recipe.ingredients}.difference(known))
        if missing:
            raise ValueError(f"recipes reference unknown ingredients: {', '.join(missing)}")
        return self


def load_catalog(ingredient_path: Path, recipe_path: Path) -> Catalog:
    ingredients = json.loads(ingredient_path.read_text(encoding="utf-8"))
    recipes = json.loads(recipe_path.read_text(encoding="utf-8"))
    return Catalog.model_validate({"ingredients": ingredients, "recipes": recipes})


def import_catalog(session: Session, catalog: Catalog) -> tuple[int, int]:
    ingredients_by_name: dict[str, Ingredient] = {}
    for record in catalog.ingredients:
        ingredient = session.scalar(select(Ingredient).where(Ingredient.normalized_name == record.normalized_name))
        if ingredient is None:
            ingredient = Ingredient(normalized_name=record.normalized_name)
            session.add(ingredient)
        ingredient.display_name = record.display_name
        ingredient.allergen = record.allergen
        ingredients_by_name[record.normalized_name] = ingredient
    session.flush()

    for record in catalog.recipes:
        recipe = session.scalar(select(Recipe).where(Recipe.slug == record.slug))
        if recipe is None:
            recipe = Recipe(slug=record.slug)
            session.add(recipe)
        recipe.title = record.title
        recipe.description = record.description
        recipe.cuisine = record.cuisine
        recipe.meal_type = record.meal_type
        recipe.servings = record.servings
        recipe.prep_time_minutes = record.prep_time_minutes
        recipe.cook_time_minutes = record.cook_time_minutes
        recipe.dietary_tags = record.dietary_tags

        if recipe.nutrition is None:
            recipe.nutrition = RecipeNutrition()
        for field, value in record.nutrition.model_dump().items():
            setattr(recipe.nutrition, field, value)

        recipe.recipe_ingredients.clear()
        recipe.steps.clear()
        session.flush()
        recipe.recipe_ingredients.extend(
            RecipeIngredient(
                ingredient=ingredients_by_name[item.ingredient],
                quantity=item.quantity,
                unit=item.unit,
                preparation=item.preparation,
                sort_order=index,
            )
            for index, item in enumerate(record.ingredients, start=1)
        )
        recipe.steps.extend(
            RecipeStep(step_number=index, instruction=instruction.strip())
            for index, instruction in enumerate(record.steps, start=1)
        )

    session.commit()
    return len(catalog.ingredients), len(catalog.recipes)
