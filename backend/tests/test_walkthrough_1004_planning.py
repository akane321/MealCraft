"""The 2026-10-04 walkthrough's planning findings, on small catalogs and on the walkthrough household.

- P3: the reply that took the last detail planned the week to check it, and Plan planned it again (13-17 s).
- P4: "the dishes are boring" (菜很单调) swaps the week's repeated dishes for different ones within its budget
  (owner, 2026-10-04); lunches added to a week were one slaw five times.
- P8: a swap's replacement was a lunch at dinner, or took the week S$9 to S$17 over its budget.
- Review round 1: the first answer after startup, or after the recipe pool aged, loaded the pool (3.5-4.5 s on
  PostgreSQL), taking an OpenAI-mode answer past 10 s.
- Review round 3: the pool aged 300 s after it was loaded, and the first answer after that loaded it again (about
  11 s in OpenAI mode); it is now loaded again in the background before it ages.
"""

import logging
import math
import re
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent import limits
from app.agent.parser import RuleBasedConstraintParser
from app.api.routes.meal_plans import build_meal_plan_service, build_replanning_service
from app.core.config import get_settings
from app.core.paths import repository_root
from app.data.catalog import Catalog, import_catalog, load_catalog
from app.data.release_v2 import import_release_v2
from app.db.base import Base
from app.main import load_planning_pool, warm_planning_pool
from app.planning.product_path import ProductPlanningEngine, meal_affinity
from app.planning.recipe_quality import dish_family, incomplete
from app.repositories.agent import AgentSessionRepository
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.recipe import RecipeRepository, _planning_pool, clear_planning_pool
from app.repositories.recipe import _reloading as reloading_binds
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
        # The API's startup would load the pool of the configured database, not the test's catalog.
        patch.setattr("app.main.warm_planning_pool", lambda *_: None, raising=False)
        patch.setattr("app.main.load_planning_pool", lambda: None, raising=False)
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


def checked_at_the_shop(plan_id: int, total: float, budget: float) -> None:
    """The week as a live plan saves it: its basket checked at FairPrice on confirm, above its snapshot (ADR-0058),
    with a weekly budget of `budget`."""
    from app.db.session import get_db_session
    from app.main import app
    from app.models.meal_plan import MealPlan

    sessions = app.dependency_overrides[get_db_session]()
    session = next(sessions)
    plan = session.get(MealPlan, plan_id)
    plan.pricing_mode, plan.purchase_total_sgd, plan.weekly_budget_sgd = "live", total, budget
    plan.constraints = {**plan.constraints, "weekly_budget_sgd": budget}
    session.commit()
    sessions.close()


def test_a_swap_of_a_week_priced_at_the_shop_is_chosen_and_previewed_at_its_saved_total(monkeypatch):
    """2026-10-09 rehearsal: a live week saved at S$97.26 took a swap that fit S$100 at snapshot prices, and its
    preview said nothing; confirming it checked the new basket and the week came to S$100.16. The swap is chosen,
    and its preview totalled, from the saved total moved by the snapshot difference."""
    with dish_client(monkeypatch, mains(*SEVEN)) as client:
        plan = a_week_of_seven(client)  # S$18.35 at snapshot prices
        first = next(dish for dish in plan["days"] if dish["day_index"] == 1)
        swap = {"entry_id": first["entry_id"], "event_type": "REPLACE_MEAL"}
        salmon = {**swap, "reason": "something with salmon"}
        dearer = client.post(f"/api/plans/{plan['id']}/replan/preview", json=salmon).json()["purchase_total_delta_sgd"]
        cheaper = client.post(f"/api/plans/{plan['id']}/replan/preview", json=swap).json()["purchase_total_delta_sgd"]
        # The salmon, ranked first, fits the budget at snapshot prices; not once the week is S$1.00 dearer at the shop.
        budget = round(18.35 + dearer + 0.5, 2)
        checked_at_the_shop(plan["id"], 19.35, budget)

        preview = client.post(f"/api/plans/{plan['id']}/replan/preview", json=swap).json()
        assert preview["after_entry"]["recipe_slug"] == "bean-chili"
        assert preview["over_budget_sgd"] is None
        assert preview["purchase_total_delta_sgd"] == cheaper  # the snapshot difference, not snapshot minus shop
        # Asked for, the salmon stays, and its preview says the overage at the saved total before confirming.
        asked = client.post(f"/api/plans/{plan['id']}/replan/preview", json=salmon).json()
        assert asked["after_entry"]["recipe_slug"] == "salmon-bake"
        assert asked["purchase_total_delta_sgd"] == dearer
        assert asked["over_budget_sgd"] == 0.5


def test_a_swap_preview_says_what_it_does_to_the_groceries_and_the_budget():
    preview = SimpleNamespace(
        event_type="REPLACE_MEAL",
        before_entry=SimpleNamespace(recipe_title="Teriyaki Fried Rice"),
        after_entry=SimpleNamespace(recipe_title="Dinner Tonight: Kimchi Chahan (Fried Rice) Recipe"),
        purchase_total_delta_sgd=2.9,
        over_budget_sgd=0.16,
    )
    plan = SimpleNamespace(grocery_estimate=SimpleNamespace(weekly_budget_sgd=100.0))
    describe = AgentSessionService.__new__(AgentSessionService)._describe_dish_preview
    assert describe(preview, plan, "en") == (
        "How about Kimchi Chahan (Fried Rice) instead of Teriyaki Fried Rice? Groceries +S$2.90. "
        "That makes the week S$100.16, S$0.16 over the S$100 weekly budget. Nothing changes until you confirm."
    )
    assert describe(preview, plan, "zh") == (
        "把Teriyaki Fried Rice换成Kimchi Chahan (Fried Rice)怎么样？买菜多花 S$2.90。"
        "这样这周要 S$100.16，超出每周 S$100 的预算 S$0.16。确认之前什么都不会改。"
    )
    within = SimpleNamespace(**{**vars(preview), "purchase_total_delta_sgd": -1.5, "over_budget_sgd": None})
    assert describe(within, plan, "en") == (
        "How about Kimchi Chahan (Fried Rice) instead of Teriyaki Fried Rice? That takes S$1.50 off the groceries. "
        "Nothing changes until you confirm."
    )


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


def test_the_walkthrough_week_has_no_wrapper_or_dough_only_meals(walked):
    from app.repositories.recipe import RecipeRepository

    with walked["factory"]() as session:
        recipes = RecipeRepository(session).list_by_ids([dish.recipe.id for dish in walked["plan"].days])
    bad = [recipe.title for recipe in recipes if incomplete(recipe) == "wrapper or dough with no filling"]
    assert bad == []


def test_the_walkthrough_budget_choices_plan_at_the_offered_amount(walked):
    """A budget button is checked against the same catalog and planning path as clicking it."""
    with walked["factory"]() as session:
        service = agent(session)
        service.starting_constraints = WALKTHROUGH.model_copy(update={"max_cooking_time_minutes": 60})
        refused = service.create("一共10新币给4个人做一周")
        options = refused.pending_interaction.options
        assert [option.label for option in options] == ["Use S$87 for the week"]
        # Two people's week (S$103) costs more than four's: said without its amount (2026-10-09 rehearsal).
        assert "S$103" not in refused.messages[-1].content
        assert "减少人数也不能降低这个预算" in refused.messages[-1].content
        for chosen in options:
            ready = service.reply(refused.id, chosen.value)
            assert ready.can_confirm, (chosen.label, ready.messages[-1].content)
            assert ready.constraints.household_size == 4
            confirmed = service.confirm(ready.id)
            assert confirmed.plan.grocery_estimate.purchase_total_sgd <= ready.constraints.weekly_budget_sgd


REFUSED_FOR_FOUR = (
    "这个预算排不出来。4 个人一周 S$10，每人每餐大约只有 S$0.36（一周 7 餐）。我能找到的最便宜的一周要 S$86.15。"
    " 减少人数也不能降低这个预算。"
)


def test_the_walkthrough_refusal_searches_each_household_size_once_under_a_budget(walked, monkeypatch):
    """Step 6 of the demo (一共10新币给4个人做一周) took 8.4-10.3 s, 6 s allowed: after the 2-person check at its
    cheapest week failed, the reply searched again to verify the week that check had already found. The search reuse
    and choice semantics stay the same after the dough-only candidates leave the planning pool."""
    planned = []
    plan = ProductPlanningEngine.plan

    def counted(self, constraints, *args, **kwargs):
        planned.append((constraints.household_size, constraints.weekly_budget_sgd, bool(kwargs.get("cheapest"))))
        return plan(self, constraints, *args, **kwargs)

    monkeypatch.setattr(ProductPlanningEngine, "plan", counted)
    with walked["factory"]() as session:
        service = agent(session)
        service.starting_constraints = WALKTHROUGH.model_copy(update={"max_cooking_time_minutes": 60})
        refused = service.create("一共10新币给4个人做一周")
    assert refused.messages[-1].content == REFUSED_FOR_FOUR
    assert [option.label for option in refused.pending_interaction.options] == ["Use S$87 for the week"]
    # Each size's cheapest week, then that amount through the budgeted path; no third search.
    assert planned == [(4, None, True), (4, 53, False), (2, None, True), (2, 41, False)]


def test_the_walkthrough_budgeted_checks_cheapest_weeks_plan_at_their_own_cost(walked):
    """What lets the reply above skip that search: a week of the budgeted check's cost-led search that only its
    budget turned down plans under a budget of its cost (planning/product_path.py `cheapest_weeks`)."""
    with walked["factory"]() as session:
        service = agent(session)
        request = service._plan_request(
            WALKTHROUGH.model_copy(update={"max_cooking_time_minutes": 60, "household_size": 2})
        )
        error = service.meal_plan_service.check(request.model_copy(update={"weekly_budget_sgd": 41}))
        backed = sorted(
            attempt["purchase_total_sgd"]
            for attempt in error.trace["validation_attempts"]
            if attempt.get("cheapest_search") and limits._failed(attempt) == {"purchase_budget"}
        )
        assert backed and math.ceil(backed[0]) == 103
        for cost in {backed[0], backed[-1]}:
            budget = math.ceil(cost)
            assert service.meal_plan_service.check(request.model_copy(update={"weekly_budget_sgd": budget})) is None


def test_tapping_an_offered_budget_plans_the_week_its_refusal_checked_without_searching_again(walked, monkeypatch):
    """Tapping an offered budget searched its week again (about 1-1.5 s) before the reply. Where the offer is the
    budget the refusal checked, the week kept by that check answers the tap's check and Plan saves it: the same week
    a new search finds. Since the dough-only recipes left the pool the offer (S$87) is the cost of a week the check at
    S$53 turned down for its budget alone, so the tap runs that one search."""
    planned = []
    plan = ProductPlanningEngine.plan

    def counted(self, constraints, *args, **kwargs):
        planned.append((constraints.household_size, constraints.weekly_budget_sgd))
        return plan(self, constraints, *args, **kwargs)

    with kept_for(300), walked["factory"]() as session:  # weeks are kept as production keeps them
        service = agent(session)
        service.starting_constraints = WALKTHROUGH.model_copy(update={"max_cooking_time_minutes": 60})
        refused = service.create("一共10新币给4个人做一周")
        monkeypatch.setattr(ProductPlanningEngine, "plan", counted)
        ready = service.reply(refused.id, refused.pending_interaction.options[0].value)
        assert ready.can_confirm and ready.constraints.weekly_budget_sgd == 87
        confirmed = service.confirm(ready.id)
        # The offered S$87 is the cost of a week the S$53 check turned down for its budget alone, so no kept week
        # answers the tap: one search, where the offered amount used to be the kept week's own budget (S$53).
        assert planned == [(4, 87.0)]
        monkeypatch.setattr(ProductPlanningEngine, "plan", plan)
        request = service._plan_request(ready.constraints)
        _, fresh = service.meal_plan_service._search(request, service.meal_plan_service._candidates(request))
        saved = sorted(day.recipe.slug for day in confirmed.plan.days)
        assert saved == sorted(item.recipe.slug for item in fresh.selected)
        assert confirmed.plan.grocery_estimate.purchase_total_sgd == fresh.grocery.purchase_total_sgd <= 87


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


# Review round 1: no answer waits for the recipe pool to load ----------------------------------------------------


@pytest.fixture
def loads(monkeypatch):
    """The thread of every load of the planner's recipe pool, in order."""
    threads: list[str] = []
    load = RecipeRepository._load_for_planning

    def counted(self, session, courses):
        threads.append(threading.current_thread().name)
        return load(self, session, courses)

    monkeypatch.setattr(RecipeRepository, "_load_for_planning", counted)
    return threads


@contextmanager
def pooled():
    """A session over a small catalog of every course a dinner role takes, its pool kept as production keeps it."""
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                _dish("salmon-bake", "main", "salmon_fillet", 400, calories=500),
                _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
                _dish("zucchini-salad", "salad", "zucchini", 300, calories=60),
                _dish("tomato-soup", "soup", "tomato", 500, calories=150),
            ]
        )
        session.commit()
    with kept_for(300), factory() as session:
        yield session
    engine.dispose()


def joined(name: str) -> None:
    for thread in threading.enumerate():
        if thread.name == name:
            thread.join()


def test_every_dish_role_plans_from_one_load_of_the_pool(loads):
    """A week loaded the courses of its roles, and then a swap loaded its role's courses again (seconds each)."""
    with pooled() as session:
        recipes = RecipeRepository(session)
        week = recipes.list_for_planning(courses=["main", "salad", "side", "soup"])
        assert [r.slug for r in week] == ["salmon-bake", "broccoli-stirfry", "zucchini-salad", "tomato-soup"]
        assert [r.slug for r in recipes.list_for_planning(courses=["side", "salad"])] == [
            "broccoli-stirfry",
            "zucchini-salad",
        ]
        assert [r.slug for r in recipes.list_for_planning()] == ["salmon-bake", "tomato-soup"]
        assert loads == ["MainThread"]


@contextmanager
def started(session):
    """The API started over `session`'s database, keeping its planning pool until it stops."""
    import app.main as main

    with pytest.MonkeyPatch.context() as patch:  # undone before kept_for's stub of the pool thread is
        patch.setattr(main, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
        patch.setattr(main, "warm_planning_pool", warm_planning_pool)
        with TestClient(main.app):
            yield
    joined("warm-planning-pool")  # stopped with the API


def waited(condition, seconds: float = 10) -> None:
    """Until a background thread did what `condition` says."""
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "the background thread did not get there"
        time.sleep(0.01)


@pytest.fixture
def clock(monkeypatch):
    """The planning pool's clock, moved by hand."""
    now = SimpleNamespace(seconds=1_000.0)
    monkeypatch.setattr("app.repositories.recipe.time", SimpleNamespace(monotonic=lambda: now.seconds))
    monkeypatch.setattr("app.repositories.recipe.POOL_CHECK_SECONDS", 0.01, raising=False)
    return now


def test_a_pool_past_its_age_is_loaded_again_rather_than_planned_from(loads, clock):
    """With nothing keeping it young, the first request past PLANNING_POOL_CACHE_SECONDS planned from it while it
    was reloaded in the background (review round 1): a catalog imported meanwhile was not seen."""
    with pooled() as session:
        recipes = RecipeRepository(session)
        recipes.list_for_planning()
        session.add(_dish("pumpkin-soup", "soup", "pumpkin", 400, calories=120))
        session.commit()
        clock.seconds += 301
        assert [r.slug for r in recipes.list_for_planning()] == ["salmon-bake", "tomato-soup", "pumpkin-soup"]
        assert loads == ["MainThread", "MainThread"]


def test_the_api_loads_the_pool_again_before_it_ages_so_no_request_waits_for_it(loads, clock):
    """The pool aged 300 s after it was loaded, and the first answer after that loaded it (about 11 s in OpenAI
    mode, ADR-0046's target is 10 s). A catalog imported meanwhile reaches the request all the same."""
    with pooled() as session:
        with started(session):
            waited(lambda: len(loads) == 1 and _planning_pool and not reloading_binds)  # loaded at 1,000 s
            clock.seconds += 100
            session.add(_dish("pumpkin-soup", "soup", "pumpkin", 400, calories=120))  # the worker's import
            session.commit()
            for loaded, age in ((2, 160), (3, 320)):
                clock.seconds = 1_000 + age
                waited(lambda loaded=loaded: len(loads) == loaded and not reloading_binds)
            recipes = RecipeRepository(session).list_for_planning()  # 320 s after the startup load
        assert [r.slug for r in recipes] == ["salmon-bake", "tomato-soup", "pumpkin-soup"]
        assert loads == ["warm-planning-pool"] * 3


def test_the_api_answers_only_once_its_planning_pool_is_loaded(loads):
    """A message sent as soon as the API answered after a restart waited about 1.2 s for the background thread's
    first load of the pool, taking the demo's cold budget refusal past 6 s (WP1 1b). The background thread is
    left out here (kept_for), so only the startup itself can have loaded it."""
    import app.main as main

    with pooled() as session, pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
        patch.setattr(main, "load_planning_pool", load_planning_pool)
        with TestClient(main.app):
            assert len(loads) == 1
            assert id(session.get_bind()) in _planning_pool


def test_a_background_load_does_not_hold_up_a_request(monkeypatch, loads, clock):
    """Requests plan from the pool in hand while the background thread loads its successor."""
    from app.repositories.recipe import keep_planning_pool_warm

    load = RecipeRepository._load_for_planning
    holding, finish, stop = threading.Event(), threading.Event(), threading.Event()

    def held(self, session, courses):
        if threading.current_thread().name == "warm":
            holding.set()
            finish.wait(10)
        return load(self, session, courses)

    with pooled() as session:
        recipes = RecipeRepository(session)
        first = recipes.list_for_planning()
        monkeypatch.setattr(RecipeRepository, "_load_for_planning", held)
        clock.seconds += 151
        warm = threading.Thread(target=keep_planning_pool_warm, args=(session.get_bind(), stop), name="warm")
        warm.start()
        try:
            waited(holding.is_set)
            started = time.monotonic()
            assert recipes.list_for_planning() == first
            assert time.monotonic() - started < 2
        finally:
            finish.set()
            stop.set()
            warm.join()
        assert recipes.list_for_planning() != first  # the successor, loaded meanwhile
        assert loads == ["MainThread", "warm"]


def test_the_warmer_rechecks_age_after_a_request_loaded_the_pool(loads, clock):
    """A warmer that observed an old pool before waiting for the lock does not replace a request's fresh load."""
    from app.repositories.recipe import _reload_pool

    with pooled() as session:
        recipes = RecipeRepository(session)
        recipes.list_for_planning()
        clock.seconds += 301
        recipes.list_for_planning()

        assert _reload_pool(session.get_bind(), maximum_age=150) is None
        assert loads == ["MainThread", "MainThread"]


def test_the_warmer_backs_off_and_only_the_first_failure_has_a_traceback(monkeypatch, caplog):
    from app.repositories.recipe import _reloading as active_reloads
    from app.repositories.recipe import keep_planning_pool_warm

    outcomes = [
        RuntimeError("database unavailable"),
        RuntimeError("still unavailable"),
        None,
        RuntimeError("down again"),
    ]

    class RecordingStop:
        def __init__(self):
            self.waits: list[float] = []

        def wait(self, seconds):
            self.waits.append(seconds)
            return len(self.waits) == 4

    stop = RecordingStop()

    def reload_outcome(bind, **_kwargs):
        active_reloads.discard(id(bind))
        return outcomes.pop(0)

    monkeypatch.setattr("app.repositories.recipe._reload_pool", reload_outcome)
    monkeypatch.setattr("app.repositories.recipe._catalog_change_marker", lambda _bind: (False, None))
    monkeypatch.setattr("app.repositories.recipe.POOL_CHECK_SECONDS", 0.01)
    monkeypatch.setattr("app.repositories.recipe.POOL_FAILURE_BACKOFF_MAX_SECONDS", 0.04)

    with caplog.at_level(logging.WARNING, logger="app.repositories.recipe"):
        keep_planning_pool_warm(object(), stop)

    records = [record for record in caplog.records if "planning pool" in record.getMessage()]
    assert outcomes == []
    assert stop.waits == [0.01, 0.02, 0.01, 0.01]
    assert [record.exc_info is not None for record in records] == [True, False, True]


def test_reference_import_refreshes_the_pool_within_one_poll(loads):
    from app.repositories.recipe import keep_planning_pool_warm

    with pooled() as session:
        catalog = Catalog.model_validate(
            {
                "ingredients": [
                    {"normalized_name": "broccoli", "display_name": "Broccoli", "allergens": []},
                    {"normalized_name": "tomato", "display_name": "Tomato", "allergens": []},
                ],
                "recipes": [
                    {
                        "slug": "broccoli-tomato-soup",
                        "title": "Broccoli Tomato Soup",
                        "description": "A newly imported soup.",
                        "cuisine": "international",
                        "meal_type": "soup",
                        "servings": 2,
                        "prep_time_minutes": 5,
                        "cook_time_minutes": 20,
                        "dietary_tags": ["vegetarian"],
                        "nutrition": {
                            "calories_kcal": 120,
                            "protein_g": 3,
                            "carbohydrate_g": 24,
                            "fat_g": 2,
                            "sodium_mg": 150,
                            "sugar_g": 8,
                        },
                        "ingredients": [
                            {"ingredient": "broccoli", "quantity": 400, "unit": "g"},
                            {"ingredient": "tomato", "quantity": 200, "unit": "g"},
                        ],
                        "steps": ["Chop the vegetables.", "Simmer until tender."],
                    }
                ],
            }
        )

        class ImportOnFirstPoll:
            imported = False

            def wait(self, _seconds):
                if not self.imported:
                    with Session(bind=session.get_bind()) as importer:
                        import_catalog(importer, catalog)
                    self.imported = True
                    return False
                return True

        keep_planning_pool_warm(session.get_bind(), ImportOnFirstPoll())

        planned = RecipeRepository(session).list_for_planning()
        assert any(recipe.slug == "broccoli-tomato-soup" for recipe in planned)
        assert loads == ["MainThread", "MainThread"]


def test_the_warmer_does_not_refresh_without_a_new_import(loads):
    from app.repositories.recipe import keep_planning_pool_warm

    class StopAfterTwoPolls:
        polls = 0

        def wait(self, _seconds):
            self.polls += 1
            return self.polls == 2

    with pooled() as session:
        keep_planning_pool_warm(session.get_bind(), StopAfterTwoPolls())
        assert loads == ["MainThread"]


def test_a_pool_load_that_an_edit_overtook_is_not_kept(monkeypatch):
    """An operations edit clears the pool so that the next plan sees it: a load under way may predate the edit."""
    load = RecipeRepository._load_for_planning

    def edited_meanwhile(self, session, courses):
        recipes = load(self, session, courses)
        clear_planning_pool()
        return recipes

    with pooled() as session:
        monkeypatch.setattr(RecipeRepository, "_load_for_planning", edited_meanwhile)
        assert [r.slug for r in RecipeRepository(session).list_for_planning()] == ["salmon-bake", "tomato-soup"]
        assert not _planning_pool


def test_an_operations_edit_has_the_pool_loaded_again_at_once(loads):
    """An edit cleared the pool, and the next plan loaded it, edit included, while the household waited."""
    from app.services.ops_data import _planning_changed

    with pooled() as session:
        recipes = RecipeRepository(session)
        recipes.list_for_planning()
        session.add(_dish("pumpkin-soup", "soup", "pumpkin", 400, calories=120))
        session.commit()
        _planning_changed()
        joined("reload-planning-pool")
        assert loads == ["MainThread", "reload-planning-pool"]
        assert [r.slug for r in recipes.list_for_planning()] == ["salmon-bake", "tomato-soup", "pumpkin-soup"]
        assert loads == ["MainThread", "reload-planning-pool"]


def test_the_api_loads_the_recipe_pool_at_startup(loads):
    """The first answer after startup loaded the pool itself (11.84 s in OpenAI mode in the walkthrough)."""
    with pooled() as session:
        with started(session):
            waited(lambda: loads == ["warm-planning-pool"])
            RecipeRepository(session).list_for_planning(courses=["main", "side", "salad", "soup"])
        assert loads == ["warm-planning-pool"]
