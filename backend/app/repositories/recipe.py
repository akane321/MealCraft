from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.recipe import Ingredient, Recipe, RecipeIngredient
from app.planning.grocery_estimator import priceable_ingredients

# Release recipes carry a course; only these can fill a meal. Curated recipes
# have no course and are always candidates. Sides, sauces, drinks and desserts
# stay browsable but never become a planned meal or a meal recommendation.
MEAL_COURSES = ("main", "soup")


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_after(self, *, after_id: int | None, limit: int) -> list[Recipe]:
        statement: Select[tuple[Recipe]] = (
            select(Recipe).options(joinedload(Recipe.nutrition)).order_by(Recipe.id).limit(limit + 1)
        )
        if after_id is not None:
            statement = statement.where(Recipe.id > after_id)

        return list(self.session.scalars(statement).unique().all())

    def get_by_slug(self, slug: str) -> Recipe | None:
        statement = (
            select(Recipe)
            .where(Recipe.slug == slug)
            .options(
                joinedload(Recipe.nutrition),
                selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient),
                selectinload(Recipe.steps),
            )
        )
        return self.session.scalars(statement).unique().one_or_none()

    def list_for_recommendation(self) -> list[Recipe]:
        """Every recipe that can fill a meal; callers load it once per request and pass it on."""
        statement = (
            self._with_ingredients()
            .where(or_(Recipe.course.is_(None), Recipe.course.in_(MEAL_COURSES)))
            .order_by(Recipe.id)
        )
        return list(self.session.scalars(statement).unique().all())

    def list_for_planning(self, *, courses: list[str] | None = None) -> list[Recipe]:
        """Meal candidates the planner can price: release recipes with an unmatchable ingredient are left out.

        `courses` widens the pool beyond mains and soups for a composed meal's roles (ADR-0036).
        """
        unmatchable_line = (
            select(RecipeIngredient.id)
            .join(Ingredient)
            .where(
                RecipeIngredient.recipe_id == Recipe.id,
                Ingredient.normalized_name.not_in(sorted(priceable_ingredients())),
            )
        )
        statement = (
            self._with_ingredients()
            .where(or_(Recipe.course.is_(None), Recipe.course.in_(courses or MEAL_COURSES)))
            .where(or_(Recipe.release_version.is_(None), ~exists(unmatchable_line)))
            .order_by(Recipe.id)
        )
        return list(self.session.scalars(statement).unique().all())

    def list_by_ids(self, ids: list[int]) -> list[Recipe]:
        if not ids:
            return []
        statement = self._with_ingredients().where(Recipe.id.in_(set(ids))).order_by(Recipe.id)
        return list(self.session.scalars(statement).unique().all())

    @staticmethod
    def _with_ingredients() -> Select[tuple[Recipe]]:
        return select(Recipe).options(
            joinedload(Recipe.nutrition),
            selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient),
        )
