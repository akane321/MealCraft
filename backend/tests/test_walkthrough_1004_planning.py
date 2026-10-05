"""The 2026-10-04 walkthrough's planning findings, on small catalogs and on the walkthrough household.

- P3: the reply that took the last detail planned the week to check it, and Plan planned it again (13-17 s).
- P4: "the dishes are boring" (菜很单调) swaps the week's repeated dishes for different ones within its budget
  (owner, 2026-10-04); lunches added to a week were one slaw five times.
- P8: a swap's replacement was a lunch at dinner, or took the week S$9 to S$17 over its budget.
"""

import re
from collections import Counter
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.parser import RuleBasedConstraintParser
from app.api.routes.meal_plans import build_meal_plan_service, build_replanning_service
from app.core.config import get_settings
from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import import_release_v2
from app.db.base import Base
from app.planning.product_path import ProductPlanningEngine, meal_affinity
from app.planning.recipe_quality import dish_family
from app.repositories.agent import AgentSessionRepository
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.recipe import clear_planning_pool
from app.schemas.agent import AgentConstraintState
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanReplanPreviewRequest, MealPlanShapeChangeRequest
from app.services.agent import AgentSessionService
from tests.test_planning_capability import _dish, dish_client


@pytest.fixture
def searches(monkeypatch):
    """Every week search the planner runs, in order: True for a cheapest-week search."""
    found: list[bool] = []
    plan = ProductPlanningEngine.plan

    def counted(self, constraints, *args, **kwargs):
        found.append(bool(kwargs.get("cheapest")))
        return plan(self, constraints, *args, **kwargs)

    monkeypatch.setattr(ProductPlanningEngine, "plan", counted)
    return found


@contextmanager
def kept_for(seconds: int):
    """Recipe pools and found weeks kept as long as production keeps them (tests keep none: see conftest)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(get_settings(), "planning_pool_cache_seconds", seconds)
        clear_planning_pool()  # and the weeks found from it
        try:
            yield
        finally:
            clear_planning_pool()


def add(*dishes) -> None:
    """Recipes added to the catalog of the client in use (`dish_client`)."""
    from app.db.session import get_db_session
    from app.main import app

    sessions = app.dependency_overrides[get_db_session]()
    session = next(sessions)
    session.add_all(dishes)
    session.commit()
    sessions.close()


def planned(client, message: str) -> dict:
    session = client.post("/api/agent/sessions", json={"message": message}).json()
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["session"]


def say(client, session: dict, message: str) -> dict:
    response = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def week(client, plan_id: int) -> dict:
    return client.get(f"/api/plans/{plan_id}").json()


def mains(*pairs, grams: int = 100) -> list:
    return [_dish(slug, "main", ingredient, grams, calories=450) for slug, ingredient in pairs]


# P3 ------------------------------------------------------------------------------------------------------------


EIGHT = [
    ("tofu-bowl", "firm_tofu"),
    ("chickpea-stew", "chickpea"),
    ("tuna-melt", "canned_tuna"),
    ("tomato-stew", "canned_tomato"),
    ("broccoli-bake", "broccoli"),
    ("pasta-toss", "wholewheat_pasta"),
    ("mushroom-rice", "mushroom"),
    ("bean-chili", "black_bean"),
]


@pytest.mark.parametrize(("seconds", "searched"), [(300, [False]), (0, [False, False])])
def test_plan_saves_the_week_the_reply_checked_instead_of_searching_it_again(monkeypatch, searches, seconds, searched):
    """The reply that takes the last detail plans the week to check it (agent/limits.py); while the planner's
    pools are kept, Plan saves that week rather than search for it a second time."""
    with kept_for(seconds), dish_client(monkeypatch, mains(*EIGHT)) as client:
        session = client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$40 total"}).json()
        assert session["status"] == "ready", session["messages"][-1]["content"]
        assert searches == [False]

        confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        assert searches == searched
        assert confirmed.json()["plan"]["grocery_estimate"]["purchase_total_sgd"] <= 40


def test_a_kept_week_is_saved_once_and_only_for_the_request_it_was_found_for(monkeypatch, searches):
    with kept_for(300), dish_client(monkeypatch, mains(*EIGHT)) as client:
        session = client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$40 total"}).json()
        changed = say(client, session, "S$45 for the week")  # a new request: checked again, and that week kept
        assert changed["constraints"]["weekly_budget_sgd"] == 45 and searches == [False, False]
        client.post(f"/api/agent/sessions/{session['id']}/confirm")
        assert searches == [False, False]
        again = client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$45 total"}).json()
        assert again["status"] == "ready" and searches == [False, False, False]


# P4 ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("complaint", "swapped", "left"),
    [
        (
            "the dishes are boring",
            r"For more variety: (Tofu Bowl|Chickpea Stew) on [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2} becomes Bean Chili\.",
            r" 4 more stay as they are: the closest different dish I found for them needs S\$(\d+\.\d\d) more than "
            r"the S\$8\.00 the week can spend\. Nothing changes until you confirm\.",
        ),
        (
            "菜很单调,不太好",
            r"多些花样：周[一二三四五六日] \d{1,2}月\d{1,2}日的(Tofu Bowl|Chickpea Stew)换成Bean Chili。",
            r"另外 4 道重复的菜先不换：我找到的最接近的换法也要比这周能花的 S\$8\.00 多 S\$(\d+\.\d\d)。"
            r"确认之前什么都不会改。",
        ),
    ],
)
def test_a_week_found_boring_has_its_repeated_dishes_swapped_within_its_budget(monkeypatch, complaint, swapped, left):
    """Two mains for seven dinners, then two more in the catalog: one fits what S$8 leaves, salmon does not.
    One preview swaps what fits; the rest stay, and the reply says what the closest one would take."""
    with dish_client(monkeypatch, mains(("tofu-bowl", "firm_tofu"), ("chickpea-stew", "chickpea"))) as client:
        session = planned(client, "Dinners for 4, S$8 total")
        before = week(client, session["plan_id"])
        assert len({dish["recipe"]["slug"] for dish in before["days"]}) == 2
        add(*mains(("bean-chili", "black_bean"), ("salmon-bake", "salmon_fillet")))

        answered = say(client, session, complaint)
        reply = answered["messages"][-1]["content"]
        assert re.fullmatch(swapped + left, reply), reply
        preview = answered["pending_replan"]
        assert preview["status"] == "previewed" and preview["over_budget_sgd"] is None
        change = preview["shape_change"]
        assert [dish["recipe_slug"] for dish in change["added"]] == ["bean-chili"]
        (removed,) = change["removed"]
        first = min(d["day_index"] for d in before["days"] if d["recipe"]["slug"] == removed["recipe_slug"])
        assert removed["day_index"] > first  # the first of a repeated dish stays

        applied = client.post(f"/api/agent/sessions/{session['id']}/replan/confirm")
        assert applied.status_code == 200, applied.text
        after = applied.json()["plan"]
        assert len({dish["recipe"]["slug"] for dish in after["days"]}) == 3
        assert after["grocery_estimate"]["purchase_total_sgd"] <= 8


def test_a_week_whose_repeats_no_different_dish_fits_stays_and_says_what_it_would_take(monkeypatch):
    with dish_client(monkeypatch, mains(("tofu-bowl", "firm_tofu"), ("chickpea-stew", "chickpea"))) as client:
        session = planned(client, "Dinners for 4, S$8 total")
        add(*mains(("salmon-bake", "salmon_fillet")))
        total = week(client, session["plan_id"])["grocery_estimate"]["purchase_total_sgd"]

        answered = say(client, session, "the dishes are boring")
        reply = answered["messages"][-1]["content"]
        found = re.fullmatch(
            r"No different dish fits in place of the repeated ones: the closest swap I found needs S\$(\d+\.\d\d) "
            r"more than the S\$8\.00 the week can spend\. I can swap a dish anyway\.",
            reply,
        )
        assert found, reply
        # Backed by the salmon: its package bought for one dinner, less what that dinner no longer buys.
        assert 0 < float(found.group(1)) <= round(total + 10.90 - 8, 2)
        assert answered["pending_replan"] is None and answered["plan_id"] == session["plan_id"]
        assert answered["pending_interaction"]["options"][0]["label"].startswith("Swap the ")


# P8 ------------------------------------------------------------------------------------------------------------


SEVEN = EIGHT[:7]


def a_week_of_seven(client) -> dict:
    """Seven mains of one package each, S$18.35 within S$20; then three more dinners in the catalog."""
    response = client.post(
        "/api/plans/generate",
        json={
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "weekly_budget_sgd": 20,
            "pricing_mode": "fixture",
            "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
        },
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["grocery_estimate"]["purchase_total_sgd"] == 18.35
    # Quickest first, so best ranked first: a breakfast bowl, a dear salmon dinner, then a cheap slow chili.
    bowl = _dish("cucumber-bowl", "main", "cucumber", 100, calories=450, prep=2, cook=3)
    bowl.meal_types = ["breakfast"]
    salmon = _dish("salmon-bake", "main", "salmon_fillet", 100, calories=500, prep=5, cook=5)
    add(bowl, salmon, _dish("bean-chili", "main", "black_bean", 100, calories=450, prep=10, cook=40))
    return plan


@pytest.mark.parametrize("event", ["REPLACE_MEAL", "ITEM_UNAVAILABLE"])
def test_a_swap_takes_a_dinner_that_keeps_the_week_within_its_budget(monkeypatch, event):
    with dish_client(monkeypatch, mains(*SEVEN)) as client:
        plan = a_week_of_seven(client)
        first = next(dish for dish in plan["days"] if dish["day_index"] == 1)
        request = {"entry_id": first["entry_id"], "event_type": event}
        if event == "ITEM_UNAVAILABLE":
            request["unavailable_ingredient"] = dict(SEVEN)[first["recipe"]["slug"]]

        preview = client.post(f"/api/plans/{plan['id']}/replan/preview", json=request)
        assert preview.status_code == 201, preview.text
        # Not the breakfast bowl (a dinner fits), nor the salmon (S$27 for the week): the chili fits S$20.
        assert preview.json()["after_entry"]["recipe_slug"] == "bean-chili"
        assert preview.json()["over_budget_sgd"] is None
        assert plan["grocery_estimate"]["purchase_total_sgd"] + preview.json()["purchase_total_delta_sgd"] <= 20


def test_a_swap_asked_for_by_name_keeps_what_was_asked_and_says_the_overage(monkeypatch):
    with dish_client(monkeypatch, mains(*SEVEN)) as client:
        plan = a_week_of_seven(client)
        first = next(dish for dish in plan["days"] if dish["day_index"] == 1)
        preview = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": first["entry_id"], "event_type": "REPLACE_MEAL", "reason": "something with salmon"},
        ).json()
        assert preview["after_entry"]["recipe_slug"] == "salmon-bake"
        assert preview["over_budget_sgd"] > 0


# The walkthrough household on the full catalog ---------------------------------------------------------------

WALKTHROUGH = AgentConstraintState.model_validate(
    {
        "household_size": 2,
        "allergens": ["peanut"],
        "excluded_ingredients": ["pork"],
        "weekly_budget_sgd": 100.0,
        "pricing_mode": "fixture",
        "plan_shape": {"meals": {"dinner": MEAL_PRESETS["dinner"]["main, vegetable and soup"]}},
    }
)
FIRST_MESSAGE = "Plan our dinners this week: two of us, one has a peanut allergy, no pork, S$100 for the week"


def agent(session) -> AgentSessionService:
    return AgentSessionService(
        repository=AgentSessionRepository(session, household_id=1),
        run_repository=AgentRunRepository(session, household_id=1),
        parser=RuleBasedConstraintParser(),
        meal_plan_service=build_meal_plan_service(session, 1, 1),
        replanning_service=build_replanning_service(session, 1, 1),
        actor_user_id=1,
        household_id=1,
        starting_constraints=WALKTHROUGH,
    )


@pytest.fixture(scope="module")
def walked():
    """The walkthrough household's first message and Plan, on a database seeded as compose seeds it, with the
    planner's searches counted in each."""
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
    with kept_for(300), pytest.MonkeyPatch.context() as patch:
        calls: list[bool] = []
        plan = ProductPlanningEngine.plan

        def counted(self, constraints, *args, **kwargs):
            calls.append(bool(kwargs.get("cheapest")))
            return plan(self, constraints, *args, **kwargs)

        patch.setattr(ProductPlanningEngine, "plan", counted)
        with factory() as session:
            snapshot = agent(session).create(FIRST_MESSAGE)
        replied = list(calls)
        with factory() as session:
            confirmed = agent(session).confirm(snapshot.id)
        yield {
            "factory": factory,
            "session_id": snapshot.id,
            "status": snapshot.status,
            "plan": confirmed.plan,
            "searches": (replied, calls[len(replied) :]),
        }
    engine.dispose()


def test_the_walkthrough_household_is_planned_from_one_search(walked):
    """Message to week took 13-17 s: the check and Plan each searched the week (P3)."""
    assert walked["status"] == "ready"
    assert walked["searches"] == ([False], [])
    assert walked["plan"].grocery_estimate.purchase_total_sgd <= 100


def test_the_walkthrough_week_found_boring_swaps_its_repeats_within_its_budget(walked):
    plan = walked["plan"]
    served = Counter(dish_family(dish.recipe.title) for dish in plan.days)
    assert max(served.values()) > 1, served  # the walkthrough's week repeats a dish
    with kept_for(300), walked["factory"]() as session:
        answered = agent(session).reply(walked["session_id"], "the dishes are boring")
    preview = answered.pending_replan
    assert preview is not None, answered.messages[-1].content
    assert answered.messages[-1].content.startswith("For more variety: ")
    change = preview.shape_change
    assert {dish_family(dish.recipe_title) for dish in change.added}.isdisjoint(served)
    assert all(served[dish_family(dish.recipe_title)] > 1 for dish in change.removed)
    assert plan.grocery_estimate.purchase_total_sgd + preview.purchase_total_delta_sgd <= 100


def test_lunch_added_to_the_walkthrough_week_is_not_one_dish_all_week(walked):
    """The walkthrough's added lunches were Lou's German Slaw five times of seven."""
    with kept_for(300), walked["factory"]() as session:
        preview = build_replanning_service(session, 1, 1).preview_shape(
            plan_id=walked["plan"].id,
            request=MealPlanShapeChangeRequest(meal_type="lunch", roles=MEAL_PRESETS["lunch"]["one dish"]),
            today=walked["plan"].start_date,
        )
    lunches = Counter(dish_family(dish.recipe_title) for dish in preview.shape_change.added)
    assert sum(lunches.values()) == 7
    assert max(lunches.values()) <= 2, lunches


@pytest.mark.parametrize("event", ["REPLACE_MEAL", "ITEM_UNAVAILABLE"])
def test_a_swap_in_the_walkthrough_week_keeps_it_within_its_budget_with_a_dinner(walked, event):
    """The walkthrough's swaps took the week S$9 to S$17 over S$100, one with a lunch dish at dinner."""
    plan = walked["plan"]
    entry = next(dish for dish in plan.days if dish.day_index == 2 and dish.role_id == "main")
    with kept_for(300), walked["factory"]() as session:
        service = build_replanning_service(session, 1, 1)
        unavailable = None
        if event == "ITEM_UNAVAILABLE":
            recipe = service.recipe_repository.list_by_ids([entry.recipe.id])[0]
            unavailable = recipe.recipe_ingredients[0].ingredient.normalized_name
        preview = service.preview(
            plan_id=plan.id,
            request=MealPlanReplanPreviewRequest(
                event_type=event, entry_id=entry.entry_id, unavailable_ingredient=unavailable
            ),
        )
        chosen = service.recipe_repository.list_by_ids([preview.after_entry.recipe_id])[0]
    assert preview.over_budget_sgd is None
    assert plan.grocery_estimate.purchase_total_sgd + preview.purchase_total_delta_sgd <= 100
    assert "dinner" in meal_affinity(chosen)
    if unavailable:
        assert unavailable not in {line.ingredient.normalized_name for line in chosen.recipe_ingredients}
