"""Short plans in the chat (owner, 2026-10-29): "one dinner for 1 person tomorrow", "dinner tonight", "today", "this
weekend", "the next 3 days" plan only those days and meals; the shopping list and the budget cover only them."""

from datetime import date, datetime

import pytest

from app.agent.parser import RuleBasedConstraintParser, budgets, read_budgets
from app.agent.plan_dates import read_span
from app.agent.workflow import AgentConstraintWorkflow
from app.core import clock
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from tests.test_recipes import recipe_client as recipe_client  # noqa: F401

MONDAY = date(2026, 10, 12)


def at(day: int, hour: int) -> datetime:
    return datetime(2026, 10, day, hour, 0, tzinfo=clock.SINGAPORE)


MONDAY_9, MONDAY_12, MONDAY_22 = at(12, 9), at(12, 12), at(12, 22)
SATURDAY, SUNDAY = at(17, 9), at(18, 9)
TOMORROW = date(2026, 10, 13)
ALL = ("breakfast", "lunch", "dinner")


@pytest.mark.parametrize(
    ("now", "message", "start", "days", "meals"),
    [
        (MONDAY_9, "one dinner for 1 person tomorrow", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "Dinner tomorrow", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "What about tomorrow's lunch and dinner?", TOMORROW, 1, ("lunch", "dinner")),
        (MONDAY_9, "Plan tomorrow for two", TOMORROW, 1, None),
        (MONDAY_9, "明天晚餐，一个人", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "明天", TOMORROW, 1, None),
        (MONDAY_9, "明晚吃什么，帮我排一下", TOMORROW, 1, ("dinner",)),
        # Tonight is today's dinner, until dinner time is over.
        (MONDAY_12, "dinner tonight", MONDAY, 1, ("dinner",)),
        (MONDAY_12, "今晚", MONDAY, 1, ("dinner",)),
        (MONDAY_22, "dinner tonight", TOMORROW, 1, ("dinner",)),
        # Today is the meals of today that are not over.
        (MONDAY_9, "plan today", MONDAY, 1, ALL),
        (MONDAY_12, "plan today", MONDAY, 1, ("lunch", "dinner")),
        (at(12, 16), "今天", MONDAY, 1, ("dinner",)),
        (MONDAY_22, "plan today", TOMORROW, 1, None),
        # The coming Saturday and Sunday; on a Saturday today and tomorrow; on a Sunday today.
        (MONDAY_9, "this weekend", date(2026, 10, 17), 2, None),
        (MONDAY_9, "周末两天", date(2026, 10, 17), 2, None),
        (SATURDAY, "dinners for the weekend", date(2026, 10, 17), 2, ("dinner",)),
        (SUNDAY, "the weekend", date(2026, 10, 18), 1, None),
        # N days from the default start.
        (MONDAY_9, "the next 3 days", None, 3, None),
        (MONDAY_9, "next three days please", None, 3, None),
        (MONDAY_9, "5 days of dinners", None, 5, ("dinner",)),
        (MONDAY_9, "接下来三天", None, 3, None),
        (MONDAY_9, "三天的饭", None, 3, None),
        (MONDAY_9, "未来十二天", None, 12, None),
        (MONDAY_9, "for 14 days", None, 14, None),
        # The meals named anywhere in the message narrow the days, a meal said no is left out of them.
        (MONDAY_9, "Dinner for 2 tomorrow", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "Plan dinner for two people tomorrow", TOMORROW, 1, ("dinner",)),
        (MONDAY_12, "dinner for 1 today", MONDAY, 1, ("dinner",)),
        (MONDAY_9, "lunch and dinner for the weekend", date(2026, 10, 17), 2, ("lunch", "dinner")),
        (MONDAY_9, "晚餐两个人，明天", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "no breakfast tomorrow", TOMORROW, 1, ("lunch", "dinner")),
        (MONDAY_9, "Plan tomorrow for two, no breakfast", TOMORROW, 1, ("lunch", "dinner")),
        (MONDAY_9, "no dinner tomorrow", TOMORROW, 1, ("breakfast", "lunch")),
        (MONDAY_9, "明天不要早餐", TOMORROW, 1, ("lunch", "dinner")),
        (MONDAY_9, "Dinners for two, no breakfast, tomorrow", TOMORROW, 1, ("dinner",)),
        (MONDAY_9, "Plan tomorrow, also plan lunch", TOMORROW, 1, None),
        # Today and tomorrow are two days; past dinner time only tomorrow is left.
        (MONDAY_9, "today and tomorrow", MONDAY, 2, None),
        (MONDAY_9, "today and tomorrow dinners", MONDAY, 2, ("dinner",)),
        (MONDAY_9, "今天和明天的晚餐", MONDAY, 2, ("dinner",)),
        (MONDAY_22, "today and tomorrow", TOMORROW, 1, None),
        # A meal-only phrase narrows the meals and leaves the days alone.
        (MONDAY_9, "dinner only", None, None, ("dinner",)),
        (MONDAY_9, "Dinners only, for two", None, None, ("dinner",)),
        (MONDAY_9, "lunch and dinner only", None, None, ("lunch", "dinner")),
        (MONDAY_9, "只要晚餐", None, None, ("dinner",)),
    ],
)
def test_the_days_and_meals_a_request_plans(now, message, start, days, meals) -> None:
    span = read_span(message, now)
    assert span is not None
    assert (span.start, span.day_count, span.meals) == (start, days, meals)


@pytest.mark.parametrize(
    "message",
    [
        "Dinners for two, no pork, S$100 a week",
        "Dinners for two next week",
        "Plan the week from tomorrow",  # a start, not one day
        "starting today",
        "从今天开始",
        "明天开始排晚饭",
        "no soup on Friday",
        "I cook 3 days a week",
        "30 days",  # a plan is 14 days at most
        "一天三餐",
        "the day after tomorrow",
        "tomorrow and the day after",
        "tonight and tomorrow",  # two kinds of day: the model reads it
        # A negation or an absence next to the day word: a rule for a day, not a request for it.
        "Dinners for two, I'm away this weekend",
        "Dinners for two, no soup on the weekend",
        "Dinners for two, except the weekend",
        "周末不吃饭，其他天晚餐两人",
        "两个人一周晚餐，周末不做饭",
        "今天不用做饭，下周一开始排晚餐",
        "I won't be home tomorrow",
        # Food at home, and durations about it, are no days of the plan.
        "I bought tofu today, dinners for two",
        "I have chicken I got today, dinners for two",
        "I have spinach that expires in 2 days, dinners for 2",
        "dinners for 2, leftovers can last 3 days",
        "no more than 3 days of leftovers",
        "晚餐两个人，鸡肉放了三天了",
        "每周五天做饭",
        "周五天气好，晚餐两个人",
        "三天",
        "in 3 days",
    ],
)
def test_a_request_that_names_no_short_plan(message: str) -> None:
    assert read_span(message, MONDAY_9) is None


def test_the_meals_a_household_plans_decide_what_today_leaves() -> None:
    assert read_span("today", at(12, 8), ("dinner",)).meals == ("dinner",)  # type: ignore[union-attr]
    # Nothing left of a household that plans breakfasts only: tomorrow's.
    late = read_span("today", at(12, 11), ("breakfast",))
    assert late is not None and (late.start, late.meals, late.moved) == (TOMORROW, None, True)


def setup(message: str, now: datetime = MONDAY_9, **current) -> tuple[AgentConstraintState, str]:
    with clock.frozen(now):
        state = AgentConstraintWorkflow(RuleBasedConstraintParser()).run(
            message, current=AgentConstraintState(**current), acknowledged_unknowns=[], history=[]
        )
    return AgentConstraintState.model_validate(state["merged_constraints"]), state["assistant_message"]


def meals_of(state: AgentConstraintState) -> list[str]:
    assert state.plan_shape is not None
    return list(state.plan_shape.meals)


def test_one_dinner_tomorrow_sets_the_day_the_meal_and_says_so() -> None:
    state, reply = setup("One dinner for 1 person tomorrow")
    assert (state.day_count, state.start_date, meals_of(state)) == (1, TOMORROW, ["dinner"])
    assert "The plan is for Tue 13 Oct." in reply and "week" not in reply


def test_a_chinese_request_is_answered_in_chinese() -> None:
    state, reply = setup("明天晚餐，一个人")
    assert (state.day_count, state.start_date, meals_of(state)) == (1, TOMORROW, ["dinner"])
    assert "这个计划是周二 10月13日的。" in reply


def test_the_next_three_days_run_from_the_default_start() -> None:
    state, reply = setup("Dinners for two for the next 3 days")
    assert (state.day_count, state.start_date) == (3, MONDAY)
    assert "The plan runs Mon 12 Oct – Wed 14 Oct." in reply
    # Past dinner time the default start is tomorrow.
    assert setup("接下来三天", MONDAY_22)[0].start_date == TOMORROW


def test_this_weekend_is_the_coming_saturday_and_sunday() -> None:
    state, reply = setup("Dinners for two this weekend")
    assert (state.day_count, state.start_date) == (2, date(2026, 10, 17))
    assert "The plan runs Sat 17 Oct – Sun 18 Oct." in reply


def test_dinner_tonight_after_dinner_time_moves_to_tomorrow_and_says_so() -> None:
    state, reply = setup("dinner tonight", MONDAY_22)
    assert (state.day_count, state.start_date, meals_of(state)) == (1, TOMORROW, ["dinner"])
    assert "Today's meals are over, so the plan starts tomorrow." in reply


def test_a_dinner_for_a_household_that_plans_no_dinner_is_planned_as_the_default_dinner() -> None:
    shape = {"meals": {"lunch": [{"role_id": "main", "courses": ["main"]}]}}
    state, _ = setup("dinner tomorrow", plan_shape=shape)
    assert meals_of(state) == ["dinner"]


def test_a_household_keeps_the_composition_of_the_meal_it_plans_today() -> None:
    soup = {"role_id": "soup", "courses": ["soup"]}
    main = {"role_id": "main", "courses": ["main"]}
    shape = {"meals": {"lunch": [main], "dinner": [main, soup]}}
    state, _ = setup("dinner tomorrow", plan_shape=shape)
    assert state.plan_shape is not None
    assert [role.role_id for role in state.plan_shape.meals["dinner"]] == ["main", "soup"]


def test_a_week_request_keeps_the_week_and_its_dump() -> None:
    state, reply = setup("Dinners for two, S$100 a week")
    assert state.day_count == 7 and "day_count" not in state.model_dump(mode="json")
    assert "plan runs" not in reply


@pytest.mark.parametrize(
    ("message", "weekly"),
    [
        ("S$15 for tomorrow's dinner", 15),
        ("tomorrow's dinner, S$15", 15),
        ("$20 for the weekend", 20),
        ("S$30 for the next 3 days", 30),
        ("S$30 for 3 days", 30),
        ("明天晚餐预算15新币", 15),
        ("周末一共40块", 40),
    ],
)
def test_an_amount_stated_for_the_plan_is_the_plans_budget(message: str, weekly: float) -> None:
    assert budgets(message.lower(), 2) == (None, weekly)


def test_an_amount_for_a_meal_stays_a_meal_budget() -> None:
    assert budgets("s$12 per dinner tomorrow", 2) == (12, None)


def test_a_stated_budget_is_the_plans_and_is_not_prorated() -> None:
    state, reply = setup("S$15 for tomorrow's dinner, 2 people", weekly_budget_sgd=140)
    assert state.weekly_budget_sgd == 15 and "of your" not in reply
    assert "S$15 for the plan" in reply and "for the week" not in reply


@pytest.mark.full_default
def test_a_saved_weekly_budget_is_prorated_by_the_meals_the_plan_holds() -> None:
    state, reply = setup("One dinner tomorrow", weekly_budget_sgd=140, household_size=1)
    # One dinner of the 21 meals of a week of breakfast, lunch and dinner.
    assert state.weekly_budget_sgd == 6.67
    assert "That is S$6.67 of your S$140 weekly budget." in reply
    # The next 3 days of all three meals: 9 of 21.
    assert setup("the next 3 days", weekly_budget_sgd=140, household_size=1)[0].weekly_budget_sgd == 60
    # A household that plans dinners only: one dinner is a seventh.
    dinners = {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}}
    assert (
        setup("dinner tomorrow", weekly_budget_sgd=140, household_size=1, plan_shape=dinners)[0].weekly_budget_sgd == 20
    )
    # A week of dinners only, of a household that plans all three meals: 7 of 21 meals.
    assert setup("dinners only this week", weekly_budget_sgd=140, household_size=1)[0].weekly_budget_sgd == 46.67


@pytest.mark.full_default
def test_a_budget_is_asked_for_in_plan_words_and_a_week_stays_week_words() -> None:
    _, short = setup("tomorrow's dinner")
    assert "How many people should this plan serve?" in short
    _, week = setup("dinners for the week")
    assert "How many people should this weekly plan serve?" in week


@pytest.mark.full_default
def test_the_model_fills_the_days_and_meals_when_the_rules_find_none() -> None:
    class Model(RuleBasedConstraintParser):
        def parse(self, message, **kwargs):
            return AgentConstraintExtraction(
                household_size=1, plan_day_count=2, plan_meals=["dinner", "lunch", "lunch"]
            )

    state = AgentConstraintWorkflow(Model()).run(
        "a couple of evenings", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    merged = AgentConstraintState.model_validate(state["merged_constraints"])
    assert merged.day_count == 2 and meals_of(merged) == ["lunch", "dinner"]


def test_the_rules_win_over_the_model_where_they_match() -> None:
    class Model(RuleBasedConstraintParser):
        def parse(self, message, **kwargs):
            return AgentConstraintExtraction(household_size=1, plan_day_count=5, plan_meals=["lunch"])

    state = AgentConstraintWorkflow(Model()).run(
        "the next 3 days, dinners only", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    merged = AgentConstraintState.model_validate(state["merged_constraints"])
    assert merged.day_count == 3 and meals_of(merged) == ["dinner"]


def test_the_extraction_keeps_only_days_and_meals_a_plan_can_have() -> None:
    with pytest.raises(ValueError):
        AgentConstraintExtraction(plan_day_count=15)
    assert AgentConstraintExtraction(plan_meals=["dinner", "breakfast"]).plan_meals == ["breakfast", "dinner"]
    assert AgentConstraintExtraction(plan_meals=[]).plan_meals is None


def member():
    return {
        "name": "Ann",
        "servings_per_meal": 1,
        "allergens": [],
        "excluded_ingredients": [],
        "dietary_preferences": [],
    }


def chat(client, message: str) -> dict:
    created = client.post("/api/agent/sessions", json={"message": message})
    assert created.status_code == 201, created.text
    return created.json()


def planned(client, session: dict) -> dict:
    confirmed = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["plan"]


@pytest.fixture
def monday_noon(monkeypatch):
    monkeypatch.setattr(clock, "simulated", lambda: "2026-10-12T12:00")


def test_a_chat_plans_one_dinner_for_tomorrow_and_prorates_the_saved_budget(recipe_client, monday_noon):
    created = recipe_client.post(
        "/api/household-profiles",
        json={"name": "Ann", "members": [member()], "weekly_budget_sgd": 140, "requires_halal": False},
    )
    assert created.status_code == 201, created.text

    session = chat(recipe_client, "One dinner for 1 person tomorrow")
    assert session["can_confirm"] and session["constraints"]["day_count"] == 1
    assert session["constraints"]["weekly_budget_sgd"] == 20  # a dinner of the seven in a week of dinners
    assert "That is S$20.00 of your S$140 weekly budget." in session["messages"][-1]["content"]

    plan = planned(recipe_client, session)
    assert (plan["day_count"], plan["start_date"], plan["end_date"]) == (1, "2026-10-13", "2026-10-13")
    assert {day["meal_type"] for day in plan["days"]} == {"dinner"} and {day["day_index"] for day in plan["days"]} == {
        1
    }
    assert plan["grocery_estimate"]["weekly_budget_sgd"] == 20
    assert (
        plan["current"]
        and "Here's your plan."
        in recipe_client.get(f"/api/agent/sessions/{session['id']}").json()["messages"][-1]["content"]
    )


def test_an_amount_stated_for_the_plan_is_the_budget_the_plan_is_made_with(recipe_client, monday_noon):
    session = chat(recipe_client, "Dinner tonight for 2 people, S$30 for tonight")
    assert session["constraints"]["weekly_budget_sgd"] == 30
    plan = planned(recipe_client, session)
    assert (plan["day_count"], plan["start_date"]) == (1, "2026-10-12")
    assert plan["grocery_estimate"]["weekly_budget_sgd"] == 30


def test_a_weekend_plan_and_the_next_three_days_cover_only_those_days(recipe_client, monday_noon):
    weekend = planned(recipe_client, chat(recipe_client, "Dinners for 2 people this weekend"))
    assert (weekend["day_count"], weekend["start_date"], weekend["end_date"]) == (2, "2026-10-17", "2026-10-18")
    three = planned(recipe_client, chat(recipe_client, "Dinners for 2 people for the next 3 days"))
    assert (three["day_count"], three["start_date"], three["end_date"]) == (3, "2026-10-12", "2026-10-14")
    assert {day["day_index"] for day in three["days"]} == {1, 2, 3}


def test_a_new_plan_of_a_short_plan_is_as_short(recipe_client, monday_noon):
    session = chat(recipe_client, "Dinners for 2 people for the next 3 days")
    first = planned(recipe_client, session)
    answered = recipe_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "Plan a new one with different dishes"}
    )
    assert answered.status_code == 200, answered.text
    replacement = recipe_client.get(f"/api/plans/{answered.json()['plan_id']}").json()
    assert (replacement["day_count"], replacement["start_date"], replacement["end_date"]) == (
        3,
        first["start_date"],
        first["end_date"],
    )
    assert replacement["plan_shape"] == first["plan_shape"]


def test_a_day_outside_a_short_plan_is_not_in_it_and_nothing_changes(recipe_client, monday_noon):
    session = chat(recipe_client, "Dinners for 2 people for the next 3 days")  # Mon 12 to Wed 14 Oct
    plan = planned(recipe_client, session)
    for message in ("Add a soup on Saturday", "Swap Friday's dinner", "Skip the dinner on Sunday"):
        answered = recipe_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["messages"][-1]["content"].startswith("That day is not in this plan"), message
        assert body["pending_replan"] is None
    assert recipe_client.get(f"/api/plans/{plan['id']}/events").json()["items"] == []


def test_the_variety_target_is_capped_at_what_the_places_of_the_plan_hold():
    """Four different dishes cannot be asked of one dinner of one dish (agent/limits.py)."""
    from app.agent import limits
    from app.planning.week_floor import WeekFloor

    calls = []

    def check(**changes):
        calls.append(changes)

    def distinct(places: int):
        floor = WeekFloor(days=places, meals=places, total_sgd=1.0, meal_sgd={}, empty_roles=[], roles={})
        dinner = {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}}
        constraints = AgentConstraintState(household_size=1, weekly_budget_sgd=30, day_count=places, plan_shape=dinner)
        return limits.refusal(
            constraints, lambda **_: floor, "en", check=check, cheapest=lambda **_: 99.0, distinct_dishes=lambda: 2
        )

    assert distinct(1) is None and calls == [{}]  # 2 dishes already fill the one place; nothing more is searched
    calls.clear()
    assert distinct(3) is None  # three places: three different dishes are asked for, not four
    assert calls == [{}, {"minimum_distinct_dishes": 3}]
    calls.clear()
    assert distinct(5) is None
    assert calls == [{}, {"minimum_distinct_dishes": 4}]


def step(message: str, state: AgentConstraintState, now: datetime = MONDAY_9) -> tuple[AgentConstraintState, str]:
    """One more message of a conversation that holds `state`."""
    with clock.frozen(now):
        out = AgentConstraintWorkflow(RuleBasedConstraintParser()).run(
            message, current=state, acknowledged_unknowns=[], history=[]
        )
    return AgentConstraintState.model_validate(out["merged_constraints"]), out["assistant_message"]


@pytest.mark.full_default
def test_every_change_of_days_or_meals_prorates_from_the_saved_weekly_budget_and_a_week_restores_it() -> None:
    state = AgentConstraintState(weekly_budget_sgd=140, household_size=1)
    for message, days, budget, meals in [
        ("One dinner tomorrow", 1, 6.67, ["dinner"]),
        ("this weekend", 2, 13.33, ["dinner"]),
        ("the next 3 days", 3, 20, ["dinner"]),
        ("lunch and dinner only", 3, 40, ["lunch", "dinner"]),
        ("make it the next 2 days", 2, 26.67, ["lunch", "dinner"]),
        ("actually plan the whole week", 7, 140, ["breakfast", "lunch", "dinner"]),
    ]:
        state, _ = step(message, state)
        assert (state.day_count, state.weekly_budget_sgd, meals_of(state)) == (days, budget, meals), message
        assert state.base_weekly_budget_sgd == (140 if days < 7 or len(meals) < 3 else None), message
    # Back at the household's week: its shape, its budget, and a dump like a week that was never short.
    assert state.usual_plan_shape is None
    dumped = state.model_dump(mode="json")
    assert "day_count" not in dumped and "base_weekly_budget_sgd" not in dumped and "usual_plan_shape" not in dumped


@pytest.mark.full_default
@pytest.mark.parametrize(
    "message",
    [
        "Plan a week of dinners",
        "this week",
        "next week",
        "the whole week",
        "plan the full week from Monday",
        "一周",
        "下周",
    ],
)
def test_a_week_phrase_with_no_days_puts_the_plan_back_to_the_week(message: str) -> None:
    state, _ = step("dinner tomorrow for 2", AgentConstraintState(weekly_budget_sgd=100))
    assert state.day_count == 1 and state.weekly_budget_sgd == 4.76
    state, reply = step(message, state)
    assert (state.day_count, state.weekly_budget_sgd, len(meals_of(state))) == (7, 100, 3)
    assert ("The week runs" in reply or "这周从" in reply) and "day_count" not in state.model_dump(mode="json")


def test_a_week_in_a_budget_or_a_rule_is_not_a_week_to_plan() -> None:
    short, _ = step("dinner tomorrow for 2", AgentConstraintState())
    for message in ["S$100 a week", "chicken twice a week", "no soup this week", "每周预算100"]:
        assert step(message, short)[0].day_count == 1, message


@pytest.mark.full_default
def test_the_household_keeps_the_meals_it_composes_through_a_short_plan_and_back() -> None:
    soup = {"role_id": "soup", "courses": ["soup"]}
    main = {"role_id": "main", "courses": ["main"]}
    shape = {"meals": {"lunch": [main], "dinner": [main, soup]}}
    state, _ = step("dinner tomorrow", AgentConstraintState(plan_shape=shape))
    assert meals_of(state) == ["dinner"] and state.usual_plan_shape is not None
    state, _ = step("dinner only, this week", state)
    assert state.day_count == 7 and meals_of(state) == ["dinner"] and state.usual_plan_shape is not None
    state, _ = step("the whole week", state)
    assert meals_of(state) == ["lunch", "dinner"] and state.usual_plan_shape is None
    assert [role.role_id for role in state.plan_shape.meals["dinner"]] == ["main", "soup"]  # type: ignore[union-attr]


@pytest.mark.full_default
def test_the_next_days_start_where_a_plan_starts_not_where_the_last_one_began() -> None:
    state, _ = step("this weekend", AgentConstraintState(household_size=1))
    assert state.start_date == date(2026, 10, 17)
    state, _ = step("the next 3 days", state)
    assert (state.start_date, state.day_count) == (MONDAY, 3)


@pytest.mark.full_default
@pytest.mark.parametrize(
    ("message", "days", "weekly"),
    [
        # Said per week: the week's, shared out by the plan's meals (a dinner of the 21 meals a week of three has).
        ("dinners for two, S$100 a week, this weekend", 2, 9.52),
        ("S$100 a week for the weekend", 2, 28.57),  # all three meals of two days: 6 of 21
        ("两个人，每周预算100，周末两天", 2, 28.57),
        # Said per day with the days: that, times the days.
        ("S$10 a day for the next 3 days", 3, 30),
        ("S$10 per day for 3 days", 3, 30),
        ("dinners for 3 days, S$10 a day", 3, 30),
        # Said for the plan or the meal: the plan's, as before.
        ("S$30 for the next 3 days", 3, 30),
        ("S$20 for the weekend", 2, 20),
    ],
)
def test_a_budget_is_the_weeks_the_days_or_the_plans_by_how_the_message_says_it(message, days, weekly) -> None:
    state, _ = step(message, AgentConstraintState(household_size=2))
    assert (state.day_count, state.weekly_budget_sgd) == (days, weekly)


def test_an_amount_each_is_for_each_person_and_one_per_day_without_days_is_left_out() -> None:
    assert budgets("s$10 each for tomorrow's dinner", 2) == (None, 20)
    assert budgets("s$10 each for tomorrow's dinner", None) == (None, None)
    assert budgets("s$15 each dinner", 2) == (15, None)
    assert budgets("s$10 a day", 2) == (None, None)
    assert budgets("s$10 a day for the next 3 days", 2, 3) == (None, 30)
    assert read_budgets("s$100 a week", 2) == (None, 100, True)
    assert read_budgets("s$20 for the weekend", 2) == (None, 20, False)


@pytest.mark.full_default
def test_a_plan_amount_stays_until_the_days_change_then_the_saved_week_decides() -> None:
    state, _ = step("S$15 for tomorrow's dinner, 2 people", AgentConstraintState(weekly_budget_sgd=140))
    assert state.weekly_budget_sgd == 15 and state.base_weekly_budget_sgd == 140
    state, reply = step("make it the next 3 days", state)
    assert state.weekly_budget_sgd == 20 and "of your S$140 weekly budget" in reply


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_the_budget_choices_of_a_short_plan_are_sentences_the_rules_read(lang: str) -> None:
    from app.agent import limits
    from app.schemas.meal_plan import MealPlanShape

    dinner = MealPlanShape.model_validate({"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}})
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=5, day_count=1, plan_shape=dinner)
    refusal = limits._budget_short(20.5, constraints, lang, cheapest=lambda **_: 12.0)
    assert len(refusal.options) == 2
    # "Use S$21 for the plan", then "2 people, S$12 for the plan".
    chosen = [step(said, constraints)[0] for _, said in refusal.options]
    assert [(state.household_size, state.weekly_budget_sgd) for state in chosen] == [(4, 21), (2, 12)]


def test_a_role_no_allergen_safe_dish_fills_is_refused_not_a_crash() -> None:
    """An allergen with no other limit once raised a TypeError where the refusal names the limit."""
    from types import SimpleNamespace

    from app.agent import limits

    constraints = SimpleNamespace(
        budget_per_meal_sgd=None,
        max_cooking_time_minutes=None,
        dietary_preferences=[],
        max_sodium_mg_per_meal=None,
        allergens=["peanut"],
        excluded_ingredients=[],
        day_count=1,
    )
    refusal = limits._no_dish(constraints, lambda **_: None, None, "dinner", "main", "en")
    assert refusal.field == "allergens"
    assert "No main dish I can plan for dinner fits" in refusal.text and "can't make the plan yet" in refusal.text


def test_today_in_a_message_about_an_ingredient_or_how_one_feels_is_not_a_day_outside_the_plan(
    recipe_client, monday_noon
):
    session = chat(recipe_client, "Dinners for 2 people this weekend")  # Sat 17 to Sun 18 Oct; today is Mon 12
    planned(recipe_client, session)
    said = {}
    for message in (
        "Swap today's dinner",
        "I can't buy tofu today",
        "tofu is out of stock today",
        "swap the dinner, I'm tired today",
    ):
        answered = recipe_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
        assert answered.status_code == 200, answered.text
        said[message] = answered.json()["messages"][-1]["content"]
    assert said["Swap today's dinner"].startswith("That day is not in this plan")
    for message in list(said)[1:]:
        assert not said[message].startswith("That day is not in this plan"), message
