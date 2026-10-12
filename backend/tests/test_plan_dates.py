"""When the week starts: read from the request, else today or tomorrow (agent/plan_dates.py, 2026-10-12)."""

from datetime import date, datetime

import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.agent.plan_dates import default_start, read_start
from app.agent.workflow import AgentConstraintWorkflow
from app.core import clock
from app.schemas.agent import AgentConstraintState

MONDAY = date(2026, 10, 12)


@pytest.mark.parametrize(
    ("message", "start"),
    [
        ("Dinners for two next week", date(2026, 10, 19)),
        ("下周的晚饭，两个人", date(2026, 10, 19)),
        ("Plan dinners from tomorrow", date(2026, 10, 13)),
        ("明天开始排晚饭", date(2026, 10, 13)),
        ("Starting Wednesday, dinners for two", date(2026, 10, 14)),
        ("from Monday", MONDAY),  # the coming Monday is today
        ("from next Monday", date(2026, 10, 19)),
        ("Friday onwards please", date(2026, 10, 16)),
        ("从周三开始", date(2026, 10, 14)),
        ("下周一开始", date(2026, 10, 19)),
        ("Start on 2026-10-21", date(2026, 10, 21)),
        ("starting 19 Oct", date(2026, 10, 19)),
        ("from Oct 20th", date(2026, 10, 20)),
        ("10月19日开始", date(2026, 10, 19)),
        ("starting 5 Jan", date(2027, 1, 5)),  # a date well past is next year's
    ],
)
def test_the_start_a_request_names(message: str, start: date) -> None:
    said = read_start(message, MONDAY)
    assert said is not None and said.start == start


@pytest.mark.parametrize(
    "message",
    [
        "Dinners for two this week, around S$90",
        "no soup on Friday",  # a day without a start word is a meal change, not when the week starts
        "We're two, one of us is allergic to peanuts, no pork, S$100 a week, dinners with a soup",
        "一共10新币给4个人做一周",
        "I may 3 dishes",
    ],
)
def test_a_request_that_names_no_start(message: str) -> None:
    assert read_start(message, MONDAY) is None


def test_with_no_start_said_the_week_starts_tomorrow_once_today_s_last_meal_is_over() -> None:
    evening = datetime(2026, 10, 12, 20, 0, tzinfo=clock.SINGAPORE)
    late = datetime(2026, 10, 12, 21, 30, tzinfo=clock.SINGAPORE)
    assert default_start(evening, ["dinner"]) == MONDAY
    assert default_start(late, ["dinner"]) == date(2026, 10, 13)
    # A household that plans only breakfast is past it by mid-morning.
    assert default_start(datetime(2026, 10, 12, 11, 0, tzinfo=clock.SINGAPORE), ["breakfast"]) == date(2026, 10, 13)


def setup(message: str) -> tuple[AgentConstraintState, str]:
    state = AgentConstraintWorkflow(RuleBasedConstraintParser()).run(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    return AgentConstraintState.model_validate(state["merged_constraints"]), state["assistant_message"]


@pytest.fixture
def monday_noon(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 12, 12, 0, tzinfo=clock.SINGAPORE))
    monkeypatch.setattr(clock, "today", lambda: MONDAY)


def test_the_reply_names_the_week_a_request_starts_and_the_shape_still_reads(monday_noon) -> None:
    state, reply = setup("Dinners for two from next Monday, with a soup, S$100 a week")
    assert state.start_date == date(2026, 10, 19)
    assert "The week runs Mon 19 Oct – Sun 25 Oct." in reply
    assert state.plan_shape is not None and "soup" in [role.role_id for role in state.plan_shape.meals["dinner"]]


def test_a_request_with_no_start_gets_today_and_says_nothing_about_dates(monday_noon) -> None:
    state, reply = setup("Dinners for two, S$100 a week")
    assert state.start_date == MONDAY
    assert "week runs" not in reply


def test_a_named_day_already_past_starts_the_week_today(monday_noon) -> None:
    state, reply = setup("Dinners for two starting 2026-10-10")
    assert state.start_date == MONDAY
    assert "Sat 10 Oct has passed, so the week starts today." in reply


@pytest.mark.parametrize("message", ["from next Monday", "下周一开始", "Start the week on 2026-10-21"])
def test_a_message_that_only_moves_the_start_is_meal_planning(message: str) -> None:
    from app.orchestration.contracts import ScopeClass
    from app.orchestration.scope_policy import ReferenceScopePolicy

    assert ReferenceScopePolicy().classify(message).scope_class == ScopeClass.DOMAIN_ACTION
