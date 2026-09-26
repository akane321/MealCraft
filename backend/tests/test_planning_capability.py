"""The planning capability switch of ADR-0036 section 6: mvp refuses meal compositions."""

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


@pytest.fixture
def composed_client(monkeypatch):
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
        session.add_all(
            [
                _dish("salmon-bake", "main", "salmon_fillet", 400, calories=500),
                _dish("chicken-roast", "main", "chicken_breast", 400, calories=450),
                _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
                _dish("spinach-saute", "side", "baby_spinach", 200, calories=80),
                _dish("zucchini-salad", "salad", "zucchini", 300, calories=60),
                _dish("tomato-soup", "soup", "tomato", 500, calories=150, cook=25),
            ]
        )
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
    assert {d["role_id"] for d in change["added"]} == {"main", "vegetable", "soup"}
    assert len(change["removed"]) == 2

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


def test_the_conversation_adds_a_meal_for_this_week_then_keeps_it_on_a_yes(composed_client):
    profile = {
        **_household_profile_payload(),
        "max_cooking_time_minutes": 90,
        "budget_per_meal_sgd": None,
        "weekly_budget_sgd": None,
        "health_preferences": [],
        "available_ingredients": [],
        "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
    }
    assert composed_client.post("/api/household-profiles", json=profile).status_code == 201
    session = composed_client.post("/api/agent/sessions", json={"message": "Plan our week"}).json()
    confirmed = composed_client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text

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
