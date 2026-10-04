"""The planning capability switch of ADR-0036 section 6: mvp refuses meal compositions."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.test_recipes import _household_profile_payload, recipe_client  # noqa: F401

COMPOSITION = [
    {"role_id": "main", "courses": ["main"]},
    {"role_id": "vegetable", "courses": ["side", "salad"]},
    {"role_id": "soup", "courses": ["soup"], "required": False},
]


@pytest.fixture
def full_capability(monkeypatch):
    monkeypatch.setattr(get_settings(), "planning_capability", "full")


def test_mvp_refuses_a_profile_with_a_meal_composition(recipe_client: TestClient, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "planning_capability", "mvp")
    response = recipe_client.post(
        "/api/household-profiles", json={**_household_profile_payload(), "meal_composition": COMPOSITION}
    )

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]


def test_full_capability_stores_the_composition_on_the_profile_version(
    recipe_client: TestClient,  # noqa: F811
    full_capability,
):
    response = recipe_client.post(
        "/api/household-profiles", json={**_household_profile_payload(), "meal_composition": COMPOSITION}
    )

    assert response.status_code == 201, response.text
    stored = response.json()["current"]["meal_composition"]
    assert [role["role_id"] for role in stored] == ["main", "vegetable", "soup"]
    assert stored[2]["required"] is False


def test_mvp_refuses_a_plan_request_with_a_meal_composition(recipe_client: TestClient, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "planning_capability", "mvp")
    response = recipe_client.post("/api/plans/generate", json={"household_size": 2, "meal_composition": COMPOSITION})

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]


def test_a_composition_needs_unique_roles_and_one_required_dish(recipe_client: TestClient):  # noqa: F811
    for composition in (
        [{"role_id": "main", "courses": ["main"]}, {"role_id": "main", "courses": ["soup"]}],
        [{"role_id": "soup", "courses": ["soup"], "required": False}],
    ):
        response = recipe_client.post(
            "/api/plans/generate", json={"household_size": 2, "meal_composition": composition}
        )
        assert response.status_code == 422


def _dish(slug, course, ingredient, grams, *, calories, prep=10, cook=15):
    from decimal import Decimal

    from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep

    return Recipe(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description="Synthetic",
        cuisine="test",
        meal_type=course,
        course=course,
        meal_types=["dinner"],
        servings=4,
        prep_time_minutes=prep,
        cook_time_minutes=cook,
        dietary_tags=[],
        nutrition=RecipeNutrition(
            calories_kcal=Decimal(calories),
            protein_g=Decimal("10"),
            carbohydrate_g=Decimal("10"),
            fat_g=Decimal("5"),
            sodium_mg=Decimal("300"),
            sugar_g=Decimal("2"),
        ),
        recipe_ingredients=[
            RecipeIngredient(
                ingredient=Ingredient(normalized_name=ingredient, display_name=ingredient),
                quantity=Decimal(grams),
                unit="g",
                sort_order=1,
            )
        ],
        steps=[RecipeStep(step_number=1, instruction="Cook.")],
    )


@contextmanager
def dish_client(monkeypatch, dishes):
    """A signed-in client over an in-memory catalog of `dishes`, with composed meals switched on."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base
    from app.db.session import get_db_session
    from app.main import app

    monkeypatch.setattr(get_settings(), "planning_capability", "full")
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        session.add_all(dishes)
        session.commit()

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = database
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"email": "cook@example.test", "password": "correct horse battery staple", "display_name": "Cook"},
        )
        client.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def composed_client(monkeypatch):
    dishes = [
        _dish("salmon-bake", "main", "salmon_fillet", 400, calories=500),
        _dish("chicken-roast", "main", "chicken_breast", 400, calories=450),
        _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
        _dish("spinach-saute", "side", "baby_spinach", 200, calories=80),
        _dish("zucchini-salad", "salad", "zucchini", 300, calories=60),
        _dish("tomato-soup", "soup", "tomato", 500, calories=150, cook=25),
    ]
    with dish_client(monkeypatch, dishes) as client:
        yield client


def test_full_capability_plans_and_stores_a_week_of_composed_dinners(composed_client):
    response = composed_client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-28",
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "meal_composition": COMPOSITION,
        },
    )

    assert response.status_code == 201, response.text
    days = response.json()["days"]
    by_day: dict[int, dict[str, dict]] = {}
    for dish in days:
        by_day.setdefault(dish["day_index"], {})[dish["role_id"]] = dish
    assert sorted(by_day) == list(range(1, 8))
    for meal in by_day.values():
        assert {"main", "vegetable", "soup"} == set(meal)  # the optional soup fits 90 minutes
        # Three dishes: the main is 0.6 of a meal, the others 0.4 (ADR-0036 section 2).
        assert meal["main"]["portion_share"] == 0.6 and meal["soup"]["portion_share"] == 0.4
        assert meal["main"]["recipe"]["slug"] in {"salmon-bake", "chicken-roast"}
    mains = [by_day[day]["main"]["recipe"]["slug"] for day in range(1, 8)]
    assert all(a != b for a, b in zip(mains, mains[1:], strict=False))  # two mains alternate
    salmon = next(d for d in days if d["recipe"]["slug"] == "salmon-bake")
    assert salmon["nutrition_per_person"]["calories_kcal"] == 300  # 500 kcal x 0.6


def _composed_plan(client):
    response = client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-28",
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "meal_composition": COMPOSITION,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_whole_meal_is_checked_in_at_once_and_a_dish_on_its_own(composed_client):
    plan = _composed_plan(composed_client)

    whole = composed_client.patch(f"/api/plans/{plan['id']}/meals/1/dinner", json={"status": "completed"}).json()
    day_one = [d for d in whole["days"] if d["day_index"] == 1]
    assert len(day_one) == 3 and all(d["status"] == "completed" for d in day_one)

    soup = next(d for d in whole["days"] if d["day_index"] == 2 and d["role_id"] == "soup")
    single = composed_client.patch(f"/api/plans/{plan['id']}/entries/{soup['entry_id']}", json={"status": "skipped"})
    day_two = {d["role_id"]: d["status"] for d in single.json()["days"] if d["day_index"] == 2}
    assert day_two == {"main": "planned", "vegetable": "planned", "soup": "skipped"}


def test_swapping_one_dish_keeps_its_role_share_and_the_rest_of_the_meal(composed_client):
    plan = _composed_plan(composed_client)
    vegetable = next(d for d in plan["days"] if d["day_index"] == 3 and d["role_id"] == "vegetable")

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"entry_id": vegetable["entry_id"], "event_type": "REPLACE_MEAL"},
    )

    assert preview.status_code == 201, preview.text
    after = preview.json()["after_entry"]
    assert after["role_id"] == "vegetable" and after["portion_share"] == 0.4
    assert after["recipe_slug"] in {"broccoli-stirfry", "spinach-saute", "zucchini-salad"}
    assert after["recipe_slug"] != vegetable["recipe"]["slug"]


def test_the_agent_asks_which_dish_when_a_day_has_several(composed_client):
    from app.agent.replanning import AgentReplanInterpreter
    from app.schemas.agent import AgentReplanDraft
    from app.schemas.meal_plan import WeeklyMealPlanResponse

    plan = WeeklyMealPlanResponse.model_validate(_composed_plan(composed_client))
    interpreter = AgentReplanInterpreter()

    draft, questions = interpreter.parse("Replace day 2", plan=plan, current=AgentReplanDraft())
    assert draft.entry_id is None and draft.day_index == 2
    assert "which one" in questions[0]

    draft, questions = interpreter.parse("the soup", plan=plan, current=draft)
    soup = next(d for d in plan.days if d.day_index == 2 and d.role_id == "soup")
    assert draft.entry_id == soup.entry_id and not questions


def _week_ahead(client, composition=COMPOSITION):
    from datetime import date, timedelta

    response = client.post(
        "/api/plans/generate",
        json={
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": composition}},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_adding_a_soup_to_one_dinner_replans_only_that_meal(composed_client):
    two_dishes = COMPOSITION[:2]
    plan = _week_ahead(composed_client, two_dishes)
    before = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in plan["days"]}

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [5]},
    )
    assert preview.status_code == 201, preview.text
    change = preview.json()["shape_change"]
    assert change["scope"] == "meal" and change["plan_shape"] is None
    # Friday's main and vegetable stay: only the soup is new, and nothing comes off.
    assert [d["role_id"] for d in change["added"]] == ["soup"]
    assert (change["removed"], change["kept"]) == ([], 2)

    applied = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")
    assert applied.status_code == 200, applied.text
    after = applied.json()["plan"]
    friday = {d["role_id"] for d in after["days"] if d["day_index"] == 5}
    assert friday == {"main", "vegetable", "soup"}
    # Every other meal is exactly as it was.
    others = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in after["days"] if d["day_index"] != 5}
    assert others == {key: slug for key, slug in before.items() if key[0] != 5}
    assert after["revision"] == plan["revision"] + 1


def test_dropping_a_meal_for_the_week_changes_this_weeks_shape_only(composed_client):
    plan = _week_ahead(composed_client)
    lunch = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "lunch", "roles": [{"role_id": "main", "courses": ["main"]}]},
    )
    assert lunch.status_code == 201, lunch.text
    assert set(lunch.json()["shape_change"]["plan_shape"]["meals"]) == {"lunch", "dinner"}
    week = composed_client.post(f"/api/plans/{plan['id']}/replan/{lunch.json()['id']}/confirm").json()["plan"]
    assert {d["meal_type"] for d in week["days"]} == {"lunch", "dinner"}

    no_dinner = composed_client.post(f"/api/plans/{plan['id']}/shape/preview", json={"meal_type": "dinner"})
    assert no_dinner.status_code == 201, no_dinner.text
    assert no_dinner.json()["shape_change"]["added"] == []
    week = composed_client.post(f"/api/plans/{plan['id']}/replan/{no_dinner.json()['id']}/confirm").json()["plan"]
    assert {d["meal_type"] for d in week["days"]} == {"lunch"}

    last = composed_client.post(f"/api/plans/{plan['id']}/shape/preview", json={"meal_type": "lunch"})
    assert last.status_code == 422 and "at least one meal" in last.json()["detail"]


def _conversation_week(client, minutes=90):
    """A week of two-dish dinners planned and confirmed in the conversation: the session and the plan."""
    profile = {
        **_household_profile_payload(),
        "max_cooking_time_minutes": minutes,
        "budget_per_meal_sgd": None,
        "weekly_budget_sgd": None,
        "health_preferences": [],
        "available_ingredients": [],
        "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
    }
    assert client.post("/api/household-profiles", json=profile).status_code == 201
    session = client.post("/api/agent/sessions", json={"message": "Plan our week"}).json()
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return session, confirmed.json()["plan"]


def test_a_weekend_soup_asked_for_in_the_conversation_replans_only_those_dinners(composed_client):
    from datetime import date

    session, plan = _conversation_week(composed_client)
    weekend = {d["day_index"] for d in plan["days"] if date.fromisoformat(d["planned_date"]).weekday() >= 5}
    before = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in plan["days"]}

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "Add a soup on weekends"}
    ).json()
    assert asked["pending_replan"]["event_type"] == "CHANGE_SHAPE", asked["messages"][-1]["content"]
    assert "Dinner with a soup on Saturday and Sunday." in asked["messages"][-1]["content"]
    assert asked["pending_replan"]["shape_change"]["day_indexes"] == sorted(weekend)

    after = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]["days"]
    assert {d["day_index"] for d in after if d["role_id"] == "soup"} == weekend
    # Every other meal is exactly as it was.
    others = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in after if d["day_index"] not in weekend}
    assert others == {key: slug for key, slug in before.items() if key[0] not in weekend}


def test_the_conversation_adds_a_meal_for_this_week_then_keeps_it_on_a_yes(composed_client):
    session, _ = _conversation_week(composed_client)

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "Also plan lunch"}
    ).json()
    assert asked["pending_replan"]["event_type"] == "CHANGE_SHAPE", asked["messages"][-1]["content"]
    assert "Nothing changes until you confirm" in asked["messages"][-1]["content"]

    applied = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()
    assert {d["meal_type"] for d in applied["plan"]["days"]} == {"lunch", "dinner"}
    question = applied["session"]["pending_interaction"]
    assert question["field_path"] == "plan_shape.keep"
    # Nothing is saved to the household before they say so.
    usual = composed_client.get("/api/household-profiles/current").json()["current"]["plan_shape"]["meals"]
    assert set(usual) == {"dinner"}

    composed_client.post(
        f"/api/agent/sessions/{session['id']}/interactions",
        json={
            "question_id": question["question_id"],
            "option_ids": ["keep"],
            "context_version": question["context_version"],
        },
    )
    usual = composed_client.get("/api/household-profiles/current").json()["current"]["plan_shape"]["meals"]
    assert set(usual) == {"lunch", "dinner"}


def test_a_second_plan_reuses_the_loaded_recipes(composed_client, monkeypatch):
    from app.repositories.recipe import clear_planning_pool

    monkeypatch.setattr(get_settings(), "planning_pool_cache_seconds", 300)
    clear_planning_pool()
    try:
        first = _week_ahead(composed_client)
        # The second plan reads recipes detached from the first request's session.
        second = _week_ahead(composed_client)
        assert [d["recipe"]["slug"] for d in second["days"]] == [d["recipe"]["slug"] for d in first["days"]]
        change = composed_client.post(
            f"/api/plans/{second['id']}/shape/preview", json={"meal_type": "dinner", "roles": COMPOSITION[:1]}
        )
        assert change.status_code == 201, change.text
    finally:
        clear_planning_pool()


def test_taking_the_vegetable_away_keeps_the_main_as_the_whole_meal(composed_client):
    plan = _week_ahead(composed_client, COMPOSITION[:2])
    main = next(d for d in plan["days"] if d["day_index"] == 2 and d["role_id"] == "main")

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION[:1], "day_indexes": [2]},
    ).json()
    assert [d["role_id"] for d in preview["shape_change"]["removed"]] == ["vegetable"]
    assert preview["shape_change"]["added"] == []

    week = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview['id']}/confirm").json()["plan"]
    tuesday = [d for d in week["days"] if d["day_index"] == 2]
    assert [(d["recipe"]["slug"], d["portion_share"]) for d in tuesday] == [(main["recipe"]["slug"], 1.0)]
    # 0.75 of the meal became all of it.
    assert tuesday[0]["nutrition_per_person"]["calories_kcal"] == round(
        main["nutrition_per_person"]["calories_kcal"] / 0.75, 2
    )


def test_adding_a_soup_to_one_dinner_keeps_its_main_and_vegetable(composed_client):
    plan = _week_ahead(composed_client, COMPOSITION[:2])
    for day in (3, 4):
        preview = composed_client.post(
            f"/api/plans/{plan['id']}/shape/preview",
            json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [day]},
        ).json()
        # The main and the vegetable stay where they are: only the soup is new.
        change = preview["shape_change"]
        assert [(d["role_id"], d["recipe_slug"]) for d in change["added"]] == [("soup", "tomato-soup")]
        assert (change["removed"], change["kept"]) == ([], 2)
    week = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview['id']}/confirm").json()["plan"]
    assert _dishes(week, 4) == {**_dishes(plan, 4), "soup": "tomato-soup"}


def _catalog_session():
    from app.db.session import get_db_session
    from app.main import app

    return next(app.dependency_overrides[get_db_session]())


def test_a_change_that_needs_one_ingredient_in_two_units_is_saved(composed_client):
    # Friday's soup takes whole eggs, the week's mains grams of egg: two shopping lines for one ingredient.
    from decimal import Decimal

    from sqlalchemy import select

    from app.models.recipe import Ingredient, Recipe, RecipeIngredient

    session = _catalog_session()
    egg = Ingredient(normalized_name="egg", display_name="egg")
    for slug, quantity, unit in (("salmon-bake", 100, "g"), ("chicken-roast", 100, "g"), ("tomato-soup", 2, "whole")):
        recipe = session.scalars(select(Recipe).where(Recipe.slug == slug)).one()
        recipe.recipe_ingredients.append(
            RecipeIngredient(ingredient=egg, quantity=Decimal(quantity), unit=unit, sort_order=2)
        )
    session.commit()
    plan = _week_ahead(composed_client, COMPOSITION[:2])

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [5]},
    )
    assert preview.status_code == 201, preview.text
    applied = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")

    assert applied.status_code == 200, applied.text
    items = applied.json()["plan"]["grocery_estimate"]["items"]
    assert sorted(item["unit"] for item in items if item["ingredient_name"] == "egg") == ["g", "whole"]


def test_a_swap_never_offers_the_same_dish_again(composed_client):
    # A catalog can hold one dish several times (eleven recipes are called "Singapore Noodles").
    from sqlalchemy import select

    from app.models.recipe import Ingredient

    session = _catalog_session()
    again = _dish("tomato-soup-again", "soup", "tomato", 450, calories=140, cook=25)
    again.title = "Tomato Soup"
    again.recipe_ingredients[0].ingredient = session.scalars(
        select(Ingredient).where(Ingredient.normalized_name == "tomato")
    ).one()
    session.add(again)
    session.commit()
    plan = _composed_plan(composed_client)
    soup = next(d for d in plan["days"] if d["day_index"] == 3 and d["role_id"] == "soup")

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"entry_id": soup["entry_id"], "event_type": "REPLACE_MEAL"},
    )

    assert preview.status_code == 422, preview.text
    assert "Tomato Soup" in preview.json()["detail"]


def _pasta_sides(count):
    """Sides of pasta alone, one shared ingredient row: not vegetable dishes (owner, 2026-10-02)."""
    sides = [_dish(f"buttered-pasta-{n:02d}", "side", "wholewheat_pasta", 200, calories=200) for n in range(count)]
    for side in sides[1:]:
        side.recipe_ingredients[0].ingredient = sides[0].recipe_ingredients[0].ingredient
    return sides


MAINS = [("salmon-bake", "salmon_fillet", 500), ("chicken-roast", "chicken_breast", 450)]


def test_the_vegetable_role_keeps_vegetable_dishes_however_many_better_sides_there_are(monkeypatch):
    """25 pasta sides rank before the one vegetable side; the candidates the planner keeps per course
    held only them, and the vegetable role had nothing to take."""
    mains = [_dish(slug, "main", ingredient, 400, calories=kcal) for slug, ingredient, kcal in MAINS]
    broccoli = _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100)  # added last: ranks last
    with dish_client(monkeypatch, [*mains, *_pasta_sides(25), broccoli]) as client:
        plan = _week_ahead(client, COMPOSITION[:2])

    assert {d["recipe"]["slug"] for d in plan["days"] if d["role_id"] == "vegetable"} == {"broccoli-stirfry"}


def test_a_whole_broccoli_the_release_weighed_as_a_floret_is_still_the_weeks_vegetable(monkeypatch):
    """The catalog row says "1 Broccoli" at 20 g; the planner reads the wording through to its candidate."""
    from decimal import Decimal

    from app.models.recipe import Ingredient, RecipeIngredient

    mains = [_dish(slug, "main", ingredient, 400, calories=kcal) for slug, ingredient, kcal in MAINS]
    bake = _dish("broccoli-egg-bake", "side", "egg", 200, calories=100)
    bake.recipe_ingredients.append(
        RecipeIngredient(
            ingredient=Ingredient(normalized_name="broccoli", display_name="broccoli"),
            quantity=Decimal(20),
            unit="g",
            original_text="1 Broccoli",
            sort_order=2,
        )
    )
    with dish_client(monkeypatch, [*mains, *_pasta_sides(1), bake]) as client:
        plan = _week_ahead(client, COMPOSITION[:2])

    assert {d["recipe"]["slug"] for d in plan["days"] if d["role_id"] == "vegetable"} == {"broccoli-egg-bake"}


def test_a_vegetable_swap_never_offers_a_side_not_led_by_vegetables(monkeypatch):
    mains = [_dish(slug, "main", ingredient, 400, calories=kcal) for slug, ingredient, kcal in MAINS]
    broccoli = _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100)
    with dish_client(monkeypatch, [*mains, broccoli, *_pasta_sides(1)]) as client:
        plan = _week_ahead(client, COMPOSITION[:2])
        vegetable = next(d for d in plan["days"] if d["day_index"] == 3 and d["role_id"] == "vegetable")
        preview = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": vegetable["entry_id"], "event_type": "REPLACE_MEAL"},
        )

    assert vegetable["recipe"]["slug"] == "broccoli-stirfry"
    assert preview.status_code == 422, preview.text  # the pasta is no vegetable to swap in
    assert "Broccoli Stirfry" in preview.json()["detail"]


def test_a_change_that_goes_over_the_weekly_budget_is_saved_as_over_it(composed_client):
    from datetime import date, timedelta

    request = {
        "start_date": (date.today() + timedelta(days=1)).isoformat(),
        "household_size": 4,
        "max_cooking_time_minutes": 90,
        "pricing_mode": "fixture",
        "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
    }
    unbudgeted = composed_client.post("/api/plans/generate", json=request).json()
    budget = unbudgeted["grocery_estimate"]["purchase_total_sgd"]
    plan = composed_client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": budget}).json()
    assert plan["grocery_estimate"]["within_weekly_budget"] is True

    # A soup on the last day buys tomatoes the week did not need: the checkout total passes the budget. (An
    # optional soup is left out instead: the rest of the week leaves nothing of the budget at the checkout.)
    soup = [*COMPOSITION[:2], {**COMPOSITION[2], "required": True}]
    preview = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": soup, "day_indexes": [7]},
    )
    assert preview.status_code == 201, preview.text
    applied = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm").json()["plan"]

    assert applied["grocery_estimate"]["purchase_total_sgd"] > budget
    assert applied["grocery_estimate"]["within_weekly_budget"] is False
    history = composed_client.get("/api/plans").json()["items"]
    assert next(week for week in history if week["id"] == plan["id"])["within_weekly_budget"] is False


def test_a_shape_change_nothing_fits_says_why_once(composed_client):
    plan = _week_ahead(composed_client)
    dessert = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "lunch", "roles": [{"role_id": "main", "courses": ["dessert"]}]},
    )
    assert dessert.status_code == 422, dessert.text
    # The conversation adds its own "I could not make that change: ", so the planner's reason comes bare.
    assert not dessert.json()["detail"].startswith("I could not"), dessert.json()["detail"]


# A change the household asks for that goes over the weekly budget is still offered, with how far over it
# goes, and the household confirms or discards it, as with a swap (owner decision 2026-10-02).
THREE_DISHES = [COMPOSITION[0], COMPOSITION[1], {**COMPOSITION[2], "required": True}]


def _budget_conversation_week(client, roles):
    """A week of `roles` dinners planned in the conversation with a weekly budget it just fits."""
    from datetime import date

    profile = {
        **_household_profile_payload(),
        "max_cooking_time_minutes": 240,
        "budget_per_meal_sgd": None,
        "health_preferences": [],
        "nutrition_targets": {},
        "available_ingredients": [],
        "plan_shape": {"meals": {"dinner": roles}},
    }
    request = {key: profile[key] for key in ("max_cooking_time_minutes", "pricing_mode", "plan_shape")}
    unbudgeted = client.post(
        "/api/plans/generate", json={**request, "start_date": date.today().isoformat(), "household_size": 2}
    )
    profile["weekly_budget_sgd"] = unbudgeted.json()["grocery_estimate"]["purchase_total_sgd"]
    assert client.post("/api/household-profiles", json=profile).status_code == 201
    session = client.post("/api/agent/sessions", json={"message": "Plan our week"}).json()
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return session, confirmed.json()["plan"]


def _spend_the_budget(client, plan, but_on_day):
    """Swap the other days' chicken for salmon, which a swap may do over the budget: none of it is left."""
    for dish in plan["days"]:
        if dish["day_index"] != but_on_day and dish["recipe"]["slug"] == "chicken-roast":
            preview = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={"entry_id": dish["entry_id"], "event_type": "REPLACE_MEAL"},
            )
            assert preview.status_code == 201, preview.text
            client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")
    week = client.get(f"/api/plans/{plan['id']}").json()
    assert week["grocery_estimate"]["within_weekly_budget"] is False
    return week


def _friday(plan) -> int:
    from datetime import date

    return next(d["day_index"] for d in plan["days"] if date.fromisoformat(d["planned_date"]).weekday() == 4)


def _dishes(plan, day) -> dict[str, str]:
    return {d["role_id"]: d["recipe"]["slug"] for d in plan["days"] if d["day_index"] == day}


def test_a_shape_change_within_the_budget_is_offered_as_before(composed_client):
    plan = _week_ahead(composed_client, COMPOSITION[:2])
    roomy = composed_client.post(
        "/api/plans/generate",
        json={
            **{key: plan[key] for key in ("start_date", "household_size")},
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
            "weekly_budget_sgd": round(plan["grocery_estimate"]["purchase_total_sgd"] * 1.5, 2),
        },
    ).json()

    preview = composed_client.post(
        f"/api/plans/{roomy['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [5]},
    ).json()

    assert preview["over_budget_sgd"] is None
    # The plan offered before over-budget changes existed (origin/main 407cd89): day 5's dishes and the soup.
    added = {d["role_id"]: d["recipe_slug"] for d in preview["shape_change"]["added"]}
    assert added == {"soup": "tomato-soup"}
    assert preview["purchase_total_delta_sgd"] == 2.8
    week = composed_client.post(f"/api/plans/{roomy['id']}/replan/{preview['id']}/confirm").json()["plan"]
    assert _dishes(week, 5) == {**_dishes(roomy, 5), "soup": "tomato-soup"}
    assert _dishes(week, 5) == {"main": "chicken-roast", "vegetable": "spinach-saute", "soup": "tomato-soup"}
    assert week["grocery_estimate"]["within_weekly_budget"] is True


def test_a_dish_the_budget_has_no_room_for_is_offered_with_how_far_over_it_goes(composed_client):
    # A quick soup ranks before the tomato soup, but its quinoa costs more: over the budget, the cheaper comes.
    database = _catalog_session()
    database.add(_dish("quinoa-soup", "soup", "quinoa", 500, calories=150, prep=5, cook=5))
    database.commit()
    session, plan = _budget_conversation_week(composed_client, COMPOSITION[:2])
    friday = _friday(plan)
    week = _spend_the_budget(composed_client, plan, but_on_day=friday)
    budget = week["grocery_estimate"]["weekly_budget_sgd"]

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "Add a soup on Friday"}
    ).json()
    change = asked["pending_replan"]
    assert change is not None and change["event_type"] == "CHANGE_SHAPE", asked["messages"][-1]["content"]
    assert "tomato-soup" in {d["recipe_slug"] for d in change["shape_change"]["added"]}
    over = change["over_budget_sgd"]
    after = week["grocery_estimate"]["purchase_total_sgd"] + change["purchase_total_delta_sgd"]
    assert over == round(after - budget, 2) > 0
    # Said as the preview card says it, before anything changes.
    assert f"S${over:.2f} over the S${budget:g} weekly budget." in asked["messages"][-1]["content"]

    # Keep as is: the week stays exactly as it was.
    composed_client.post(f"/api/agent/sessions/{session['id']}/replan/discard")
    kept = composed_client.get(f"/api/plans/{plan['id']}").json()
    assert (kept["revision"], kept["days"]) == (week["revision"], week["days"])

    # Confirm: the soup is added and the week says it is over its budget.
    composed_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": "Add a soup on Friday"})
    applied = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]
    assert set(_dishes(applied, friday)) == {"main", "vegetable", "soup"}
    assert applied["grocery_estimate"]["within_weekly_budget"] is False
    assert applied["grocery_estimate"]["purchase_total_sgd"] == round(budget + over, 2)


def test_another_soup_on_a_friday_that_has_one_keeps_its_dishes_over_the_budget(composed_client):
    # The 2026-10-02 walkthrough: a household with a soup every night asked for one more on Friday. With no
    # budget left it is still planned (over the budget), as another soup beside the dishes Friday has: a
    # second soup re-opened the soup course, so Friday's main and vegetable used to be replaced as well.
    from sqlalchemy import select

    from app.models.recipe import Ingredient

    database = _catalog_session()
    soup = _dish("broccoli-soup", "soup", "broccoli", 250, calories=90, cook=20)
    soup.recipe_ingredients[0].ingredient = database.scalars(
        select(Ingredient).where(Ingredient.normalized_name == "broccoli")
    ).one()
    database.add(soup)
    database.commit()
    session, plan = _budget_conversation_week(composed_client, THREE_DISHES)
    friday = _friday(plan)
    week = _spend_the_budget(composed_client, plan, but_on_day=friday)
    before = _dishes(week, friday)

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "周五晚餐加一个汤"}
    ).json()

    reply = asked["messages"][-1]["content"]
    change = asked["pending_replan"]
    assert change is not None, reply
    assert "周五" in reply and "再加一道汤" in reply and "Dinner" not in reply, reply
    # The dishes Friday had stay; the new soup is the other one.
    assert [d["recipe_slug"] for d in change["shape_change"]["added"]] == [
        *({"tomato-soup", "broccoli-soup"} - {before["soup"]})
    ]
    assert (change["shape_change"]["removed"], change["shape_change"]["kept"]) == ([], 3)
    # It needs no more than the broccoli the week buys: it costs nothing, so it is not said to put the
    # week over its budget, though the week is still over it.
    assert change["purchase_total_delta_sgd"] == 0
    assert change["over_budget_sgd"] is None and "over your" not in reply


def _broccoli_soup():
    """A second soup in the catalog, on the broccoli the vegetables already buy."""
    from sqlalchemy import select

    from app.models.recipe import Ingredient

    database = _catalog_session()
    soup = _dish("broccoli-soup", "soup", "broccoli", 250, calories=90, cook=20)
    soup.recipe_ingredients[0].ingredient = database.scalars(
        select(Ingredient).where(Ingredient.normalized_name == "broccoli")
    ).one()
    database.add(soup)
    database.commit()


def test_another_soup_on_a_day_that_got_one_in_the_conversation_keeps_its_dishes(composed_client):
    # The week plans main + vegetable; Friday got its soup from an earlier one-day change. "Another soup" is
    # read from what Friday has, not from the week's shape, so Friday's three dishes stay and a second soup
    # comes: read from the shape, it asked for main, vegetable and soup again and replanned all of Friday.
    _broccoli_soup()
    session, plan = _conversation_week(composed_client, minutes=240)  # four dishes take more than 90 minutes
    friday = _friday(plan)
    composed_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": "Add a soup on Friday"})
    week = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]
    before = _dishes(week, friday)
    assert set(before) == {"main", "vegetable", "soup"}

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "周五晚餐加一个汤"}
    ).json()

    reply = asked["messages"][-1]["content"]
    assert "周五" in reply and "再加一道汤" in reply and "Dinner" not in reply, reply
    # Friday's dishes stay (either soup may take either soup's place) and the other soup comes.
    other = {"tomato-soup", "broccoli-soup"} - {before["soup"]}
    expected = sorted([*before.values(), *other])
    assert [d["recipe_slug"] for d in asked["pending_replan"]["shape_change"]["added"]] == [*other]
    after = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]
    assert sorted(_dishes(after, friday).values()) == expected


def test_only_a_change_that_costs_more_is_said_to_put_the_week_over_its_budget(composed_client):
    from datetime import date

    session, plan = _budget_conversation_week(composed_client, COMPOSITION[:2])
    chicken = next(d for d in plan["days"] if d["recipe"]["slug"] == "chicken-roast")
    day = f"{date.fromisoformat(chicken['planned_date']):%A}"
    week = _spend_the_budget(composed_client, plan, but_on_day=chicken["day_index"])
    budget = week["grocery_estimate"]["weekly_budget_sgd"]

    def ask(message):
        asked = composed_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message}).json()
        composed_client.post(f"/api/agent/sessions/{session['id']}/replan/discard")
        return asked["pending_replan"], asked["messages"][-1]["content"]

    # A swap to a dearer dish: the reply says how far over, as the card does.
    swap, reply = ask(f"Swap {day}'s main")
    assert swap["event_type"] == "REPLACE_MEAL" and swap["purchase_total_delta_sgd"] > 0, reply
    assert swap["over_budget_sgd"] > 0
    assert f"S${swap['over_budget_sgd']:.2f} over the S${budget:g} weekly budget." in reply
    # Keeping a dish costs nothing and skipping one saves: neither puts the week anywhere.
    for message, event_type in ((f"Lock {day}'s vegetable", "LOCK_MEAL"), (f"Skip {day}'s main", "CANCEL_MEAL")):
        change, reply = ask(message)
        assert change["event_type"] == event_type and change["purchase_total_delta_sgd"] <= 0, reply
        assert change["over_budget_sgd"] is None
        assert "over your" not in reply, reply


def test_a_change_on_a_week_of_two_meals_a_day_goes_over_by_the_cheapest_week(monkeypatch):
    """Lunch and dinner every day, a tight budget; then dinners with a soup. Seven soups, one package
    each (S$1.85 to S$2.75): the cheapest change is one soup all week, costing S$1.85 more. A repeat is charged one
    meal's share of the budget, as the week's own planning charges it; charged a day's share (twice as much
    on two meals a day), seven different soups looked cheapest and the change went S$15.95 over."""
    from datetime import date, timedelta

    def only_for(meal, recipe):
        recipe.meal_types = [meal]
        return recipe

    soups = ["chickpea", "black_bean", "cucumber", "canned_tomato", "ginger", "garlic", "canned_tuna"]
    dishes = [
        only_for("lunch", _dish("chicken-lunch", "main", "chicken_breast", 400, calories=450)),
        only_for("lunch", _dish("tofu-lunch", "main", "firm_tofu", 300, calories=300)),
        only_for("dinner", _dish("sweet-potato-bake", "main", "sweet_potato", 200, calories=400)),
        *[only_for("dinner", _dish(f"{name}-soup", "soup", name, 100, calories=150)) for name in soups],
    ]
    main = {"role_id": "main", "courses": ["main"]}
    with dish_client(monkeypatch, dishes) as client:
        request = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"lunch": [main], "dinner": [main]}},
        }
        unbudgeted = client.post("/api/plans/generate", json=request).json()
        budget = unbudgeted["grocery_estimate"]["purchase_total_sgd"]
        plan = client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": budget}).json()
        assert plan["grocery_estimate"]["within_weekly_budget"] is True

        preview = client.post(
            f"/api/plans/{plan['id']}/shape/preview",
            json={"meal_type": "dinner", "roles": [main, {"role_id": "soup", "courses": ["soup"], "required": True}]},
        )

    assert preview.status_code == 201, preview.text
    added = preview.json()["shape_change"]["added"]
    assert {d["recipe_slug"] for d in added if d["role_id"] == "soup"} == {"chickpea-soup"}
    assert preview.json()["purchase_total_delta_sgd"] == 1.85
    # Budgeted planning can leave a little room compared with the unbudgeted week's price.
    # The soup still costs one whole package; only the part beyond the stated budget is "over".
    assert preview.json()["over_budget_sgd"] == round(plan["grocery_estimate"]["purchase_total_sgd"] + 1.85 - budget, 2)


def test_a_change_with_cheap_lunches_left_still_charges_a_repeat_one_meals_share(monkeypatch):
    """As above, but the lunches cost little and the dinners most of the budget (S$3.80 of S$25.60), so what the
    rest of the week leaves (S$21.80) is more than the dinners' share of the budget (S$12.80). A repeat is still
    charged one meal's share (S$1.83): one soup all week, S$1.85 over. Charged what is left per dinner instead
    (S$3.11, nearly a day's share), seven different soups looked cheapest and the change went S$15.95 over."""
    from datetime import date, timedelta

    def only_for(meal, recipe):
        recipe.meal_types = [meal]
        return recipe

    soups = ["chickpea", "black_bean", "cucumber", "canned_tomato", "ginger", "garlic", "canned_tuna"]
    dishes = [
        only_for("lunch", _dish("sweet-potato-lunch", "main", "sweet_potato", 200, calories=450)),
        # 70 g of salmon a dinner: two packages a week whether the main is the whole meal or three quarters of it.
        only_for("dinner", _dish("salmon-dinner", "main", "salmon_fillet", 140, calories=400)),
        *[only_for("dinner", _dish(f"{name}-soup", "soup", name, 100, calories=150)) for name in soups],
    ]
    main = {"role_id": "main", "courses": ["main"]}
    with dish_client(monkeypatch, dishes) as client:
        request = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"lunch": [main], "dinner": [main]}},
            "weekly_budget_sgd": 25.6,
        }
        plan = client.post("/api/plans/generate", json=request).json()
        assert plan["grocery_estimate"]["purchase_total_sgd"] == 25.6
        assert {d["recipe"]["slug"] for d in plan["days"] if d["meal_type"] == "lunch"} == {"sweet-potato-lunch"}

        preview = client.post(
            f"/api/plans/{plan['id']}/shape/preview",
            json={"meal_type": "dinner", "roles": [main, {"role_id": "soup", "courses": ["soup"], "required": True}]},
        )

    assert preview.status_code == 201, preview.text
    added = preview.json()["shape_change"]["added"]
    assert {d["recipe_slug"] for d in added if d["role_id"] == "soup"} == {"chickpea-soup"}
    assert preview.json()["over_budget_sgd"] == 1.85


def test_dinners_with_a_soup_keep_each_days_main_and_vegetable(composed_client):
    """A soup added to every dinner keeps each day's dishes, each in its place (the 2026-10-02 review of
    mdw-dev-019): the dishes were kept only for a change on one day, and a change on several planned all their
    dinners again."""
    plan = _week_ahead(composed_client, COMPOSITION[:2])
    # A swap makes Monday a dinner the planner would not choose, so planning the week again would change it.
    monday = next(d for d in plan["days"] if d["day_index"] == 1 and d["role_id"] == "main")
    swap = composed_client.post(
        f"/api/plans/{plan['id']}/replan/preview", json={"entry_id": monday["entry_id"], "event_type": "REPLACE_MEAL"}
    ).json()
    week = composed_client.post(f"/api/plans/{plan['id']}/replan/{swap['id']}/confirm").json()["plan"]

    preview = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": [*COMPOSITION[:2], {**COMPOSITION[2], "required": True}]},
    )

    assert preview.status_code == 201, preview.text
    after = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm").json()["plan"]
    for day in range(1, 8):
        assert _dishes(after, day) == {**_dishes(week, day), "soup": "tomato-soup"}, day


def test_a_soup_added_day_by_day_over_the_budget_is_the_one_the_week_already_buys(monkeypatch):
    """Over the budget, a dish the rest of the week has is weighed against new ones: Tuesday's soup is
    Monday's, from the package the week already buys. Drawn first from dishes the week did not have, every day
    bought a new soup (the 2026-10-02 review: S$96.82 over on mdw-dev-019 at S$40)."""
    from datetime import date, timedelta

    soups = ["chickpea", "black_bean", "cucumber", "canned_tomato"]
    dishes = [
        _dish("sweet-potato-bake", "main", "sweet_potato", 200, calories=400),
        *[_dish(f"{name}-soup", "soup", name, 100, calories=150) for name in soups],
    ]
    main = {"role_id": "main", "courses": ["main"]}
    soup = {"role_id": "soup", "courses": ["soup"], "required": True}
    with dish_client(monkeypatch, dishes) as client:
        request = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": [main]}},
        }
        unbudgeted = client.post("/api/plans/generate", json=request).json()
        budget = unbudgeted["grocery_estimate"]["purchase_total_sgd"]
        plan = client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": budget}).json()
        previews = []
        for day in (1, 2):
            preview = client.post(
                f"/api/plans/{plan['id']}/shape/preview",
                json={"meal_type": "dinner", "roles": [main, soup], "day_indexes": [day]},
            )
            assert preview.status_code == 201, preview.text
            previews.append(preview.json())
            week = client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm").json()["plan"]

    assert {_dishes(week, day)["soup"] for day in (1, 2)} == {"chickpea-soup"}
    assert previews[0]["over_budget_sgd"] == 1.85
    # Tuesday's soup comes from Monday's package: nothing more to buy.
    assert previews[1]["purchase_total_delta_sgd"] == 0


def _lunch_and_dinner_dishes(lunch=None, grams=None):
    """Seven cheap dishes for lunch or dinner and seven dearer ones for lunch only, each of one ingredient
    (100 g, or `grams` of it)."""
    both = ["chickpea", "firm_tofu", "black_bean", "cucumber", "canned_tomato", "ginger", "garlic"]
    lunch = lunch or ["mushroom", "zucchini", "sweet_potato", "chicken_breast", "tomato", "soba_noodle", "brown_rice"]
    dishes = []
    for names, meals in ((both, ["lunch", "dinner"]), (lunch, ["lunch"])):
        for name in names:
            dish = _dish(f"{name}-plate", "main", name, (grams or {}).get(name, 100), calories=450)
            dish.meal_types = meals
            dishes.append(dish)
    return dishes


@pytest.mark.parametrize("cap", [1, 2])
def test_a_meal_added_over_the_budget_keeps_the_households_cap_across_the_week(monkeypatch, cap):
    """'No dish twice' (or 'at most twice') holds for the whole week when a meal is added over the budget: the
    dinners' dishes are the cheapest lunches, and the planner held the cap only among the meals it planned
    (the 2026-10-02 review: 'Also plan lunch' on mdw-dev-013 served five of its dinner salads again)."""
    from collections import Counter
    from datetime import date, timedelta

    main = {"role_id": "main", "courses": ["main"]}
    with dish_client(monkeypatch, _lunch_and_dinner_dishes()) as client:
        request = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": [main]}},
            "max_uses_per_recipe": cap,
        }
        unbudgeted = client.post("/api/plans/generate", json=request).json()
        budget = unbudgeted["grocery_estimate"]["purchase_total_sgd"]
        plan = client.post("/api/plans/generate", json={**request, "weekly_budget_sgd": budget}).json()
        assert max(Counter(d["recipe"]["slug"] for d in plan["days"]).values()) <= cap

        preview = client.post(f"/api/plans/{plan['id']}/shape/preview", json={"meal_type": "lunch", "roles": [main]})
        assert preview.status_code == 201, preview.text
        week = client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm").json()["plan"]

    assert {d["meal_type"] for d in week["days"]} == {"lunch", "dinner"} and len(week["days"]) == 14
    uses = Counter(d["recipe"]["slug"] for d in week["days"])
    assert max(uses.values()) <= cap, uses


def test_a_dish_added_to_every_dinner_is_the_only_new_one_in_the_reply_and_on_the_card(composed_client):
    """'Dinners with a soup' keeps every day's main and vegetable, so the reply and the card name only the soup
    as new and nothing comes off (the 2026-10-02 review: the reply listed the kept dinners under 'New:' and said
    '14 dishes come off the week')."""
    session, plan = _conversation_week(composed_client)

    asked = composed_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "Dinners with a soup"}
    ).json()

    reply = asked["messages"][-1]["content"]
    change = asked["pending_replan"]["shape_change"]
    assert {d["recipe_slug"] for d in change["added"]} == {"tomato-soup"}, reply
    assert (change["removed"], change["kept"]) == ([], len(plan["days"]))
    assert "New: Tomato Soup." in reply and "come off" not in reply, reply


def test_a_meal_added_over_the_budget_counts_repeats_with_the_rest_of_the_week(monkeypatch):
    """Over the budget, a dish the rest of the week has costs a repeat (one meal's share of the budget, S$2.00
    here), as a repeat among the meals planned does. Each meal here takes one whole package: the week's dinners
    as lunches cost S$15.15 and seven repeats (S$14.00), seven new lunches S$24.55. Repeats with the rest of
    the week went uncharged, and every lunch was one of the week's dinners (the 2026-10-02 review: 'Also plan
    lunch' on mdw-dev-013 at S$180 served seven of its dinners again)."""
    from collections import Counter
    from datetime import date, timedelta

    package = {"chickpea": 400, "firm_tofu": 300, "black_bean": 400, "cucumber": 500, "canned_tomato": 400}
    package |= {"ginger": 300, "garlic": 300, "broccoli": 300, "wholewheat_pasta": 500, "baby_spinach": 200}
    package |= {"mushroom": 300, "zucchini": 500, "chicken_breast": 300, "soba_noodle": 300}
    lunch = ["broccoli", "wholewheat_pasta", "baby_spinach", "mushroom", "zucchini", "chicken_breast", "soba_noodle"]
    # A recipe serves four, the household two: twice a package is one package a meal.
    dishes = _lunch_and_dinner_dishes(lunch, grams={name: 2 * size for name, size in package.items()})
    main = {"role_id": "main", "courses": ["main"]}
    with dish_client(monkeypatch, dishes) as client:
        request = {
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 2,
            "max_cooking_time_minutes": 240,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": [main]}},
            # S$12.85 left: seven lunches cost at least S$12.95 (chickpeas every day).
            "weekly_budget_sgd": 28.0,
        }
        plan = client.post("/api/plans/generate", json=request).json()
        assert plan["grocery_estimate"]["purchase_total_sgd"] == 15.15
        assert max(Counter(d["recipe"]["slug"] for d in plan["days"]).values()) == 1

        preview = client.post(f"/api/plans/{plan['id']}/shape/preview", json={"meal_type": "lunch", "roles": [main]})
        assert preview.status_code == 201, preview.text
        week = client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm").json()["plan"]

    assert {d["recipe"]["slug"] for d in week["days"] if d["meal_type"] == "lunch"} == {f"{n}-plate" for n in lunch}
    assert preview.json()["over_budget_sgd"] == round(15.15 + 24.55 - 28.0, 2)
