"""The first request shapes the week it sets up: "dinners with a soup" before any week is planned."""

import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.agent.workflow import AgentConstraintWorkflow
from app.schemas.agent import AgentConstraintState
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShape

DEMO = "We're two, one of us is allergic to peanuts, no pork, S$100 a week, dinners with a soup"


def setup(message: str, shape: MealPlanShape | None = None) -> tuple[AgentConstraintState, str]:
    state = AgentConstraintWorkflow(RuleBasedConstraintParser()).run(
        message, current=AgentConstraintState(plan_shape=shape), acknowledged_unknowns=[], history=[]
    )
    return AgentConstraintState.model_validate(state["merged_constraints"]), state["assistant_message"]


def roles(state: AgentConstraintState) -> dict[str, list[str]]:
    assert state.plan_shape is not None
    return {meal: [role.role_id for role in dishes] for meal, dishes in state.plan_shape.meals.items()}


def test_the_demo_request_gives_a_new_household_dinners_with_a_soup() -> None:
    state, reply = setup(DEMO)
    assert roles(state) == {"dinner": ["main", "vegetable", "soup"]}
    assert state.household_size == 2 and state.allergens == ["peanut"]
    assert "Dinner: main, vegetable and soup." in reply


def test_a_household_whose_dinners_have_a_soup_gets_no_second_one() -> None:
    soup = MealPlanShape.model_validate({"meals": {"dinner": MEAL_PRESETS["dinner"]["main, vegetable and soup"]}})
    state, reply = setup(DEMO, soup)
    assert roles(state) == {"dinner": ["main", "vegetable", "soup"]}
    assert "Dinner:" not in reply


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Plan lunch and dinner for three, S$120 a week", {"dinner": ["main", "vegetable"], "lunch": ["main"]}),
        ("Dinners for two, just one main", {"dinner": ["main"]}),
        ("两个人，一周100新币，晚餐加一个汤", {"dinner": ["main", "vegetable", "soup"]}),
    ],
)
def test_other_shapes_are_read_at_setup(message: str, expected: dict[str, list[str]]) -> None:
    state, _ = setup(message)
    assert roles(state) == expected


@pytest.mark.parametrize(
    "message",
    [
        "Dinners for two this week, around S$90",
        "Two of us, no pork, add a soup on Friday",
        "一共10新币给4个人做一周",
    ],
)
def test_requests_that_name_no_shape_or_name_days_keep_the_household_shape(message: str) -> None:
    state, _ = setup(message)
    assert state.plan_shape is None
