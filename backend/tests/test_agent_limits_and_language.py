"""What the 2026-10-02 walkthrough found in the conversation.

An impossible week is refused before the assistant says it has everything, with the number that shows
it; a week the planner then cannot find is explained in the chat by the limit its search ran into. Every
templated reply follows the household's language, and an unclear message gets choices, not a dead end.
Both parsers: the rule parser, and the live one with its model stubbed (no call goes out).
"""

import itertools
import math
import random
import re
import time
from types import SimpleNamespace

import pytest

from app.agent import limits
from app.agent.limits import _budget_short, planning_failure
from app.agent.parser import (
    FallbackConstraintParser,
    OpenAIConstraintParser,
    RuleBasedConstraintParser,
)
from app.agent.replies import language, planner_message
from app.planning import meal_beam
from app.planning.meal_composition import portion_shares
from app.planning.product_path import CHEAPEST_MEAL_OPTIONS, ProductPlanningEngine, ProductPlanningError
from app.planning.week_floor import WeekFloor, _cheapest_days, _cheapest_meal, week_floor
from app.products.provider import ProductProviderError
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from app.schemas.meal_plan import MEAL_PRESETS, WeeklyMealPlanRequest
from app.schemas.planning_v2 import PlanningCompositionPolicy
from app.services.agent import AgentSessionService
from app.services.meal_plan import WeeklyMealPlanService
from tests.test_planning_capability import _dish, composed_client, dish_client  # noqa: F401


def parse(message: str) -> AgentConstraintExtraction:
    return RuleBasedConstraintParser().parse(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )


@pytest.mark.parametrize(
    ("message", "size", "weekly", "per_meal"),
    [
        ("Plan a week for 4 for S$10 total", 4, 10, None),
        ("4 people, S$10 total", 4, 10, None),
        ("A total of S$10 for 4 people", 4, 10, None),
        ("For 4 people, S$10 for the week", 4, 10, None),
        ("Dinners for 4, S$10 in total", 4, 10, None),
        ("$80 a week, $12 a meal", None, 80, 12),
        ("我们4个人，一周一共10新币", 4, 10, None),
        ("4个人，总共10块", 4, 10, None),
        ("四个人，总预算10新币", 4, 10, None),
        ("4个人，每餐不超过15新币", 4, None, 15),
        # The walkthrough sentence without "total", and sums that are not who eats.
        ("Plan a week for 4 for S$10", 4, 10, None),
        ("4 people for 10 dollars total", 4, 10, None),
        ("4 people, S$100 total for 7 dinners", 4, 100, None),
        ("我们四个人，总共一百块", 4, 100, None),
        # Who eats, said between the sum and what it is for.
        ("S$40 for 4 people for the week", 4, 40, None),
        ("S$40 for four people for the week", 4, 40, None),
        ("S$40 for the week for 4 people", 4, 40, None),
        ("S$12 for 4 people per meal", 4, None, 12),
        ("10新币给4个人一周", 4, 10, None),
        ("40块钱4个人一周", 4, 40, None),
        ("每餐给4个人15块", 4, None, 15),
        ("S$40 for the 4 of us for the week", 4, 40, None),
        ("S$40 for the four of us for the week", 4, 40, None),
        ("One week of dinners for four people, S$40", 4, 40, None),
        # An amount for each person is one for the household.
        ("S$10 per person for 4 people for the week", 4, 40, None),
        ("Dinners for 4, S$3 per person per meal", 4, None, 12),
        ("Dinners for 2, S$12 per person per meal", 2, None, 24),
        ("4 people, 2 dollars per person per meal", 4, None, 8),
        ("4 people, S$20 per person for the week", 4, 80, None),
        ("4个人，每人每餐3块", 4, None, 12),
        # ... and is left out while nobody has said how many eat.
        ("S$3 per person per meal", None, None, None),
    ],
)
def test_a_budget_for_the_whole_week_is_read_however_it_is_said(message, size, weekly, per_meal):
    extraction = parse(message)
    assert (extraction.household_size, extraction.weekly_budget_sgd, extraction.budget_per_meal_sgd) == (
        size,
        weekly,
        per_meal,
    )


def test_a_reply_is_in_the_language_of_the_message_or_else_of_the_conversation():
    chinese = [SimpleNamespace(role="user", content="我们两个人"), SimpleNamespace(role="assistant", content="Got it")]
    assert language("我想吃点好的") == "zh"
    assert language("something nice") == "en"
    # A number, a sum or "ok" has no words to tell by: the conversation's language holds.
    assert language("4", chinese) == language("S$40", chinese) == language("ok", chinese) == "zh"
    assert language("ok") == "en"


def live_parser(extraction: AgentConstraintExtraction) -> FallbackConstraintParser:
    """The OpenAI parser with its model replaced: it 'hears' `extraction`, whatever the message."""
    live = OpenAIConstraintParser.__new__(OpenAIConstraintParser)
    live.vocabulary, live.model = None, "stub"
    live.structured_model = SimpleNamespace(invoke=lambda prompt: extraction.model_copy())
    return FallbackConstraintParser(live)


# What the stubbed model hears; anything else is read as the rule parser reads it.
HEARD = {
    "Plan a week for 4 for S$10 total": AgentConstraintExtraction(household_size=4, weekly_budget_sgd=10),
    "我们4个人，一周一共10新币": AgentConstraintExtraction(household_size=4, weekly_budget_sgd=10),
}


def stub_openai(monkeypatch):
    import app.api.routes.agent as routes

    def hear(prompt: str) -> AgentConstraintExtraction:
        message = prompt.rsplit("Latest user message: ", 1)[1].strip()
        if message in HEARD:
            return HEARD[message]
        read = RuleBasedConstraintParser().parse(
            message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
        )
        return read.model_copy(update={"assistant_summary": None})

    def parser(settings, database=None, *, provider=None):
        parsed = live_parser(AgentConstraintExtraction())
        parsed.primary.structured_model = SimpleNamespace(invoke=hear)
        return parsed

    monkeypatch.setattr(routes, "create_constraint_parser", parser)


@pytest.fixture(params=["fixture", "openai"])
def client(request, composed_client, monkeypatch):  # noqa: F811
    """The synthetic week (two mains, three vegetables, a soup), in each parser mode."""
    if request.param == "openai":
        stub_openai(monkeypatch)
    composed_client.mode = request.param
    return composed_client


# Eight mains, each a little of an ingredient sold in a whole package: what a week uses costs a few dollars,
# what it buys costs several times that. The floor under the week's cost cannot tell S$10 from enough.
PACKAGED = [
    ("chickpea-stew", "chickpea"),
    ("tofu-bowl", "firm_tofu"),
    ("bean-chili", "black_bean"),
    ("pasta-toss", "wholewheat_pasta"),
    ("mushroom-rice", "mushroom"),
    ("sweet-potato-bake", "sweet_potato"),
    ("soba-salad", "soba_noodle"),
    ("lentil-soup-main", "red_lentil"),
]


@pytest.fixture(params=["fixture", "openai"])
def packaged(request, monkeypatch):
    if request.param == "openai":
        stub_openai(monkeypatch)
    dishes = [_dish(slug, "main", ingredient, 40, calories=400) for slug, ingredient in PACKAGED]
    with dish_client(monkeypatch, dishes) as client:
        client.mode = request.param
        yield client


def tap(client, session: dict, label: str) -> dict:
    interaction = session["pending_interaction"]
    option = next(item for item in interaction["options"] if item["label"] == label)
    response = client.post(
        f"/api/agent/sessions/{session['id']}/interactions",
        json={
            "question_id": interaction["question_id"],
            "option_ids": [option["id"]],
            "context_version": interaction["context_version"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def labels(session: dict) -> list[str]:
    return [option["label"] for option in (session["pending_interaction"] or {}).get("options", [])]


def cheapest_quoted(reply: str) -> float:
    return float(re.search(r"The cheapest week I could plan costs about S\$(\d+\.\d\d)", reply).group(1))


def plans(client, session: dict) -> dict:
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["plan"]


def test_a_budget_whole_packages_overrun_is_refused_up_front_and_every_choice_plans(packaged, floors):
    """The walkthrough's S$10 for 4: the floor allows it, the packages do not. Refused before "ready",
    with the cheapest week the planner found, and each choice offered plans."""
    first = "Plan a week for 4, S$10 total, no dish twice"
    session = packaged.post("/api/agent/sessions", json={"message": first}).json()
    assert session["parser_provider"] == packaged.mode

    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"]
    assert "everything I need" not in reply
    assert "S$10 for 4 people is S$0.36 a person a meal over 7 meals" in reply
    assert "the cheapest my search found, not a proof that none is cheaper" in reply
    cost = cheapest_quoted(reply)
    assert cost > 10
    # What a week uses is far less than what it buys: the floor alone would have said "ready".
    assert floors[0] < 10 < cost
    use, fewer = labels(session)
    assert use == f"Use S${math.ceil(cost)} for the week"
    assert fewer.startswith("2 people at S$") and fewer.endswith(" a week")

    for label in (use, fewer):
        again = packaged.post("/api/agent/sessions", json={"message": first}).json()
        ready = tap(packaged, again, label)
        assert ready["status"] == "ready" and ready["can_confirm"], ready["messages"][-1]["content"]
        plan = plans(packaged, ready)
        assert plan["grocery_estimate"]["purchase_total_sgd"] <= ready["constraints"]["weekly_budget_sgd"]


@pytest.fixture
def floors(monkeypatch):
    """Records the floor each check computed, so a test can show what the floor alone would have said."""
    seen = []
    original = WeeklyMealPlanService.week_floor

    def week_floor(self, constraints):
        floor = original(self, constraints)
        seen.append(floor.total_sgd)
        return floor

    monkeypatch.setattr(WeeklyMealPlanService, "week_floor", week_floor)
    return seen


def test_an_impossible_budget_is_refused_up_front_in_both_parser_modes(client):
    session = client.post("/api/agent/sessions", json={"message": "Plan a week for 4 for S$10 total"}).json()
    assert session["parser_provider"] == client.mode

    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"]
    assert "everything I need" not in reply
    assert "S$10 for 4 people is S$0.36 a person a meal over 7 meals" in reply
    cost = cheapest_quoted(reply)
    ready = tap(client, session, f"Use S${math.ceil(cost)} for the week")
    assert ready["status"] == "ready" and ready["can_confirm"]
    assert plans(client, ready)["grocery_estimate"]["purchase_total_sgd"] <= math.ceil(cost)


def no_check_up_front(monkeypatch):
    monkeypatch.setattr(AgentSessionService, "_refusal", lambda self, constraints, lang: None)


def test_a_week_that_fails_at_plan_for_budget_offers_only_a_budget_a_real_week_backs(client, monkeypatch):
    """No "Try S$X" ladder: the budget offered after a failed Plan is the cost of the cheapest week the
    search found, and with it the week plans."""
    no_check_up_front(monkeypatch)  # the week fails at Plan
    session = client.post("/api/agent/sessions", json={"message": "Plan a week for 4 for S$10 total"}).json()
    assert session["can_confirm"]

    failed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert failed.status_code == 422
    why = failed.json()["detail"]
    cost = cheapest_quoted(why)
    explained = client.get(f"/api/agent/sessions/{session['id']}").json()
    assert explained["messages"][-1]["content"] == why
    assert not explained["can_confirm"] and explained["status"] == "collecting"  # the Plan card gives way
    use = f"Use S${math.ceil(cost)} for the week"
    assert labels(explained)[0] == use
    ready = tap(client, explained, use)
    assert ready["can_confirm"]
    assert plans(client, ready)["grocery_estimate"]["purchase_total_sgd"] <= math.ceil(cost)


def test_a_chinese_household_is_refused_in_chinese_with_choices_in_chinese(client):
    session = client.post("/api/agent/sessions", json={"message": "我们4个人，一周一共10新币"}).json()
    assert session["parser_provider"] == client.mode

    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"]
    assert "4 个人一周 S$10，相当于每人每餐 S$0.36（共 7 餐）" in reply and "最便宜的一周大约要" in reply
    assert not re.search(r"[A-Za-z]{3,}", reply)
    options = session["pending_interaction"]["options"]
    assert options[0]["label"].startswith("一周用 S$")
    assert options[0]["value"].startswith("每周预算 ")


@pytest.mark.parametrize(
    ("answer", "lang"),
    [("S$50", "en"), ("ok, 50 dollars then", "en"), ("50", "en"), ("那就50新币吧", "zh")],
)
def test_a_bare_amount_answers_the_budget_the_refusal_asked_about(client, answer, lang):
    first = "Plan a week for 4 for S$10 total" if lang == "en" else "我们4个人，一周一共10新币"
    session = client.post("/api/agent/sessions", json={"message": first}).json()
    assert session["missing_fields"] == ["weekly_budget_sgd"]

    answered = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": answer}).json()
    assert answered["constraints"]["weekly_budget_sgd"] == 50
    assert answered["status"] == "ready" and answered["can_confirm"]
    assert language(answered["messages"][-1]["content"]) == lang


@pytest.mark.parametrize(
    ("message", "size", "weekly", "per_meal"),
    [
        ("4个人，总共10块", 4, 10, None),
        ("4 people, SGD 10 in total", 4, 10, None),
        ("4 people, $10 per week", 4, 10, None),
        ("4 people, 10 dollars for the week", 4, 10, None),
        ("我们四个人，总共一百块", 4, 100, None),
        ("4个人，每顿饭不超过15块", 4, None, 15),
    ],
)
def test_a_budget_however_it_is_said_reaches_the_parser(client, message, size, weekly, per_meal):
    """The scope gate runs before either parser: a sum of money is a planning message."""
    session = client.post("/api/agent/sessions", json={"message": message}).json()

    assert session["last_scope_decision"]["scope_class"] == "domain_action"
    constraints = session["constraints"]
    assert (constraints["household_size"], constraints["weekly_budget_sgd"], constraints["budget_per_meal_sgd"]) == (
        size,
        weekly,
        per_meal,
    )


@pytest.mark.parametrize(
    ("message", "weekly"),
    [
        ("S$40 for 4 people for the week", 40),
        ("S$40 for the week for 4 people", 40),
        ("10新币给4个人一周", 10),
        ("一周10新币，给4个人", 10),
        ("S$10 per person for 4 people for the week", 40),
        ("S$40 for the 4 of us for the week", 40),
        # Who eats is not the sum: "budget for the 4", "for 7" dinners.
        ("Weekly budget for the 4 of us is S$40", 40),
        ("Weekly budget for 4 is S$40", 40),
        ("S$50 for a family of 4 for the week", 50),
        ("S$50 for my family of four this week", 50),
        ("S$40 for 7 dinners for 4 people", 40),
    ],
)
def test_a_weekly_sum_said_before_who_eats_is_the_weeks(client, message, weekly):
    session = client.post("/api/agent/sessions", json={"message": message}).json()

    assert (session["constraints"]["household_size"], session["constraints"]["weekly_budget_sgd"]) == (4, weekly)


def profile_of_four(client, **profile) -> None:
    member = {"servings_per_meal": 1, "allergens": [], "excluded_ingredients": [], "dietary_preferences": []}
    created = client.post(
        "/api/household-profiles",
        json={
            "name": "Four",
            "members": [{"name": f"Member {n}", **member} for n in range(4)],
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            **profile,
        },
    )
    assert created.status_code == 201, created.text


@pytest.mark.parametrize(
    ("message", "weekly"),
    [
        ("Plan a week of dinners, S$60 total, one of us is vegetarian", 60),
        ("Plan this week's dinners, one of us doesn't eat pork", None),
        ("One of us works late, so plan quick dinners this week", None),
        ("Plan a week for my family, two of us don't eat beef", None),
        ("Plan dinners, the one of us who cooks is busy", None),
        ("S$40 for seven dinners", 40),
    ],
)
def test_part_of_the_household_leaves_the_profiles_size(client, message, weekly):
    """ "One of us" or "two of us" is some of the household, not how many eat: the profile's four hold."""
    profile_of_four(client)

    session = client.post("/api/agent/sessions", json={"message": message}).json()
    assert (session["constraints"]["household_size"], session["constraints"]["weekly_budget_sgd"]) == (4, weekly)


def test_a_failed_search_names_the_limit_it_ran_into_never_a_proof():
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=50)
    over = {"purchase_total_sgd": 61.2, "checks": [{"code": "purchase_budget", "status": "failed", "hard": True}]}
    cheapest = {**over, "purchase_total_sgd": 58.4, "cheapest_search": True}

    def failure(trace, status="candidate_rejected", message="I couldn't find a week."):
        return ProductPlanningError(status, message, trace)

    told = planning_failure(failure({"validation_attempts": [over, cheapest]}), constraints, "en")
    assert told.text == (
        "S$50 for 4 people is S$1.79 a person a meal over 7 meals. The cheapest week I could plan costs about "
        "S$58.40: the cheapest my search found, not a proof that none is cheaper."
    )
    # Only the cheapest-week search's own week backs an amount, never a ranked week or a guess.
    assert told.options == (("Use S$59 for the week", "Make the weekly budget S$59"),)
    # With no such week, the budget the search ran into is still named, with no amount to offer: every week it
    # ranked failed the budget alone, or the search emptied on the budget before it ranked one.
    named = (
        "I couldn't plan this week: the search found no week that meets the S$50 weekly budget. "
        "That is the limit it kept running into."
    )
    for trace in ({"validation_attempts": [over]}, {"search": {"emptied_by": "budget"}}):
        unbacked = planning_failure(failure(trace), constraints, "en")
        assert (unbacked.field, unbacked.text, unbacked.options) == ("weekly_budget_sgd", named, ())
    zh = planning_failure(failure({"search": {"emptied_by": "budget"}}), constraints, "zh")
    assert zh.text == "这周没排出来：搜索没有找到符合每周 S$50 预算的一周。卡住它的就是这个限制。"
    # A ranked week that fails something else too: the budget is not all that binds.
    repeats = {"code": "repetition_rule", "status": "failed", "hard": True}
    both = {**over, "checks": [*over["checks"], repeats]}
    together = planning_failure(failure({"validation_attempts": [both, over]}), constraints, "en")
    assert together.field == "plan" and together.text.startswith("I couldn't plan this week: the search found no week")
    assert "every limit together" in together.text
    emptied = planning_failure(failure({"search": {"emptied_by": "repeats"}}), constraints, "zh")
    assert emptied.text == "这周没排出来：搜索没有找到符合菜不重样的要求的一周。卡住它的就是这个限制。"
    slow = planning_failure(failure({"search": {"exhausted": True}}), constraints, "en")
    assert slow.retry  # nothing to change: the Plan card stays

    # A guess at a per-meal budget or a cooking time is not offered: no week backs it.
    limited = AgentConstraintState(household_size=4, budget_per_meal_sgd=5, max_cooking_time_minutes=20)
    for code in ("per_meal_budget", "time_limit"):
        failed = {"purchase_total_sgd": 40.0, "checks": [{"code": code, "status": "failed", "hard": True}]}
        told = planning_failure(failure({"validation_attempts": [failed]}), limited, "en")
        assert told.text.startswith("I couldn't plan this week: the search found no week that meets the ")
        assert told.options == ()


def test_a_per_meal_budget_is_offered_only_when_a_week_plans_with_it(monkeypatch):
    """S$1 a meal fits no dish; the cheapest needs S$2, but with no dish twice two dishes are not a week."""
    dishes = [_dish(slug, "main", ingredient, 400, calories=400) for slug, ingredient in PACKAGED]
    with dish_client(monkeypatch, dishes) as client:
        session = client.post(
            "/api/agent/sessions", json={"message": "Dinners for 4, S$1 a meal, no dish twice"}
        ).json()
        assert session["status"] == "collecting" and "S$1 a meal" in session["messages"][-1]["content"]
        assert not any("per-meal" in label for label in labels(session))

        # Without the rule, S$2 a meal plans, and is offered.
        session = client.post("/api/agent/sessions", json={"message": "Dinners for 4, S$1 a meal"}).json()
        raise_to = next(label for label in labels(session) if "per-meal" in label)
        ready = tap(client, session, raise_to)
        assert ready["can_confirm"]
        plans(client, ready)


def test_a_search_that_ran_out_of_steps_up_front_leaves_the_week_to_plan():
    floor = WeekFloor(days=7, meals=7, total_sgd=9.0, meal_sgd={}, empty_roles=[], roles={})
    slow = ProductPlanningError("candidate_rejected", "Planning took longer.", {"search": {"exhausted": True}})
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=20)

    told = limits.refusal(constraints, lambda **_: floor, "en", check=lambda **_: slow, cheapest=lambda **_: None)
    assert told is None  # nothing to change: Plan may well find the week


def unsearched(**changes):
    raise AssertionError("searched for a week within the reply")


def test_a_budget_under_the_floor_is_refused_with_the_floor_when_the_search_finds_no_week():
    """Three meals a day, no dish twice: the cheapest-week search finds nothing, and the floor still proves
    S$50 is not enough. Planning the week as well would only end in "every limit together"."""
    floor = WeekFloor(days=7, meals=21, total_sgd=61.53, meal_sgd={}, empty_roles=[], roles={})
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=50, max_uses_per_recipe=1)

    told = limits.refusal(constraints, lambda **_: floor, "en", check=unsearched, cheapest=lambda **_: None)
    assert (told.field, told.options) == ("weekly_budget_sgd", ())
    assert told.text == (
        "S$50 for 4 people is S$0.60 a person a meal over 21 meals: what this week's dishes use costs at least "
        "S$61.53, before buying whole packages."
    )


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_a_meal_too_big_to_search_in_a_reply_is_refused_only_under_the_floor(lang):
    """Four dishes or more: the planner's searches take 5 to 26 s, so the reply refuses what the floor proves."""
    dinner = [
        {"role_id": r, "courses": c} for r, c in (("main", ["main"]), ("vegetable", ["side"]), ("soup", ["soup"]))
    ]
    big = {"meals": {"dinner": [*dinner, {"role_id": "vegetable-2", "courses": ["side"]}]}}
    floor = WeekFloor(days=7, meals=7, total_sgd=30.0, meal_sgd={"dinner": 5.0}, empty_roles=[], roles={})
    state = AgentConstraintState(household_size=4, weekly_budget_sgd=20, budget_per_meal_sgd=2, plan_shape=big)

    def refused(**changes):
        return limits.refusal(
            state.model_copy(update=changes), lambda **_: floor, lang, check=unsearched, cheapest=unsearched
        )

    per_meal = refused()  # the per-meal raise is offered only when a week plans with it: unchecked, not offered
    assert per_meal.field == "budget_per_meal_sgd" and per_meal.options == ()
    told = refused(budget_per_meal_sgd=None)
    assert told.field == "weekly_budget_sgd" and told.options == ()  # no amount a week backs to offer
    assert ("S$30.00" in told.text) and (("at least" in told.text) if lang == "en" else ("至少" in told.text))
    assert refused(budget_per_meal_sgd=None, weekly_budget_sgd=40) is None  # Plan answers the rest

    # Three dishes a meal: searched within the reply as before.
    small = AgentConstraintState(household_size=4, weekly_budget_sgd=20, plan_shape={"meals": {"dinner": dinner}})
    with pytest.raises(AssertionError, match="searched"):
        limits.refusal(small, lambda **_: floor, lang, check=unsearched, cheapest=unsearched)


@pytest.mark.parametrize(
    ("message", "told"),
    [
        (
            "Plan a week for 4 for S$10 total, no dish twice",
            "I couldn't plan this week: the search found no week that meets the S$10 weekly budget. "
            "That is the limit it kept running into.",
        ),
        (
            "我们4个人，一周一共10新币，菜不要重复",
            "这周没排出来：搜索没有找到符合每周 S$10 预算的一周。卡住它的就是这个限制。",
        ),
    ],
)
def test_a_meal_too_big_to_search_in_a_reply_is_told_at_plan_the_budget_it_ran_into(packaged, message, told):
    """A main and three dishes "if one fits" (三菜一汤): the reply searches nothing, so S$10 with no dish twice is
    ready over the floor. Plan, which skips the cheapest-week search for such a meal, then names the budget, with
    no amount, since no week backs one."""
    optional = [("vegetable", ["side", "salad"]), ("vegetable-2", ["side", "salad"]), ("soup", ["soup"])]
    dinner = [{"role_id": "main", "courses": ["main"]}]
    dinner += [{"role_id": role, "courses": courses, "required": False} for role, courses in optional]
    member = {"servings_per_meal": 1, "allergens": [], "excluded_ingredients": [], "dietary_preferences": []}
    profile = {
        "members": [{**member, "name": f"Cook {n}"} for n in range(4)],
        "max_cooking_time_minutes": 90,
        "plan_shape": {"meals": {"dinner": dinner}},
    }
    assert packaged.post("/api/household-profiles", json=profile).status_code == 201
    session = packaged.post("/api/agent/sessions", json={"message": message}).json()
    assert session["can_confirm"]  # the trade for the reply's time limit

    failed = packaged.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert failed.status_code == 422 and failed.json()["detail"] == told
    explained = packaged.get(f"/api/agent/sessions/{session['id']}").json()
    assert explained["missing_fields"] == ["weekly_budget_sgd"] and labels(explained) == []


def test_a_request_the_planner_turned_down_before_searching_is_passed_on_as_it_said():
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=80.555)
    cents = ProductPlanningError("needs_clarification", "Enter a budget in whole cents and try again.", {})
    told = planning_failure(cents, constraints, "en")
    assert told.text == "I couldn't plan this week: Enter a budget in whole cents and try again."
    assert not told.retry
    assert planning_failure(cents, constraints, "zh").text == "这周没排出来：预算请精确到分（最多两位小数）再试一次。"

    allergen = "Recipe coverage for a requested allergen is missing; update the allergen data before planning."
    missing = ProductPlanningError("needs_data", allergen, {"status": "needs_data"})
    unchecked = AgentConstraintState(household_size=2, allergens=["lupin"])
    assert not planning_failure(missing, unchecked, "en").retry  # retrying cannot add the data
    gap = ProductPlanningError("needs_data", "Some recipe or price details are missing. Try again in a moment.", {})
    assert planning_failure(gap, constraints, "en").retry


def test_a_budget_in_fractions_of_a_cent_is_answered_with_the_planners_reason(client, monkeypatch):
    no_check_up_front(monkeypatch)
    session = client.post("/api/agent/sessions", json={"message": "Plan a week for 4 for S$80.555 total"}).json()
    failed = client.post(f"/api/agent/sessions/{session['id']}/confirm")

    assert failed.status_code == 422
    assert failed.json()["detail"] == "I couldn't plan this week: Enter a budget in whole cents and try again."


def test_prices_that_cannot_be_read_skip_the_check_instead_of_failing_the_turn(composed_client, monkeypatch):  # noqa: F811
    def unavailable(self, constraints):
        raise ProductProviderError("FairPrice request failed: timed out")

    monkeypatch.setattr(WeeklyMealPlanService, "week_floor", unavailable)
    session = composed_client.post("/api/agent/sessions", json={"message": "Plan a week for 4 for S$10 total"})

    assert session.status_code == 201, session.text
    assert session.json()["status"] == "ready"


def test_no_dish_twice_with_too_few_dishes_is_refused_with_the_count(composed_client):  # noqa: F811
    session = composed_client.post("/api/agent/sessions", json={"message": "Dinners for 4, no repeats"}).json()

    assert session["status"] == "collecting" and not session["can_confirm"]
    assert (
        "No dish twice needs 7 different main dishes for dinner this week, and only 2 fit"
        in (session["messages"][-1]["content"])
    )


def test_the_cheapest_meal_counts_each_dish_at_its_share():
    roles = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side"], "required": False}]
    policy = PlanningCompositionPolicy()
    # A main alone is a whole meal; with a vegetable it is 0.75 of one and the vegetable 0.5.
    assert _cheapest_meal(roles, {"main": 8.0, "vegetable": 1.0}, policy) == pytest.approx(6.5)
    assert _cheapest_meal(roles, {"main": 8.0, "vegetable": 10.0}, policy) == pytest.approx(8.0)
    assert _cheapest_meal(roles, {"main": 8.0}, policy) == pytest.approx(8.0)


def priced(recipe_id: int, cost: float) -> SimpleNamespace:
    """A candidate main whose one ingredient costs `cost` as used."""
    line = SimpleNamespace(
        ingredient_name=f"ingredient-{recipe_id}",
        unit="g",
        required_quantity=1.0,
        product=SimpleNamespace(package_size=1.0, package_unit="g", price_sgd=cost),
    )
    recipe = SimpleNamespace(id=recipe_id, course="main", total_time_minutes=20, nutrition=SimpleNamespace(sodium_mg=1))
    return SimpleNamespace(recipe=recipe, grocery_estimate=SimpleNamespace(items=[line], consumed_total_sgd=cost))


@pytest.mark.parametrize(
    ("cap", "floor"), [(None, 7.0), (7, 7.0), (3, 3 + 6 + 10), (1, 1 + 2 + 10 + 11 + 12 + 13 + 14)]
)
def test_the_floor_serves_each_dish_at_most_the_cap_on_uses(cap, floor):
    """No dish twice: seven different mains, not the cheapest one seven times."""
    mains = [priced(index, cost) for index, cost in enumerate([1.0, 2.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0])]
    dinners = {"meals": {"dinner": MEAL_PRESETS["dinner"]["one main"]}}
    request = WeeklyMealPlanRequest(household_size=4, plan_shape=dinners, max_uses_per_recipe=cap)

    found = week_floor(request, mains, [item.recipe for item in mains])
    assert found.total_sgd == pytest.approx(floor)


def test_the_floor_under_a_cap_is_never_above_a_real_week():
    """Days may differ in which dishes they serve: the bound mixes them as a real week can, not day by day."""
    roles = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side"], "required": False}]
    policy = PlanningCompositionPolicy()
    mains, vegetables = [1.0, 10.0], [0.0, 20.0]

    def meal(main: float, vegetable: float | None) -> float:
        return main if vegetable is None else 0.75 * main + 0.5 * vegetable

    # Two days, each dish once. The cheapest real week: the 1.00 main alone, the 10.00 one with the 0.00 side.
    weeks = [
        meal(first, a) + meal(second, b)
        for first, second in itertools.permutations(mains)
        for a, b in itertools.product([None, *vegetables], repeat=2)
        if a is None or a != b
    ]
    bound = _cheapest_days(roles, {"main": mains, "vegetable": vegetables}, policy, 2)
    assert bound == pytest.approx(min(weeks)) == pytest.approx(8.5)


def optional_dinner(count: int) -> list[dict]:
    """A main and `count` dishes served only "if one fits", as the profile's meal editor allows (up to six)."""
    extra = ["vegetable", "soup", "vegetable-2", "main-2", "vegetable-3"][:count]
    return [
        {"role_id": "main", "courses": ["main"]},
        *({"role_id": r, "courses": ["side"], "required": False} for r in extra),
    ]


@pytest.mark.parametrize("seed", range(5))
def test_the_floor_with_several_optional_dishes_is_never_above_a_real_week(seed):
    """Three days, a main and two optional dishes, no dish twice: every real week, against the bound."""
    rng = random.Random(seed)
    roles, policy = optional_dinner(2), PlanningCompositionPolicy()
    prices = {role["role_id"]: sorted(round(rng.uniform(0, 10), 2) for _ in range(3)) for role in roles}
    weeks = []
    for mains in itertools.permutations(prices["main"]):
        for served in itertools.product([(), ("vegetable",), ("soup",), ("vegetable", "soup")], repeat=3):
            uses = {role: [day for day, extra in enumerate(served) if role in extra] for role in ("vegetable", "soup")}
            for picks in itertools.product(*(itertools.permutations(prices[r], len(uses[r])) for r in uses)):
                dish = {
                    (r, day): cost
                    for r, chosen in zip(uses, picks, strict=True)
                    for day, cost in zip(uses[r], chosen, strict=True)
                }
                week = 0.0
                for day, extra in enumerate(served):
                    shares = portion_shares(policy, ["main", *extra])
                    week += float(shares["main"]) * mains[day] + sum(float(shares[r]) * dish[r, day] for r in extra)
                weeks.append(week)
    assert 0 < _cheapest_days(roles, prices, policy, 3) <= min(weeks) + 1e-9


def test_the_floor_of_a_meal_of_six_dishes_is_found_at_once():
    """A main and five dishes "if one fits": trying every mix of the 32 ways to serve it took 90 s a meal."""
    roles = optional_dinner(5)
    prices = {role["role_id"]: [1.0 + day / 10 for day in range(7)] for role in roles}
    start = time.perf_counter()
    bound = _cheapest_days(roles, prices, PlanningCompositionPolicy(), 7)
    assert time.perf_counter() - start < 1.0
    assert bound == pytest.approx(sum(prices["main"]))  # an optional dish only adds to the meal's cost


def test_a_budget_any_multiple_over_the_floor_is_still_planned_up_front(monkeypatch, floors):
    """A pinch of each of eight packaged ingredients: the week uses cents and buys seven whole packages, far
    over any fixed multiple of the floor (one person's breakfasts on the release catalog: 122 times)."""
    dishes = [_dish(slug, "main", ingredient, 1, calories=400) for slug, ingredient in PACKAGED]
    with dish_client(monkeypatch, dishes) as client:
        first = "Dinners for 4, no dish twice, S$15 total"
        session = client.post("/api/agent/sessions", json={"message": first}).json()

        reply = session["messages"][-1]["content"]
        assert session["status"] == "collecting" and not session["can_confirm"], reply
        cost = cheapest_quoted(reply)
        assert 100 * floors[0] < 15 < cost  # what the floor alone would have let through
        ready = tap(client, session, labels(session)[0])
        assert ready["status"] == "ready", ready["messages"][-1]["content"]
        assert plans(client, ready)["grocery_estimate"]["purchase_total_sgd"] <= math.ceil(cost)


def test_a_budget_only_the_cap_on_uses_rules_out_is_refused_up_front(packaged):
    """With no dish twice the cheapest week buys seven dishes' packages; the floor must know that."""
    session = packaged.post("/api/agent/sessions", json={"message": "Dinners for 4, no dish twice, S$15 total"}).json()

    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"], reply
    assert cheapest_quoted(reply) > 15


def test_a_budget_under_the_floor_is_refused_without_planning_the_week(packaged, monkeypatch):
    checked = []
    monkeypatch.setattr(WeeklyMealPlanService, "check", lambda self, constraints: checked.append(constraints))
    session = packaged.post("/api/agent/sessions", json={"message": "Dinners for 4, no dish twice, S$1 total"}).json()

    assert not checked  # the floor already proves it: only the cheapest week is searched for
    cost = cheapest_quoted(session["messages"][-1]["content"])
    assert labels(session)[0] == f"Use S${math.ceil(cost)} for the week"


def test_half_the_household_is_searched_for_only_for_one_meal_a_day():
    asked = []

    def cheapest(**changes):
        asked.append(changes)
        return 20.0

    meals = {"lunch": MEAL_PRESETS["lunch"]["one dish"], "dinner": MEAL_PRESETS["dinner"]["one main"]}
    two_meals = AgentConstraintState(household_size=4, weekly_budget_sgd=10, plan_shape={"meals": meals})
    use = ("Use S$30 for the week", "Make the weekly budget S$30")
    assert _budget_short(30.0, two_meals, "en", cheapest).options == (use,)
    assert not asked  # a second search for more meals a day would take the reply past its time limit

    dish = {"role_id": "main", "courses": ["main"]}
    four = [dish, *({"role_id": f"vegetable-{n}", "courses": ["side"]} for n in range(2, 5))]
    big = AgentConstraintState(household_size=4, weekly_budget_sgd=10, plan_shape={"meals": {"dinner": four}})
    assert _budget_short(30.0, big, "en", cheapest).options == (use,)
    assert not asked  # nor for one meal a day of four dishes or more

    dinners = AgentConstraintState(household_size=4, weekly_budget_sgd=10)
    assert _budget_short(30.0, dinners, "en", cheapest).options[0] == use
    assert asked == [{"household_size": 2}]


def test_the_cheapest_week_search_bisects_under_the_cheapest_week_it_found(packaged, monkeypatch):
    probes = []
    original = meal_beam.MealBeamPlanner.search_candidates

    def search(self, problem):
        found = original(self, problem)
        if self.limits.meal_options_per_slot == CHEAPEST_MEAL_OPTIONS:
            probes.append((problem.purchase_budget_sgd, bool(found.states)))
        return found

    monkeypatch.setattr(meal_beam.MealBeamPlanner, "search_candidates", search)
    session = packaged.post("/api/agent/sessions", json={"message": "Dinners for 4, no dish twice, S$1 total"}).json()

    cost = cheapest_quoted(session["messages"][-1]["content"])
    first = next(index for index, (_, found) in enumerate(probes) if found)
    # Not halfway down to the budget the first week was found within: under what that week costs.
    assert probes[first + 1][0] < cost < probes[first][0] / 2


def test_the_cheapest_week_mode_returns_the_cheapest_validated_week_not_the_first(packaged, monkeypatch):
    """The amount offered is what the cheapest week the search found costs, so that week is the one returned."""
    results = []
    original = ProductPlanningEngine.plan

    def plan(self, *args, cheapest=False, **kwargs):
        result = original(self, *args, cheapest=cheapest, **kwargs)
        if cheapest:
            results.append(result)
        return result

    monkeypatch.setattr(ProductPlanningEngine, "plan", plan)
    session = packaged.post("/api/agent/sessions", json={"message": "Dinners for 4, no dish twice, S$1 total"}).json()

    passed = [a["purchase_total_sgd"] for a in results[0].trace["validation_attempts"] if a["status"] == "passed"]
    assert passed[0] > min(passed)  # the first week validated is not the cheapest...
    assert results[0].grocery.purchase_total_sgd == min(passed)  # ...the cheapest is returned
    assert f"S${min(passed):.2f}" in session["messages"][-1]["content"]


@pytest.mark.parametrize(
    ("extra", "searched"), [([], True), ([{"role_id": "vegetable-2", "courses": ["side"]}], False)]
)
def test_a_plan_of_meals_too_big_to_search_quickly_ends_without_the_cheapest_week(
    composed_client,  # noqa: F811
    monkeypatch,
    extra,
    searched,
):
    """Under a budget no week fits, the cheapest-week search is tried last, but not for four dishes a meal: it
    takes 5 to 16 s there on the release catalog, and minutes with no dish twice (a plan answers within 10 s)."""
    probes = []
    original = meal_beam.MealBeamPlanner.search_candidates

    def search(self, problem):
        if self.limits.meal_options_per_slot == CHEAPEST_MEAL_OPTIONS:
            probes.append(problem.purchase_budget_sgd)
        return original(self, problem)

    monkeypatch.setattr(meal_beam.MealBeamPlanner, "search_candidates", search)
    dinner = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side", "salad"]}]
    request = {
        "start_date": "2026-09-28",
        "household_size": 4,
        "max_cooking_time_minutes": 240,
        "pricing_mode": "fixture",
        "weekly_budget_sgd": 1,
        "plan_shape": {"meals": {"dinner": [*dinner, {"role_id": "soup", "courses": ["soup"]}, *extra]}},
    }
    response = composed_client.post("/api/plans/generate", json=request)

    assert response.status_code == 422, response.text
    assert bool(probes) is searched


@pytest.mark.parametrize(
    ("message", "expected", "first_option"),
    [
        ("something nice", "Happy to help you eat well.", "Plan a week of meals"),
        ("我想吃点好的", "好呀，我来帮你吃得好一点。", "规划一周的饭菜"),
        ("嗯……", "我不太确定这是不是饮食规划的请求。", "规划一周的饭菜"),
        ("Can you help me tomorrow?", "I am not sure whether this is a meal-planning request.", "Plan a week of meals"),
        # A greeting and a question about a dish are not wishes for food.
        ("good morning", "I am not sure whether this is a meal-planning request.", "Plan a week of meals"),
        ("这个菜怎么做？", "我不太确定这是不是饮食规划的请求。", "规划一周的饭菜"),
        # Boredom with the dishes is a wish for variety, in either language.
        ("the dishes are boring", "Let's make it more varied.", "A week with no dish twice"),
        ("菜很单调,不太好", "那就多换些花样。", "一周菜不重样"),
    ],
)
def test_an_unclear_message_gets_choices_in_its_language(composed_client, message, expected, first_option):  # noqa: F811
    session = composed_client.post("/api/agent/sessions", json={"message": message}).json()

    assert session["messages"][-1]["content"].startswith(expected)
    assert session["pending_interaction"]["options"][0]["label"] == first_option
    # A choice is what the household would have typed: it starts the planning conversation.
    started = tap(composed_client, session, first_option)
    assert started["constraints"]["household_size"] is None
    assert started["missing_fields"] == ["household_size"]


def planned(client, message: str) -> dict:
    session = client.post("/api/agent/sessions", json={"message": message}).json()
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["session"]


def say(client, session: dict, message: str) -> dict:
    response = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def test_swap_every_dish_asks_for_a_day_with_the_weeks_days_as_choices(composed_client):  # noqa: F811
    session = planned(composed_client, "Dinners for 4 this week")

    asked = say(composed_client, session, "swap every dish")
    assert asked["messages"][-1]["content"].startswith("I change one dish at a time")
    days = asked["pending_interaction"]["options"]
    assert [option["value"] for option in days] == [f"Day {n}" for n in range(1, 8)]
    assert re.fullmatch(r"[A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}", days[0]["label"])

    # Day 2 holds a main and a vegetable: its dishes are the next choices, and one leads to a preview.
    which = tap(composed_client, asked, days[1]["label"])
    dishes = [option["label"] for option in which["pending_interaction"]["options"]]
    assert len(dishes) == 2 and which["messages"][-1]["content"].startswith("That day has 2 dishes")
    previewed = tap(composed_client, which, dishes[0])
    assert previewed["pending_replan"]["status"] == "previewed"


def test_a_chinese_week_is_planned_and_changed_in_chinese(composed_client):  # noqa: F811
    session = planned(composed_client, "4个人，这周的晚餐")
    assert session["messages"][-1]["content"] == "这是你这一周的安排。点一道菜看食谱，想换什么都可以告诉我。"

    wish = say(composed_client, session, "我想吃点好的")
    assert wish["messages"][-1]["content"].startswith("想换换口味？")
    assert labels(wish) == ["换掉今晚的晚餐", "换别的日子的菜"]

    every = say(composed_client, session, "所有菜都换掉")
    assert every["messages"][-1]["content"] == "我一次换一道菜，确认之前什么都不会改。先从哪一天开始？"
    first_day = every["pending_interaction"]["options"][0]
    assert re.fullmatch(r"周[一二三四五六日] \d{1,2}月\d{1,2}日", first_day["label"]) and first_day["value"] == "第1天"
    which = tap(composed_client, every, first_day["label"])
    assert which["messages"][-1]["content"].startswith("那天有 2 道菜")
    dish = which["pending_interaction"]["options"][0]["label"]
    previewed = tap(composed_client, which, dish)
    assert previewed["messages"][-1]["content"].endswith("确认之前什么都不会改。")

    off_topic = say(composed_client, session, "我明天看什么电影？")
    assert off_topic["messages"][-1]["content"].startswith("这个请求不在 MealCraft 的饮食规划范围内")


def test_a_change_the_planner_turns_down_is_answered_wholly_in_chinese(composed_client):  # noqa: F811
    session = planned(composed_client, "4个人，这周的晚餐，做饭不超过30分钟")  # a soup takes 35 minutes

    changed = say(composed_client, session, "晚餐加一个汤")
    assert changed["messages"][-1]["content"] == "我没法做这个调整：我找不到满足所有限制的安排，放宽其中一个再试试。"


VEGETABLE_ALWAYS = {
    "plan_shape": {
        "meals": {
            "dinner": [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side", "salad"]}]
        }
    }
}


@pytest.mark.parametrize(
    ("message", "change", "over"),
    [
        (
            "这周的晚餐，一周38新币",
            "晚餐加一个汤",
            r"这样这周要 S\$(\d+\.\d\d)，超出每周 S\$38 的预算 S\$(\d+\.\d\d)。确认之前什么都不会改。$",
        ),
        (
            "This week's dinners, S$38 in total",
            "dinners with a soup",
            r"That makes the week S\$(\d+\.\d\d), S\$(\d+\.\d\d) over the S\$38 weekly budget\. "
            r"Nothing changes until you confirm\.$",
        ),
    ],
)
def test_a_dish_the_budget_left_cannot_buy_is_offered_over_it_with_the_overage(client, message, change, over):
    """Dinner is a main and a vegetable, and the week leaves too little of S$38 for a soup as well: the
    cheapest week with one is offered with what it puts the week over, to confirm or discard as a swap is."""
    profile_of_four(client, **VEGETABLE_ALWAYS)
    session = planned(client, message)

    changed = say(client, session, change)
    assert changed["pending_replan"]["status"] == "previewed", changed["messages"][-1]["content"]
    total, overage = map(float, re.search(over, changed["messages"][-1]["content"]).groups())
    assert overage == round(total - 38, 2) > 0

    applied = client.post(f"/api/agent/sessions/{session['id']}/replan/confirm")
    assert applied.status_code == 200, applied.text
    estimate = applied.json()["plan"]["grocery_estimate"]
    assert (estimate["purchase_total_sgd"], estimate["within_weekly_budget"]) == (total, False)
    assert {dish["role_id"] for dish in applied.json()["plan"]["days"]} == {"main", "vegetable", "soup"}


def test_a_dish_added_over_the_budget_left_is_searched_for_once_within_it(composed_client, monkeypatch):  # noqa: F811
    """Within the budget left, a change is searched for once, without the cheapest-week search Plan ends on:
    the week is offered over the budget instead, and a chat turn stays within its time."""
    session = planned(composed_client, "4个人，这周的晚餐，一周38新币")
    failed: list[tuple[float | None, bool]] = []
    plan = ProductPlanningEngine.plan

    def spy(self, constraints, *args, **kwargs):
        try:
            return plan(self, constraints, *args, **kwargs)
        except ProductPlanningError as error:
            failed.append((constraints.weekly_budget_sgd, "cheapest_search" in error.trace))
            raise

    monkeypatch.setattr(ProductPlanningEngine, "plan", spy)
    changed = say(composed_client, session, "晚餐加一个汤")

    assert changed["pending_replan"]["status"] == "previewed"
    assert failed == [(38.0, False)]  # every dinner is planned again: nothing kept, the whole S$38 left


@pytest.mark.parametrize(
    ("said", "chinese"),
    [
        (
            "I couldn't fit seven dinners into S$38.00. The cheapest week I found costs S$41.20. "
            "Try a higher budget or fewer limits.",
            "S$38.00 排不下这些饭菜：我找到的最便宜的一周要 S$41.20。可以提高预算，或者少一些限制。",
        ),
        ("There is no dinner left to change on those days.", "那几天已经没有可以调整的晚餐了。"),
        ("Lunch is not planned on those days.", "那几天没有安排午餐。"),
        ("This meal is locked and cannot be replanned.", "这顿饭已经锁定，不能调整。"),
        (
            "No dish other than Tofu Bowl satisfies the current hard constraints.",
            "除了Tofu Bowl，没有别的菜符合现在的限制。",
        ),
        ("A reason no one has written Chinese for yet.", "有个限制这次满足不了。"),
    ],
)
def test_the_reason_a_change_or_a_week_is_turned_down_follows_the_households_language(said, chinese):
    assert planner_message(said, "zh") == chinese
    assert planner_message(said, "en") == said


@pytest.mark.parametrize(
    ("message", "reason", "option"),
    [
        (
            "Dinners for 4, 10 minutes of cooking",
            "No main dish I can plan for dinner fits a 10-minute cooking limit (the quickest takes 25 minutes)",
            "Allow up to 25 minutes",
        ),
        (
            "Dinners for 4, sodium under 100 mg",
            "No main dish I can plan for dinner fits a 100 mg sodium limit (the lowest has 300 mg)",
            "Allow up to 300 mg sodium",
        ),
    ],
)
def test_a_limit_no_dish_meets_is_named_with_the_dish_that_comes_closest(composed_client, message, reason, option):  # noqa: F811
    session = composed_client.post("/api/agent/sessions", json={"message": message}).json()

    assert session["status"] == "collecting" and not session["can_confirm"]
    assert reason in session["messages"][-1]["content"]
    eased = tap(composed_client, session, option)
    assert eased["status"] == "ready" and eased["can_confirm"]


VARIED = [
    "chicken_breast",
    "brown_rice",
    "cucumber",
    "cherry_tomato",
    "firm_tofu",
    "soba_noodle",
    "broccoli",
    "red_lentil",
    "rolled_oats",
    "salmon_fillet",
    "canned_tuna",
    "chickpea",
    "black_bean",
    "quinoa",
    "wholewheat_pasta",
    "sweet_potato",
]


@pytest.fixture(params=["fixture", "openai"])
def varied(request, monkeypatch):
    """Sixteen mains: two weeks' worth with nothing in common."""
    if request.param == "openai":
        stub_openai(monkeypatch)
    dishes = [_dish(f"{name.replace('_', '-')}-main", "main", name, 200, calories=450) for name in VARIED]
    with dish_client(monkeypatch, dishes) as client:
        yield client


def slugs(client, plan_id: int) -> list[str]:
    return [dish["recipe"]["slug"] for dish in client.get(f"/api/plans/{plan_id}").json()["days"]]


def plan_again(client, session: dict, complaint: str = "the dishes are boring") -> dict:
    offered = say(client, session, complaint)
    return tap(client, offered, labels(offered)[0])


@pytest.mark.parametrize("complaint", ["菜很单调,不太好", "the dishes are boring", "too repetitive"])
def test_a_week_found_monotonous_is_replaced_by_a_new_week_with_different_dishes(varied, complaint):
    session = planned(varied, "Dinners for 4 this week")
    before = slugs(varied, session["plan_id"])

    offered = say(varied, session, complaint)
    chinese = language(complaint) == "zh"
    assert offered["messages"][-1]["content"].startswith(
        "那就多换些花样。" if chinese else "Let's make it more varied."
    )
    again = labels(offered)[0]
    assert again in {"Plan a new week with different dishes", "重新规划一周，换一批菜"}

    new = tap(varied, offered, again)
    assert new["plan_id"] not in {None, session["plan_id"]} and new["status"] == "planned"
    assert new["messages"][-1]["content"].startswith(
        "新的一周排好了：7 道不同的菜" if chinese else "Here's a new week with 7 different dishes"
    )
    mains = slugs(varied, new["plan_id"])
    assert len(mains) == len(set(mains)) == 7  # none twice
    assert not set(before) & set(mains)  # and none of last week's
    assert slugs(varied, session["plan_id"]) == before  # the old week stays saved as it was


def test_a_household_with_a_weekly_budget_gets_a_new_week_within_it(varied):
    session = planned(varied, "Dinners for 4, S$40 total")
    before = slugs(varied, session["plan_id"])

    new = plan_again(varied, session)
    assert new["plan_id"] not in {None, session["plan_id"]}, new["messages"][-1]["content"]
    assert new["status"] == "planned" and new["messages"][-1]["content"].startswith("Here's a new week with ")
    week = varied.get(f"/api/plans/{new['plan_id']}").json()
    assert week["grocery_estimate"]["purchase_total_sgd"] <= 40  # the budget holds
    assert not set(before) & {dish["recipe"]["slug"] for dish in week["days"]}


def test_a_new_week_the_budget_cannot_buy_keeps_the_week_and_says_why(varied):
    session = planned(varied, "Dinners for 4, S$22 total")  # the seven cheapest mains

    kept = say(varied, session, "Plan a new week with different dishes, no dish twice")
    assert kept["plan_id"] == session["plan_id"] and kept["status"] == "planned"
    reply = kept["messages"][-1]["content"]
    assert reply.startswith("Your week stays as it is. For a new week with different dishes: S$22 for 4 people is ")
    assert cheapest_quoted(reply) > 22  # the cheapest week of other dishes the search found
    assert labels(kept)[0].startswith("Swap ")  # a swap instead, not a dead end


def test_a_new_week_with_too_few_dishes_keeps_the_week_and_says_why(composed_client):  # noqa: F811
    session = planned(composed_client, "Dinners for 4 this week")  # two mains for seven dinners

    kept = plan_again(composed_client, session)
    assert kept["plan_id"] == session["plan_id"]
    assert kept["messages"][-1]["content"].startswith(
        "Your week stays as it is. For a new week with different dishes: I couldn't plan this week"
    )


def test_a_new_week_no_more_varied_than_this_one_is_not_put_in_its_place(packaged):
    """Eight mains: too few others to leave this week's out, so the new week would be the same seven."""
    session = planned(packaged, "Dinners for 4, S$40 total")

    kept = plan_again(packaged, session)
    assert kept["plan_id"] == session["plan_id"]
    assert kept["messages"][-1]["content"] == (
        "Your week stays as it is: the most varied new week I could plan within S$40 has 7 different dishes, "
        "0 of them new, and this one has 7. I can swap a dish instead."
    )


def test_a_repeated_dish_is_offered_for_a_swap_when_the_week_repeats_one(composed_client):  # noqa: F811
    session = planned(composed_client, "Dinners for 4 this week")  # two mains for seven dinners
    offered = say(composed_client, session, "the dishes are boring")

    swap = labels(offered)[1]
    assert re.fullmatch(r"Swap the .+ on [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}", swap)
    previewed = tap(composed_client, offered, swap)
    assert previewed["pending_replan"]["status"] == "previewed"
