"""Budgeted composed weeks that vary (owner, 2026-10-02: "菜很单调,不太好").

The 2026-10-02 walkthrough household (two people, one allergic to peanuts, no pork, S$100 a week, every
dinner a main, a vegetable dish and a soup, fixture prices) was served one dish five times and twelve
distinct dishes of 21 on the vegetable rule (#210). The planner's candidates hold at most 18 distinct dishes
of 21 within S$100 at the profile's 60 minutes (20 at 240 minutes), by an exact whole-package search; the
whole catalog holds 21 for about S$53.
"""

from collections import Counter
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.meal_plans import build_meal_plan_service
from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import import_release_v2
from app.db.base import Base
from app.planning import product_path
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner, MealState
from app.planning.product_path import _vary_starts_within_time_budget, composed_packet
from app.planning.recipe_quality import dish_family, dish_kind
from app.repositories.recipe import clear_planning_pool
from app.schemas.meal_plan import MEAL_PRESETS, WeeklyMealPlanRequest
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningDiversityPolicy,
    PlanningNutritionBand,
    PlanningRecipeCount,
    PlanningRepetitionRules,
)
from app.services import recommendation as recommendation_service

DINNER_WITH_SOUP = MEAL_PRESETS["dinner"]["main, vegetable and soup"]
NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")


class Ranked(SimpleNamespace):
    """A recommendation as the planning steps read one."""

    def model_copy(self, *, update):
        return Ranked(**{**vars(self), **update})


def ranked(identifier: int, title: str, cost: float = 1.0) -> Ranked:
    return Ranked(
        recipe=SimpleNamespace(id=identifier, title=title, slug=f"r{identifier}"),
        reasons=[],
        grocery_estimate=SimpleNamespace(consumed_total_sgd=cost, purchase_total_sgd=cost),
    )


def test_a_composed_shape_keeps_the_best_of_each_course_it_takes(monkeypatch):
    """Kept as one list of 500, the quickest mains crowded out the soups: 12 of 178 reached the walkthrough."""
    monkeypatch.setattr(recommendation_service, "CANDIDATE_LIMIT", 2)
    monkeypatch.setattr(recommendation_service, "RecipeRecommendationCollectionResponse", SimpleNamespace)
    recipes = [SimpleNamespace(id=i, course="soup" if i > 3 else "main", release_version=None) for i in range(1, 6)]
    engine = SimpleNamespace(
        recommend=lambda recipes, constraints: ([ranked(r.id, f"dish {r.id}") for r in recipes], [])
    )
    estimate = SimpleNamespace(
        complete=True, warnings=[], within_budget=None, consumed_total_sgd=1.0, purchase_total_sgd=2.0
    )
    service = recommendation_service.RecipeRecommendationService(
        None, SimpleNamespace(estimate=lambda recipe, constraints: estimate), engine
    )

    def kept(**request) -> list[int]:
        constraints = WeeklyMealPlanRequest.model_validate({"pricing_mode": "fixture", **request})
        found = service.recommend(constraints, deduct_pantry_from_cost=False, recipes=recipes)
        return [r.recipe.id for r in found.recommendations]

    assert kept(plan_shape={"meals": {"dinner": DINNER_WITH_SOUP}}) == [1, 2, 4, 5]
    assert kept() == [1, 2]  # one dish a dinner: the best 500 of all, as before


def test_a_budgeted_packet_holds_cheap_dishes_and_one_of_each_dish_family():
    """Under a budget half of each course's places go to the cheapest dishes, and "Basic Fried Rice" after "Chinese
    Fried Rice" waits until every other dish family is in; without one the packet is the best-ranked."""
    fried = ["Chinese Fried Rice", "Basic Fried Rice", "Easy Fried Rice", "Simple Fried Rice", "Quick Fried Rice"]
    titles = fried + [f"Dish {chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(6, 41)]  # one family each
    mains = [ranked(i, title, cost=1.0 if i > 30 else 10.0) for i, title in enumerate(titles, start=1)]
    recipes = [SimpleNamespace(id=i, course="main") for i in range(1, 41)]
    shape = [("dinner", [SimpleNamespace(role_id="main", courses=["main"])])]

    packet, limits = composed_packet(shape, 7, 100.0, mains, recipes)
    ids = {r.recipe.id for r in packet}
    assert limits == {"main": 24} and len(packet) == 24
    assert set(range(31, 41)) <= ids  # every cheap dish, all ranked below the 24th
    assert sum(dish_family(r.recipe.title) == "fried rice" for r in packet) == 1

    unbudgeted, _ = composed_packet(shape, 7, None, mains, recipes)
    assert [r.recipe.id for r in unbudgeted] == list(range(1, 25))  # the best-ranked, as before


def week_problem() -> FinalPlanningProblem:
    """Two dinners of a main and a vegetable dish. Chicken rice comes twice in the week below; chicken noodles
    use the same chicken (a pack holds both dinners' worth) and cost a S$1 pack of noodles more; beef stew
    costs S$9 of beef."""

    def recipe(recipe_id, course, *lines):
        return {
            "recipe_id": recipe_id,
            "title": recipe_id.replace("-", " "),
            "servings": 2,
            "allowed_meal_types": ["dinner"],
            "total_time_minutes": 30,
            "prep_minutes": 10,
            "cook_minutes": 20,
            "passive_minutes": 0,
            "course": course,
            "allergens": [],
            "ingredients": [{"ingredient_id": i, "quantity": q, "unit": "g"} for i, q in lines],
            "nutrients_per_serving": dict.fromkeys(NUTRIENTS, 10),
        }

    recipes = [
        recipe("beef-stew", "main", ("beef", 300)),
        recipe("chicken-rice", "main", ("chicken", 300), ("rice", 200)),
        recipe("chicken-noodles", "main", ("chicken", 300), ("noodles", 200)),
        recipe("garlic-spinach", "side", ("spinach", 300)),
        recipe("bok-choy", "side", ("bok_choy", 300)),
    ]
    prices = {"beef": 9.0, "chicken": 6.0, "rice": 2.0, "noodles": 1.0, "spinach": 2.0, "bok_choy": 2.0}
    composition = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side"]}]
    return FinalPlanningProblem.model_validate(
        {
            "problem_id": "varied-week",
            "slots": [
                {
                    "slot_id": f"d{day}",
                    "planned_date": date(2026, 9, 27 + day).isoformat(),
                    "meal_type": "dinner",
                    "servings": 2,
                    "max_time_minutes": 120,
                    "composition": composition,
                }
                for day in (1, 2)
            ],
            "recipes": recipes,
            "products": [
                {
                    "ingredient_id": ingredient,
                    "product_id": f"p-{ingredient}",
                    "package_quantity": 1000,
                    "package_unit": "g",
                    "price_sgd": price,
                }
                for ingredient, price in prices.items()
            ],
            "allergen_vocabulary": [],
            "purchase_budget_sgd": 13.0,
            "catalog_version": "test",
            "product_snapshot_version": "test",
            "policy_version": "test",
        }
    )


def repeated_week() -> MealState:
    return MealState(
        (
            ("d1", (("main", "chicken-rice"), ("vegetable", "garlic-spinach"))),
            ("d2", (("main", "chicken-rice"), ("vegetable", "bok-choy"))),
        )
    )


def test_a_composed_packet_keeps_a_locked_dish_outside_its_ranked_limit():
    mains = [ranked(i, f"dish {i}") for i in range(1, 41)]
    recipes = [SimpleNamespace(id=i, course="main") for i in range(1, 41)]
    shape = [("dinner", [SimpleNamespace(role_id="main", courses=["main"])])]
    packet, _ = composed_packet(shape, 7, None, mains, recipes, keep={"r40": 1})
    assert {r.recipe.id for r in packet} == set(range(1, 25)) | {40}


def test_varying_a_composed_week_does_not_replace_locked_roles():
    problem = week_problem()
    slots = [slot.model_copy(update={"locked_roles": {"main": "chicken-rice"}}) for slot in problem.slots]
    problem = problem.model_copy(update={"slots": slots})
    repeated = MealState(
        (
            ("d1", (("main", "chicken-rice"), ("vegetable", "garlic-spinach"))),
            ("d2", (("main", "chicken-rice"), ("vegetable", "bok-choy"))),
        )
    )
    planner = MealBeamPlanner(MealBeamLimits(distinct_kinds=True))
    assert planner.vary_within_budget(problem, repeated) == repeated
    for slot in slots:
        assert {r.recipe_id for r in planner.role_dishes(problem, slot, slot.composition[0])} == {"chicken-rice"}


def test_a_repeat_is_swapped_for_the_dish_sharing_what_the_week_buys():
    """Chicken rice twice costs S$12; chicken noodles share its chicken and fit S$13, beef stew does not."""
    problem = week_problem()
    repeated = repeated_week()
    varied = MealBeamPlanner(MealBeamLimits(distinct_kinds=True)).vary_within_budget(problem, repeated)
    mains = sorted(dict(dishes)["main"] for _, dishes in varied.choices)
    assert mains == ["chicken-noodles", "chicken-rice"]
    # With S$12 the week stays as it was: even the noodles' S$1 pack does not fit.
    tight = problem.model_copy(update={"purchase_budget_sgd": 12.0})
    assert MealBeamPlanner().vary_within_budget(tight, repeated) == repeated


def test_variety_starts_stop_when_the_pass_spends_its_time_budget():
    """The time is read between starts: the start begun before two seconds finishes, the next is not begun."""
    state = repeated_week()
    calls = []
    planner = SimpleNamespace(vary_within_budget=lambda problem, state: calls.append(state) or state)
    ticks = iter((0.0, 0.0, 1.0, 2.0))

    _vary_starts_within_time_budget(
        planner,
        week_problem(),
        [(0.0, state)] * 3,
        {state.choices},
        is_best=lambda state: False,
        clock=lambda: next(ticks),
        seconds=2.0,
    )

    assert len(calls) == 2


@pytest.mark.parametrize(("best", "starts_tried"), [(True, 1), (False, 3)])
def test_variety_starts_stop_only_at_a_week_none_can_beat(best, starts_tried):
    state = repeated_week()
    calls = []
    planner = SimpleNamespace(vary_within_budget=lambda problem, state: calls.append(state) or state)

    _vary_starts_within_time_budget(
        planner, week_problem(), [(0.0, state)] * 3, set(), is_best=lambda state: best, clock=lambda: 0.0
    )

    assert len(calls) == starts_tried


def test_varying_keeps_distinct_dish_kinds_within_each_meal():
    problem = week_problem()
    titles = {
        "chicken-noodles": "Chicken Bok Choy",
        "garlic-spinach": "Garlic Bok Choy",
        "bok-choy": "Bok Choy",
    }
    problem = problem.model_copy(
        update={
            "recipes": [
                recipe.model_copy(update={"title": titles.get(recipe.recipe_id, recipe.title)})
                for recipe in problem.recipes
            ]
        }
    )
    repeated = repeated_week()

    assert MealBeamPlanner(MealBeamLimits(distinct_kinds=True)).vary_within_budget(problem, repeated) == repeated


def test_varying_respects_a_candidate_recipe_maximum():
    problem = week_problem().model_copy(
        update={
            "repetition_rules": PlanningRepetitionRules(
                recipe_counts=[PlanningRecipeCount(recipe_id="chicken-noodles", max_uses=0)]
            )
        }
    )

    assert MealBeamPlanner().vary_within_budget(problem, repeated_week()) == repeated_week()


def test_varying_does_not_remove_a_dish_the_household_requested():
    problem = week_problem().model_copy(
        update={
            "repetition_rules": PlanningRepetitionRules(
                recipe_counts=[PlanningRecipeCount(recipe_id="chicken-rice", min_uses=2)]
            )
        }
    )

    assert MealBeamPlanner().vary_within_budget(problem, repeated_week()) == repeated_week()


def test_varying_keeps_hard_daily_nutrition_bands():
    problem = week_problem()
    recipes = [
        recipe.model_copy(
            update={"nutrients_per_serving": recipe.nutrients_per_serving.model_copy(update={"calories_kcal": 100})}
        )
        if recipe.recipe_id == "chicken-noodles"
        else recipe
        for recipe in problem.recipes
    ]
    problem = problem.model_copy(
        update={
            "recipes": recipes,
            "nutrition_bands": [PlanningNutritionBand(metric="calories_kcal", scope="per_day", upper=20)],
        }
    )

    assert MealBeamPlanner().vary_within_budget(problem, repeated_week()) == repeated_week()


def test_varying_leaves_roles_the_household_allows_to_repeat():
    problem = week_problem().model_copy(update={"repetition_rules": PlanningRepetitionRules(repeat_ok_roles=["main"])})

    assert MealBeamPlanner().vary_within_budget(problem, repeated_week()) == repeated_week()


def test_varying_defers_to_the_explicit_diversity_policy():
    problem = week_problem().model_copy(
        update={
            "diversity_policy": PlanningDiversityPolicy(
                classification_version="test",
                classification_rule="Test classifications are intentionally empty.",
                classifications={},
            )
        }
    )

    assert MealBeamPlanner().vary_within_budget(problem, repeated_week()) == repeated_week()


@pytest.fixture(scope="module")
def product():
    """A product database as compose seeds it: the curated catalog, then release v2.1."""
    root = repository_root()
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        import_catalog(
            session, load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
        )
    with factory() as session:
        import_release_v2(session)
    clear_planning_pool()
    with factory() as session:
        yield session
    clear_planning_pool()
    engine.dispose()


def test_the_walkthrough_week_varies_within_its_budget(product):
    """12 distinct dishes of 21 and one soup five times before; the candidates hold at most 18 within S$100."""
    request = WeeklyMealPlanRequest.model_validate(
        {
            "start_date": "2026-09-28",
            "household_size": 2,
            "allergens": ["peanut"],
            "excluded_ingredients": ["pork"],
            "weekly_budget_sgd": 100.0,
            "plan_shape": {"meals": {"dinner": DINNER_WITH_SOUP}},
            "pricing_mode": "fixture",
        }
    )
    plan = build_meal_plan_service(product, 1).generate(request)
    dishes = Counter(dish_family(dish.recipe.title) for dish in plan.days)
    assert plan.grocery_estimate.purchase_total_sgd <= 100.0
    assert sum(dishes.values()) == 21
    assert len(dishes) >= 16, dishes
    assert max(dishes.values()) <= 2, dishes


# Breakfast, a lunch of a main and a vegetable dish and a dinner of a main and an optional vegetable dish:
# 35 dish positions, the fewest the heavy-composition gate bounds.
THREE_MEALS_35 = {
    "breakfast": MEAL_PRESETS["breakfast"]["one dish"],
    "lunch": MEAL_PRESETS["lunch"]["main and vegetable"],
    "dinner": MEAL_PRESETS["dinner"]["main and vegetable"],
}
WALKTHROUGH = {"allergens": ["peanut"], "excluded_ingredients": ["pork"], "max_cooking_time_minutes": 60}


def three_meals(budget: float, meals=THREE_MEALS_35, **household) -> WeeklyMealPlanRequest:
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": "2026-09-28",
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "weekly_budget_sgd": budget,
            "plan_shape": {"meals": meals},
            "pricing_mode": "fixture",
            **household,
        }
    )


def variety_passes(monkeypatch) -> list[dict]:
    """Each variety pass `plan` runs: its time budget, its starts, and the starts it tried."""
    passes = []
    real = product_path._vary_starts_within_time_budget

    def spy(meal_beam, problem, starts, seen, *, is_best, seconds):
        tried = []
        added = real(meal_beam, problem, starts, seen, is_best=lambda s: tried.append(s) or is_best(s), seconds=seconds)
        passes.append({"seconds": seconds, "starts": len(starts), "tried": len(tried)})
        return added

    monkeypatch.setattr(product_path, "_vary_starts_within_time_budget", spy)
    return passes


def test_a_heavy_week_stops_varying_only_at_a_week_the_final_order_cannot_beat(product, monkeypatch):
    """PR #243 review: the early stop took a week with no dish or dish family twice as one no start could beat,
    but the order that picks the week also counts empty optional dishes and dish kinds. Here that stop ended
    after one start with 33 dish kinds of 35; with the time budget lifted, a new heavy week is now as varied as
    trying every start makes it (35 kinds)."""
    monkeypatch.setattr(product_path, "VARIETY_PASS_SECONDS", float("inf"))
    plans = build_meal_plan_service(product, 1)
    request = three_meals(150.0, **WALKTHROUGH)

    def variety(plan) -> tuple[int, int, int, int]:
        titles = [dish.recipe.title for dish in plan.days]
        uses = Counter(titles)
        return len(titles), len(uses), max(uses.values()), len({dish_kind(title) for title in titles})

    bounded = variety(plans.generate(request))
    monkeypatch.setattr(product_path, "HEAVY_COMPOSITION_DISH_POSITIONS", 10**6)  # every start, as before #243
    assert bounded == variety(plans.generate(request))


def test_only_new_heavy_weeks_bound_their_variety_pass(product, monkeypatch):
    """Ordinary weeks (under 35 dish positions) and replanning with locked dishes try every start, unbounded."""
    plans = build_meal_plan_service(product, 1)
    passes = variety_passes(monkeypatch)

    plans.generate(three_meals(200.0))
    assert passes[-1]["seconds"] == product_path.VARIETY_PASS_SECONDS

    plans.generate(three_meals(100.0, {"dinner": DINNER_WITH_SOUP}, **WALKTHROUGH))
    assert passes[-1]["seconds"] == float("inf") and passes[-1]["tried"] == passes[-1]["starts"] > 0

    request = three_meals(200.0)
    recipes, found = plans._candidates(request)
    course = {recipe.id: recipe.course for recipe in recipes}
    main = next(r.recipe.slug for r in found.recommendations if course.get(r.recipe.id) == "main")
    plans.planning_engine.plan(request, found.recommendations, recipes, locked={(0, "dinner"): {"main": main}})
    assert passes[-1]["seconds"] == float("inf") and passes[-1]["tried"] == passes[-1]["starts"] > 0
