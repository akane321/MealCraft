"""What the 2026-10-02 walkthrough found in the conversation.

An impossible week is refused before the assistant says it has everything, with the number that shows
it; a week the planner then cannot find is explained in the chat by the limit its search ran into. Every
templated reply follows the household's language, and an unclear message gets choices, not a dead end.
Both parsers: the rule parser, and the live one with its model stubbed (no call goes out).
"""

import math
import re
from types import SimpleNamespace

import pytest

from app.agent.limits import planning_failure
from app.agent.parser import FallbackConstraintParser, OpenAIConstraintParser, RuleBasedConstraintParser
from app.agent.replies import language
from app.planning.week_floor import _cheapest_meal
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from app.schemas.planning_v2 import PlanningCompositionPolicy
from tests.test_planning_capability import composed_client  # noqa: F401


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


@pytest.fixture(params=["fixture", "openai"])
def client(request, composed_client, monkeypatch):  # noqa: F811
    """The synthetic week (two mains, three vegetables, a soup), in each parser mode."""
    if request.param == "openai":
        import app.api.routes.agent as routes

        heard = {
            "Plan a week for 4 for S$10 total": AgentConstraintExtraction(household_size=4, weekly_budget_sgd=10),
            "我们4个人，一周一共10新币": AgentConstraintExtraction(household_size=4, weekly_budget_sgd=10),
            "Make the weekly budget S$36": AgentConstraintExtraction(weekly_budget_sgd=36),
        }

        def parser(settings, database=None, *, provider=None):
            stub = SimpleNamespace(invoke=lambda prompt: heard[prompt.rsplit("Latest user message: ", 1)[1].strip()])
            parsed = live_parser(AgentConstraintExtraction())
            parsed.primary.structured_model = stub
            return parsed

        monkeypatch.setattr(routes, "create_constraint_parser", parser)
    composed_client.mode = request.param
    return composed_client


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


def test_an_impossible_budget_is_refused_up_front_and_a_failed_week_replaces_the_plan_card(client):
    session = client.post("/api/agent/sessions", json={"message": "Plan a week for 4 for S$10 total"}).json()
    assert session["parser_provider"] == client.mode

    # Refused before "That's everything I need", with the per-person number and the floor that proves it.
    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"]
    assert "everything I need" not in reply
    assert "S$10 for 4 people is S$0.36 a person a meal over 7 meals" in reply
    floor = float(re.search(r"cost at least S\$(\d+\.\d\d) for the week", reply).group(1))
    assert floor > 10
    labels = [option["label"] for option in session["pending_interaction"]["options"]]
    assert labels[0] == f"Raise the weekly budget to S${math.ceil(floor)}"

    # A budget the floor allows is planned; this one is still under what whole packages cost, so the
    # search finds no week, and the reply says which limit it ran into instead of a generic failure.
    ready = tap(client, session, labels[0])
    assert ready["status"] == "ready" and ready["can_confirm"]
    assert ready["constraints"]["weekly_budget_sgd"] == math.ceil(floor)
    failed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert failed.status_code == 422
    why = failed.json()["detail"]
    assert why.startswith(f"I couldn't plan this week: the search found no week that meets the S${math.ceil(floor)}.00")
    assert "couldn't find a week that meets every limit" not in why

    explained = client.get(f"/api/agent/sessions/{session['id']}").json()
    assert explained["messages"][-1]["content"] == why
    assert not explained["can_confirm"] and explained["status"] == "collecting"  # the Plan card gives way
    assert [option["label"] for option in explained["pending_interaction"]["options"]] == [
        f"Try S${math.ceil(math.ceil(floor) * 1.25)} for the week"
    ]


def test_a_chinese_household_is_refused_in_chinese_with_choices_in_chinese(client):
    session = client.post("/api/agent/sessions", json={"message": "我们4个人，一周一共10新币"}).json()
    assert session["parser_provider"] == client.mode

    reply = session["messages"][-1]["content"]
    assert session["status"] == "collecting" and not session["can_confirm"]
    assert "4 个人一周 S$10，相当于每人每餐 S$0.36（共 7 餐）" in reply and "至少要" in reply
    assert not re.search(r"[A-Za-z]{3,}", reply)
    options = session["pending_interaction"]["options"]
    assert options[0]["label"].startswith("把每周预算提高到 S$")
    assert options[0]["value"].startswith("每周预算 ")


def test_no_dish_twice_with_too_few_dishes_is_refused_with_the_count(composed_client):  # noqa: F811
    session = composed_client.post("/api/agent/sessions", json={"message": "Dinners for 4, no repeats"}).json()

    assert session["status"] == "collecting" and not session["can_confirm"]
    assert (
        "No dish twice needs 7 different main dishes for dinner this week, and only 2 fit"
        in (session["messages"][-1]["content"])
    )


def test_a_failed_search_names_the_limit_it_ran_into_never_a_proof():
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=50)
    over = {"purchase_total_sgd": 61.2, "checks": [{"code": "purchase_budget", "status": "failed", "hard": True}]}
    told = planning_failure("candidate_rejected", {"validation_attempts": [over]}, constraints, "en")
    assert told.text == (
        "I couldn't plan this week: the search found no week that meets the S$50.00 weekly budget; the cheapest "
        "week it finished costs S$61.20. That is the limit it kept running into."
    )
    assert told.options == (("Try S$62 for the week", "Make the weekly budget S$62"),)
    emptied = planning_failure("candidate_rejected", {"search": {"emptied_by": "repeats"}}, constraints, "zh")
    assert emptied.text == "这周没排出来：搜索没有找到符合菜不重样的要求的一周。卡住它的就是这个限制。"
    slow = planning_failure("candidate_rejected", {"search": {"exhausted": True}}, constraints, "en")
    assert slow.retry  # nothing to change: the Plan card stays


def test_the_cheapest_meal_counts_each_dish_at_its_share():
    roles = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["side"], "required": False}]
    policy = PlanningCompositionPolicy()
    # A main alone is a whole meal; with a vegetable it is 0.75 of one and the vegetable 0.5.
    assert _cheapest_meal(roles, {"main": 8.0, "vegetable": 1.0}, policy) == pytest.approx(6.5)
    assert _cheapest_meal(roles, {"main": 8.0, "vegetable": 10.0}, policy) == pytest.approx(8.0)
    assert _cheapest_meal(roles, {"main": 8.0}, policy) == pytest.approx(8.0)


@pytest.mark.parametrize(
    ("message", "expected", "first_option"),
    [
        ("something nice", "Happy to help you eat well.", "Plan a week of meals"),
        ("我想吃点好的", "好呀，我来帮你吃得好一点。", "规划一周的饭菜"),
        ("嗯……", "我不太确定这是不是饮食规划的请求。", "规划一周的饭菜"),
        ("Can you help me tomorrow?", "I am not sure whether this is a meal-planning request.", "Plan a week of meals"),
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
    assert wish["messages"][-1]["content"].startswith("想吃点好的？")
    assert [option["label"] for option in wish["pending_interaction"]["options"]] == [
        "把今晚的晚餐换成更好吃的",
        "换别的日子的菜",
    ]

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
