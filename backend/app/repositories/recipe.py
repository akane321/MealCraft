import json
import time
from functools import cache

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.core.paths import repository_root
from app.models.recipe import Ingredient, Recipe, RecipeIngredient
from app.planning.grocery_estimator import priceable_ingredients
from app.planning.recipe_quality import incomplete

# Release recipes carry a course; only these can fill a meal. Curated recipes
# have no course and are always candidates. Sides, sauces, drinks and desserts
# stay browsable but never become a planned meal or a meal recommendation.
MEAL_COURSES = ("main", "soup")


@cache
def withdrawn_slugs() -> tuple[str, ...]:
    """Recipes kept in the catalog but never planned (data/recipes/withdrawn.json)."""
    path = repository_root() / "data/recipes/withdrawn.json"
    return tuple(item["slug"] for item in json.loads(path.read_text(encoding="utf-8"))["recipes"])


# Planning candidates by (database, courses): loading ~5,000 recipes with their lines takes seconds,
# and every plan and change needs them. Detached and fully loaded, so they are only read.
# ponytail: a recipe edited meanwhile is planned with its old values until the entry expires.
_planning_pool: dict[tuple, tuple[float, list[Recipe]]] = {}


def clear_planning_pool() -> None:
    _planning_pool.clear()


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
        seconds = get_settings().planning_pool_cache_seconds
        key = (id(self.session.get_bind()), tuple(sorted(courses or MEAL_COURSES)))
        cached = _planning_pool.get(key)
        if seconds and cached and time.monotonic() - cached[0] < seconds:
            return list(cached[1])
        if not seconds:
            return self._load_for_planning(self.session, courses)
        # A session of its own: the request's commits would otherwise expire what the pool keeps.
        with Session(bind=self.session.get_bind()) as private:
            recipes = self._load_for_planning(private, courses)
            private.expunge_all()
        _planning_pool[key] = (time.monotonic(), recipes)
        return list(recipes)

    def _load_for_planning(self, session: Session, courses: list[str] | None) -> list[Recipe]:
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
            .options(selectinload(Recipe.steps))  # read when a plan is saved
            .where(or_(Recipe.course.is_(None), Recipe.course.in_(courses or MEAL_COURSES)))
            .where(or_(Recipe.release_version.is_(None), ~exists(unmatchable_line)))
            .where(Recipe.slug.not_in(withdrawn_slugs()))
            .order_by(Recipe.id)
        )
        # A release recipe that lost a line still lists, but never becomes a planned dinner.
        return [recipe for recipe in session.scalars(statement).unique().all() if incomplete(recipe) is None]

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
