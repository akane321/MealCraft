"""The full meal structure's plumbing (ADR-0070, ADR-0072): request limits, the profile's equipment, the reference
the profile page reads, structured shape changes in the conversation, and a plan of two shopping trips saved."""

from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.shape_change import read_shape_change
from app.data.household_reference import reference_table
from app.schemas.household import HouseholdProfilePlanRequest, HouseholdReferenceResponse
from app.schemas.meal_plan import MealPlanShapeChangeRequest, WeeklyMealPlanRequest, default_plan_shape
from app.services.household import household_planning


@pytest.mark.parametrize(("days", "ok"), [(1, True), (14, True), (15, False), (0, False)])
def test_a_plan_is_one_to_fourteen_days(days, ok):
    for model in (WeeklyMealPlanRequest, HouseholdProfilePlanRequest):
        if ok:
            assert model.model_validate({"day_count": days}).day_count == days
        else:
            with pytest.raises(ValidationError):
                model.model_validate({"day_count": days})
    assert MealPlanShapeChangeRequest.model_validate({"meal_type": "dinner", "day_indexes": [9, 14]}).day_indexes


def test_missing_equipment_reaches_the_planner_and_the_reference_lists_the_structure():
    version = SimpleNamespace(
        members=[{"name": "Lin"}],
        nutrition_limits=None,
        presence_rules=None,
        cooking_time_rules=None,
        missing_basics=None,
        missing_equipment=["oven"],
    )
    assert household_planning(version).missing_equipment == ["oven"]
    reference = HouseholdReferenceResponse.model_validate(reference_table()).meal_structure
    assert list(reference.presets["dinner"])[0] == "Full meal (grows with the household)"
    assert reference.energy_floor_share == {"lunch": 0.25, "dinner": 0.25}
    assert "oven" in reference.equipment and reference.perishable_days == 3 and reference.trip_days == 7
    assert [(row.min_people, row.max_people, row.protein_mains, row.vegetables) for row in reference.dinner_counts] == [
        (1, 2, 1, 1),
        (3, 4, 2, 1),
        (5, 6, 2, 2),
        (7, None, 3, 2),
    ]


def _week(shape):
    return SimpleNamespace(plan_shape=shape, days=[])


@pytest.mark.parametrize(
    ("message", "meal", "roles"),
    [
        ("no soup", "dinner", ["main", "main-2", "main-3", "vegetable", "vegetable-2", "staple"]),
        ("add a soup", "dinner", None),  # the full default's dinner already has one: nothing to change
        ("lunch just one dish", "lunch", ["main"]),
        ("dinner just a main", "dinner", ["main", "staple"]),
        ("no meat dish for dinner", "dinner", ["main", "vegetable", "vegetable-2", "soup", "staple"]),
    ],
)
def test_a_full_default_week_changes_in_meal_roles_and_keeps_its_staple(message, meal, roles):
    intent = read_shape_change(message, plan=_week(default_plan_shape()), day_indexes=None)
    if roles is None:
        assert intent is None or intent.request.roles is None or len(intent.request.roles) > 7
        return
    assert intent is not None and intent.request.meal_type == meal
    assert [role.role_id for role in intent.request.roles] == roles
    assert all(role.meal_roles for role in intent.request.roles)


def test_another_soup_goes_before_the_staple():
    intent = read_shape_change("add another soup to dinner", plan=_week(default_plan_shape()), day_indexes=None)
    assert [role.role_id for role in intent.request.roles][-2:] == ["soup-2", "staple"]


def test_a_ten_day_plan_shops_twice_and_saves_each_trip(tmp_path):
    from app.api.routes.meal_plans import build_meal_plan_service
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog
    from app.db.base import Base
    from app.repositories.recipe import clear_planning_pool

    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    clear_planning_pool()
    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            import_catalog(session, catalog)
            plans = build_meal_plan_service(session, 1)
            request = WeeklyMealPlanRequest.model_validate(
                {
                    "start_date": "2027-01-03",
                    "day_count": 10,
                    "household_size": 2,
                    "pricing_mode": "fixture",
                    "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
                    "household": {"members": [{"name": "Lin", "servings": 1}, {"name": "Raj", "servings": 1}]},
                }
            )
            plan = plans.generate(request)
            assert plan.day_count == 10 and {day.day_index for day in plan.days} == set(range(1, 11))
            trips = {line.shopping_trip for line in plan.grocery_estimate.items}
            assert trips == {1, 2}
            again = plans.get(plan.id)
            assert {line.shopping_trip for line in again.grocery_estimate.items} == {1, 2}
            # A perishable dish is kept to days 1-3 and 8-10 (three days after each trip).
            perishable = {line.ingredient_name for line in again.grocery_estimate.items if line.perishable}
            for day in again.days:
                recipe = plans.recipe_repository.get_by_slug(day.recipe.slug)
                if perishable & {line.ingredient.normalized_name for line in recipe.recipe_ingredients}:
                    assert (day.day_index - 1) % 7 < 3, day
            assert date.fromisoformat(str(again.end_date)) == date(2027, 1, 12)
    finally:
        clear_planning_pool()
        engine.dispose()


def _catalog_recipe(recipe_id, role, course="main", **estimated):
    marks = {
        name: {"method": method, "batch": "b", "reviewed": reviewed} for name, (method, reviewed) in estimated.items()
    }
    return SimpleNamespace(
        id=recipe_id,
        meal_role=role,
        course=course,
        contains_staple=role == "one_bowl",
        protein_sources=["chicken"],
        cooking_methods=[],
        equipment=[],
        cuisine="chinese",
        recipe_ingredients=[],
        estimated=marks,
    )


def test_a_model_decided_tag_fills_no_meal_role_until_its_batch_is_reviewed():
    from app.planning.meal_composition import catalog_role_admits, unreviewed
    from app.planning.product_path import pool_for, recipe_tags
    from app.schemas.planning_v2 import PlanningMealRole

    rule = _catalog_recipe(1, "protein_main", meal_role=("rule", False))
    model = _catalog_recipe(2, "one_bowl", meal_role=("llm", False), contains_staple=("llm", False))
    sources = _catalog_recipe(3, "protein_main", meal_role=("rule", False), protein_sources=("llm", False))
    accepted = _catalog_recipe(4, "one_bowl", meal_role=("llm", True), contains_staple=("llm", True))
    recipes = [rule, model, sources, accepted]
    assert [unreviewed(r) for r in recipes] == [False, True, True, False]

    tagged = PlanningMealRole(role_id="main", meal_roles=["protein_main", "one_bowl"])
    assert [r.id for r in pool_for([("dinner", [tagged])], recipes)] == [1, 4]
    assert [catalog_role_admits(tagged, r) for r in recipes] == [True, False, False, True]
    candidate = SimpleNamespace(ingredients=[])
    assert recipe_tags(model, candidate)["meal_role"] is None
    assert recipe_tags(sources, candidate)["protein_sources"] is None
    assert recipe_tags(accepted, candidate)["meal_role"] == "one_bowl"
    # A role of courses is the older form: it admits by course, the tags' review aside.
    by_course = PlanningMealRole(role_id="main", courses=["main"])
    assert pool_for([("dinner", [by_course])], recipes) == recipes
    assert all(catalog_role_admits(by_course, r) for r in recipes)
