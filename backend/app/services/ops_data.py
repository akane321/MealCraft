"""The catalog for the operations console (ADR-0047 Data): recipes, ingredients and product mappings.

Recipe fields and ingredient display names are database columns and are edited in place. Aliases, Chinese
names and the FairPrice mapping live in reviewed files; an edit is a catalog_overrides row laid over the
file (app/data/overrides.py). Allergens stay rule-derived and are never edited here. Every change writes
an audit row with its before and after values.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.agent.ingredient_matcher import ALIASES, ZH_ALIASES, alias_file
from app.data import overrides as catalog_overrides
from app.models.platform import AuditEvent, CatalogOverride
from app.models.recipe import Ingredient, Recipe, RecipeIngredient
from app.planning.grocery_estimator import release_products, release_snapshot
from app.repositories import recipe as recipe_repo
from app.repositories.recipe import withdrawn_reasons, withdrawn_slugs
from app.schemas.operations import (
    OpsIngredient,
    OpsIngredientCollection,
    OpsIngredientUpdate,
    OpsMappedProduct,
    OpsProductMapping,
    OpsProductMappingCollection,
    OpsRecipeCollection,
    OpsRecipeDetail,
    OpsRecipeSummary,
    OpsRecipeUpdate,
)


class OpsDataNotFoundError(LookupError):
    pass


class OpsDataConflictError(ValueError):
    pass


def _planning_changed() -> None:
    # The planner keeps its candidates for a few minutes; an edit must reach the next plan.
    recipe_repo.clear_planning_pool()


def _names(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class DataService:
    def __init__(self, database: Session, *, actor_user_id: int) -> None:
        self.database = database
        self.actor_user_id = actor_user_id

    # --- recipes ---

    def recipes(
        self,
        *,
        query: str | None,
        course: str | None,
        meal_type: str | None,
        origin: str | None,
        withdrawn: bool | None,
        offset: int,
        limit: int,
    ) -> OpsRecipeCollection:
        filters = []
        if query:
            pattern = f"%{query.strip().casefold()}%"
            filters.append(or_(func.lower(Recipe.title).like(pattern), Recipe.slug.like(pattern)))
        if course:
            filters.append(Recipe.course == course)
        if meal_type:
            # meal_types is a JSON list; its text holds each value in quotes on SQLite and Postgres alike.
            filters.append(cast(Recipe.meal_types, String).like(f'%"{meal_type}"%'))
        if origin == "release":
            filters.append(Recipe.release_version.is_not(None))
        elif origin == "curated":
            filters.append(Recipe.release_version.is_(None))
        is_withdrawn = or_(Recipe.withdrawn_at.is_not(None), Recipe.slug.in_(withdrawn_slugs()))
        if withdrawn is True:
            filters.append(is_withdrawn)
        elif withdrawn is False:
            filters.append(~is_withdrawn)
        total = self.database.scalar(select(func.count()).select_from(Recipe).where(*filters)) or 0
        recipes = self.database.scalars(select(Recipe).where(*filters).order_by(Recipe.id).offset(offset).limit(limit))
        return OpsRecipeCollection(items=[self._recipe_summary(recipe) for recipe in recipes], total=total)

    def recipe(self, recipe_id: int) -> OpsRecipeDetail:
        recipe = self.database.scalars(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.recipe_ingredients).selectinload(RecipeIngredient.ingredient),
                selectinload(Recipe.steps),
                selectinload(Recipe.nutrition),
            )
        ).one_or_none()
        if recipe is None:
            raise OpsDataNotFoundError
        nutrition = recipe.nutrition
        return OpsRecipeDetail(
            **self._recipe_summary(recipe).model_dump(),
            description=recipe.description,
            cuisine=recipe.cuisine,
            servings=recipe.servings,
            prep_time_minutes=recipe.prep_time_minutes,
            cook_time_minutes=recipe.cook_time_minutes,
            allergens=recipe.allergens,
            nutrition=(
                {
                    key: float(getattr(nutrition, key))
                    for key in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
                }
                if nutrition is not None
                else None
            ),
            ingredients=[
                {
                    "ingredient_id": item.ingredient_id,
                    "name": item.ingredient.display_name,
                    "normalized_name": item.ingredient.normalized_name,
                    "quantity": float(item.quantity) if item.quantity is not None else None,
                    "unit": item.unit,
                    "preparation": item.preparation,
                    "original_text": item.original_text,
                }
                for item in recipe.recipe_ingredients
            ],
            steps=[step.instruction for step in recipe.steps],
            withdrawn_at=recipe.withdrawn_at,
        )

    def update_recipe(self, recipe_id: int, change: OpsRecipeUpdate) -> OpsRecipeDetail:
        recipe = self._recipe(recipe_id)
        fields = ("title", "dietary_tags", "course", "meal_types")
        before = {key: getattr(recipe, key) for key in fields}
        if change.title is not None:
            recipe.title = change.title.strip()
        if change.dietary_tags is not None:
            recipe.dietary_tags = list(dict.fromkeys(change.dietary_tags))
        if change.course is not None:
            recipe.course = change.course
        if change.meal_types is not None:
            recipe.meal_types = list(dict.fromkeys(change.meal_types))
        after = {key: getattr(recipe, key) for key in fields}
        self._audit("recipe.updated", "recipe", recipe.slug, {"before": before, "after": after})
        self.database.commit()
        _planning_changed()
        return self.recipe(recipe_id)

    def withdraw_recipe(self, recipe_id: int, reason: str) -> OpsRecipeDetail:
        recipe = self._recipe(recipe_id)
        if self._withdrawn(recipe):
            raise OpsDataConflictError("This recipe is already withdrawn.")
        recipe.withdrawn_at = datetime.now(UTC)
        recipe.withdrawn_reason = reason.strip()
        self._audit("recipe.withdrawn", "recipe", recipe.slug, {"reason": recipe.withdrawn_reason})
        self.database.commit()
        _planning_changed()
        return self.recipe(recipe_id)

    def restore_recipe(self, recipe_id: int) -> OpsRecipeDetail:
        recipe = self._recipe(recipe_id)
        if self._withdrawn(recipe) == "file":
            raise OpsDataConflictError(
                "This recipe is withdrawn by data/recipes/withdrawn.json; remove it from that reviewed file instead."
            )
        if recipe.withdrawn_at is None:
            raise OpsDataConflictError("This recipe is not withdrawn.")
        details = {"withdrawn_at": recipe.withdrawn_at.isoformat(), "reason": recipe.withdrawn_reason}
        recipe.withdrawn_at = None
        recipe.withdrawn_reason = None
        self._audit("recipe.restored", "recipe", recipe.slug, details)
        self.database.commit()
        _planning_changed()
        return self.recipe(recipe_id)

    # --- ingredients ---

    def ingredients(self, *, query: str | None, offset: int, limit: int) -> OpsIngredientCollection:
        counts = dict(
            self.database.execute(
                select(RecipeIngredient.ingredient_id, func.count(distinct(RecipeIngredient.recipe_id))).group_by(
                    RecipeIngredient.ingredient_id
                )
            )
            .tuples()
            .all()
        )
        # ponytail: every ingredient read and filtered in Python so Chinese names and aliases (files) match too.
        items = [
            self._ingredient_view(item, counts.get(item.id, 0))
            for item in self.database.scalars(select(Ingredient).order_by(Ingredient.normalized_name))
        ]
        if query and query.strip():
            needle = query.strip().casefold()
            items = [
                item
                for item in items
                if any(
                    needle in text.casefold()
                    for text in (item.normalized_name, item.display_name, *item.zh_names, *item.aliases)
                )
            ]
        return OpsIngredientCollection(items=items[offset : offset + limit], total=len(items))

    def update_ingredient(self, ingredient_id: int, change: OpsIngredientUpdate) -> OpsIngredient:
        ingredient = self.database.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise OpsDataNotFoundError
        key = ingredient.normalized_name
        view = self._ingredient_view(ingredient, 0)
        before = {"display_name": view.display_name, "zh_names": view.zh_names, "aliases": view.aliases}
        after = dict(before)
        if change.display_name is not None:
            ingredient.display_name = change.display_name.strip()
        for kind, file, values in (("zh_names", ZH_ALIASES, change.zh_names), ("aliases", ALIASES, change.aliases)):
            if values is None:
                continue
            values = after[kind] = _names(values)
            row = self.database.get(CatalogOverride, (kind, key))
            if values == alias_file(file).get(key, []):
                # Back to what the reviewed file says: no override needed.
                if row is not None:
                    self.database.delete(row)
            elif row is None:
                self.database.add(
                    CatalogOverride(kind=kind, key=key, value=values, updated_by_user_id=self.actor_user_id)
                )
            else:
                row.value = values
                row.updated_by_user_id = self.actor_user_id
                row.updated_at = datetime.now(UTC)
        after["display_name"] = ingredient.display_name
        self._audit("ingredient.updated", "ingredient", key, {"before": before, "after": after})
        self.database.commit()
        catalog_overrides.reload(self.database)
        _planning_changed()
        recipes = self.database.scalar(
            select(func.count(distinct(RecipeIngredient.recipe_id))).where(
                RecipeIngredient.ingredient_id == ingredient.id
            )
        )
        return self._ingredient_view(ingredient, recipes or 0)

    # --- product mappings ---

    def mappings(
        self, *, query: str | None, status: str | None, offset: int, limit: int
    ) -> OpsProductMappingCollection:
        entries = {**release_snapshot(), **catalog_overrides.overrides("product_mapping")}
        names = dict(self.database.execute(select(Ingredient.normalized_name, Ingredient.display_name)).tuples().all())
        items = [self._mapping_view(key, entry, names.get(key)) for key, entry in sorted(entries.items())]
        if status:
            items = [item for item in items if item.status == status or item.source == status]
        if query and query.strip():
            needle = query.strip().casefold()
            items = [
                item
                for item in items
                if needle.replace("_", " ") in item.ingredient.replace("_", " ")
                or needle in (item.display_name or "").casefold()
                or any(needle in product.name.casefold() for product in item.products)
            ]
        return OpsProductMappingCollection(items=items[offset : offset + limit], total=len(items))

    def change_mapping(self, ingredient: str, product: OpsMappedProduct) -> OpsProductMapping:
        if self.database.scalar(select(Ingredient.id).where(Ingredient.normalized_name == ingredient)) is None:
            raise OpsDataNotFoundError
        value = {"status": "mapped", "review_status": "console", "products": [product.model_dump(mode="json")]}
        return self._set_mapping("mapping.changed", ingredient, value)

    def remove_mapping(self, ingredient: str) -> OpsProductMapping:
        if ingredient not in release_products():
            raise OpsDataNotFoundError
        return self._set_mapping("mapping.removed", ingredient, {"status": "removed"})

    # --- helpers ---

    def _set_mapping(self, action: str, ingredient: str, value: dict[str, Any]) -> OpsProductMapping:
        before = release_products().get(ingredient)
        row = self.database.get(CatalogOverride, ("product_mapping", ingredient))
        if row is None:
            self.database.add(
                CatalogOverride(
                    kind="product_mapping", key=ingredient, value=value, updated_by_user_id=self.actor_user_id
                )
            )
        else:
            row.value = value
            row.updated_by_user_id = self.actor_user_id
            row.updated_at = datetime.now(UTC)
        self._audit(action, "product_mapping", ingredient, {"before": before, "after": value})
        self.database.commit()
        catalog_overrides.reload(self.database)
        _planning_changed()
        name = self.database.scalar(select(Ingredient.display_name).where(Ingredient.normalized_name == ingredient))
        return self._mapping_view(ingredient, value, name)

    @staticmethod
    def _ingredient_view(ingredient: Ingredient, recipes: int) -> OpsIngredient:
        key = ingredient.normalized_name
        return OpsIngredient(
            id=ingredient.id,
            normalized_name=key,
            display_name=ingredient.display_name,
            zh_names=catalog_overrides.overrides("zh_names").get(key, alias_file(ZH_ALIASES).get(key, [])),
            aliases=catalog_overrides.overrides("aliases").get(key, alias_file(ALIASES).get(key, [])),
            allergens=ingredient.allergens or [],
            recipes=recipes,
        )

    @staticmethod
    def _mapping_view(key: str, entry: dict[str, Any], display_name: str | None) -> OpsProductMapping:
        return OpsProductMapping(
            ingredient=key,
            display_name=display_name,
            status=entry["status"],
            review_status=entry.get("review_status"),
            products=entry.get("products", []),
            source="console" if key in catalog_overrides.overrides("product_mapping") else "file",
        )

    def _recipe(self, recipe_id: int) -> Recipe:
        recipe = self.database.get(Recipe, recipe_id)
        if recipe is None:
            raise OpsDataNotFoundError
        return recipe

    @staticmethod
    def _withdrawn(recipe: Recipe) -> str | None:
        if recipe.slug in withdrawn_slugs():
            return "file"
        return "console" if recipe.withdrawn_at is not None else None

    def _recipe_summary(self, recipe: Recipe) -> OpsRecipeSummary:
        withdrawn = self._withdrawn(recipe)
        return OpsRecipeSummary(
            id=recipe.id,
            slug=recipe.slug,
            title=recipe.title,
            course=recipe.course,
            meal_types=recipe.meal_types,
            dietary_tags=recipe.dietary_tags or [],
            release_version=recipe.release_version,
            withdrawn=withdrawn,
            withdrawn_reason=withdrawn_reasons().get(recipe.slug, recipe.withdrawn_reason),
        )

    def _audit(self, action: str, target_type: str, target_id: str, details: dict) -> None:
        self.database.add(
            AuditEvent(
                actor_user_id=self.actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
            )
        )
