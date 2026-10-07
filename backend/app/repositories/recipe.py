import json
import logging
import threading
import time
from functools import cache
from typing import get_args

from sqlalchemy import Engine, Select, exists, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.core.paths import repository_root
from app.models.recipe import Ingredient, Recipe, RecipeIngredient
from app.planning.grocery_estimator import priceable_ingredients
from app.planning.recipe_quality import incomplete
from app.schemas.planning_v2 import DishCourse

logger = logging.getLogger(__name__)

# Release recipes carry a course; only these can fill a meal. Curated recipes
# have no course and are always candidates. Sides, sauces, drinks and desserts
# stay browsable but never become a planned meal or a meal recommendation.
MEAL_COURSES = ("main", "soup")


@cache
def withdrawn_reasons() -> dict[str, str]:
    """Recipes kept in the catalog but never planned (data/recipes/withdrawn.json), with the reason; the
    console withdraws more with `Recipe.withdrawn_at`."""
    path = repository_root() / "data/recipes/withdrawn.json"
    return {item["slug"]: item["reason"] for item in json.loads(path.read_text(encoding="utf-8"))["recipes"]}


def withdrawn_slugs() -> tuple[str, ...]:
    return tuple(withdrawn_reasons())


# The planning pool by database: every recipe the planner can price whose course a dish role can take (~5,000
# recipes with their lines take seconds to load), filtered by course for each caller. The API keeps it young
# (`keep_planning_pool_warm`, started by app/main.py): loaded at startup, again in the background whenever it is half
# PLANNING_POOL_CACHE_SECONDS old, and at once after an operations edit clears it, so no answer waits for a load
# (ADR-0046 section 3) and none plans from recipes loaded longer ago than PLANNING_POOL_CACHE_SECONDS. A request that
# finds no pool, or one past that age, loads it itself. Detached and fully loaded, so they are only read.
# ponytail: a catalog imported by the worker or a script reaches plans with the next background load, within half
# PLANNING_POOL_CACHE_SECONDS; a change marker the worker writes would make it immediate.
_planning_pool: dict[int, tuple[float, list[Recipe]]] = {}
_pool_binds: dict[int, Engine] = {}
POOL_COURSES = frozenset(get_args(DishCourse))
_pool_lock = threading.Lock()  # one load at a time: a request that finds no pool waits for the load under way
_pool_clears = 0  # a load that began before a clear may predate the edit that cleared it, and is not kept
_reloading: set[int] = set()
POOL_CHECK_SECONDS = 5.0  # how often the API's background thread looks at the pool's age
POOL_FAILURE_BACKOFF_MAX_SECONDS = 300.0
# Weeks the planner found from the pool for a chat turn's check, by database, household, planner limits and exact
# request, so the Plan that follows saves the week instead of searching again (services/meal_plan.py `check`).
# Each is used once, and expires after PLANNING_POOL_CACHE_SECONDS or is cleared with the pool.
# ponytail: a price refreshed meanwhile is seen only once the entry expires, as with the pool's recipes.
found_weeks: dict[tuple, tuple[float, tuple]] = {}
FOUND_WEEKS_KEPT = 8


def clear_planning_pool(*, reload: bool = False) -> None:
    """Drops the planning pools and the weeks found from them. `reload` (an operations edit, committed) loads the
    dropped pools again at once in the background: the next plan sees the edit and waits at most for that load."""
    global _pool_clears
    _pool_clears += 1
    dropped = [_pool_binds[key] for key in list(_planning_pool)]
    _planning_pool.clear()
    _pool_binds.clear()
    found_weeks.clear()
    for bind in dropped if reload else ():
        _reload_in_background(bind)


def _load_pool(bind: Engine) -> tuple[float, list[Recipe]]:
    clears = _pool_clears
    # A session of its own: a request's commits would otherwise expire what the pool keeps.
    with Session(bind=bind) as private:
        recipes = RecipeRepository(private)._load_for_planning(private, sorted(POOL_COURSES))
        private.expunge_all()
    entry = (time.monotonic(), recipes)
    if clears == _pool_clears:
        _planning_pool[id(bind)] = entry
        _pool_binds[id(bind)] = bind
    return entry


def _reload_in_background(bind: Engine) -> None:
    if id(bind) not in _reloading:
        _reloading.add(id(bind))
        threading.Thread(target=_reload_pool, args=(bind,), name="reload-planning-pool", daemon=True).start()


def _reload_pool(bind: Engine, *, maximum_age: float | None = None, log_failure: bool = True) -> Exception | None:
    try:
        with _pool_lock:
            cached = _planning_pool.get(id(bind))
            if maximum_age is not None and cached is not None and time.monotonic() - cached[0] < maximum_age:
                return None
            _load_pool(bind)
            if id(bind) not in _planning_pool:  # an edit cleared the pool meanwhile: load what it left
                _load_pool(bind)
    except Exception as error:  # the pool in use stays; the next look at its age tries again
        if log_failure:
            logger.warning("The planning pool could not be loaded", exc_info=True)
        return error
    finally:
        _reloading.discard(id(bind))
    return None


def keep_planning_pool_warm(bind: Engine, stop: threading.Event) -> None:
    """Loads `bind`'s planning pool, and again whenever it is half PLANNING_POOL_CACHE_SECONDS old or an edit
    dropped it, until `stop` is set. Requests go on planning from the pool in hand meanwhile."""
    failure_delay = POOL_CHECK_SECONDS
    consecutive_failures = 0
    while True:
        cached = _planning_pool.get(id(bind))
        half_life = get_settings().planning_pool_cache_seconds / 2
        if (cached is None or time.monotonic() - cached[0] >= half_life) and id(bind) not in _reloading:
            _reloading.add(id(bind))
            error = _reload_pool(bind, maximum_age=half_life, log_failure=False)
            if error is not None:
                consecutive_failures += 1
                if consecutive_failures == 1:
                    logger.warning(
                        "The planning pool could not be loaded; retrying in %.0f seconds",
                        failure_delay,
                        exc_info=(type(error), error, error.__traceback__),
                    )
                else:
                    logger.warning(
                        "The planning pool still could not be loaded; retrying in %.0f seconds",
                        failure_delay,
                    )
                wait_seconds = failure_delay
                failure_delay = min(failure_delay * 2, POOL_FAILURE_BACKOFF_MAX_SECONDS)
            else:
                consecutive_failures = 0
                failure_delay = POOL_CHECK_SECONDS
                wait_seconds = POOL_CHECK_SECONDS
        else:
            wait_seconds = POOL_CHECK_SECONDS
        if stop.wait(wait_seconds):
            return


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_after(
        self, *, after_id: int | None, limit: int, query: str | None = None, course: str | None = None
    ) -> list[Recipe]:
        statement: Select[tuple[Recipe]] = (
            select(Recipe).options(joinedload(Recipe.nutrition)).order_by(Recipe.id).limit(limit + 1)
        )
        if after_id is not None:
            statement = statement.where(Recipe.id > after_id)
        # Every word of the query appears in the title (browsing, not ranking).
        for word in (query or "").split():
            statement = statement.where(Recipe.title.ilike(f"%{word}%"))
        if course is not None:
            statement = statement.where(Recipe.course == course)

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
        wanted = set(courses or MEAL_COURSES)
        seconds = get_settings().planning_pool_cache_seconds
        if not seconds or not wanted <= POOL_COURSES:
            return self._load_for_planning(self.session, courses)
        bind = self.session.get_bind()
        cached = _planning_pool.get(id(bind))
        if cached is None or time.monotonic() - cached[0] >= seconds:
            with _pool_lock:  # a load under way (startup, background, an edit's) is waited for, not repeated
                cached = _planning_pool.get(id(bind))
                if cached is None or time.monotonic() - cached[0] >= seconds:
                    cached = _load_pool(bind)
        return [recipe for recipe in cached[1] if recipe.course is None or recipe.course in wanted]

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
            .where(Recipe.slug.not_in(withdrawn_slugs()), Recipe.withdrawn_at.is_(None))
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
