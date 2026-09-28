"""Shape changes read from the conversation (ADR-0046 section 2)."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.agent.replanning import AgentReplanInterpreter
from app.agent.shape_change import read_shape_change
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShape, default_plan_shape

# A week from Monday 2026-09-28.
DAYS = [SimpleNamespace(day_index=n, planned_date=date(2026, 9, 28) + timedelta(days=n - 1)) for n in range(1, 8)]
PLAN = SimpleNamespace(plan_shape=default_plan_shape(), days=DAYS)  # dinner: main + vegetable
WITH_SOUP = SimpleNamespace(
    plan_shape=MealPlanShape.model_validate({"meals": {"dinner": MEAL_PRESETS["dinner"]["main, vegetable and soup"]}}),
    days=DAYS,
)
WEEKDAYS = [1, 2, 3, 4, 5]


def intent(message, days=None, plan=PLAN):
    """What the product reads: the days from the interpreter (unless given), then the shape change."""
    days = days or AgentReplanInterpreter().day_indexes(message.lower(), plan)
    return read_shape_change(message, plan=plan, day_indexes=days)


def roles(message, days=None, plan=PLAN):
    read = intent(message, days, plan)
    if read is None:
        return None
    request = read.request
    ids = None if request.roles is None else [role.role_id for role in request.roles]
    return request.meal_type, ids, request.day_indexes


@pytest.mark.parametrize(
    ("message", "days", "expected"),
    [
        ("Also plan lunch", None, ("lunch", ["main"], None)),
        ("也安排午餐", None, ("lunch", ["main"], None)),
        # Read even though breakfast is not planned; the preview then says so.
        ("no breakfast please", None, ("breakfast", None, None)),
        ("Dinners with a soup", None, ("dinner", ["main", "vegetable", "soup"], None)),
        ("add a soup on Friday", None, ("dinner", ["main", "vegetable", "soup"], [5])),
        ("周五晚餐加个汤", None, ("dinner", ["main", "vegetable", "soup"], [5])),
        ("no side dish tonight", [1], ("dinner", ["main"], [1])),
        ("今晚不要配菜", [1], ("dinner", ["main"], [1])),
        ("add another meat dish", None, ("dinner", ["main", "vegetable", "main-2"], None)),
        ("lunch just one dish", None, ("lunch", ["main"], None)),
        ("no dinner on Sunday", None, ("dinner", None, [7])),
        # Several days: weekends, weekdays, a range, a list; every day is the whole week.
        ("add a soup on weekends", None, ("dinner", ["main", "vegetable", "soup"], [6, 7])),
        ("周末晚餐加个汤", None, ("dinner", ["main", "vegetable", "soup"], [6, 7])),
        ("no breakfast on weekdays", None, ("breakfast", None, WEEKDAYS)),
        ("工作日不要早餐", None, ("breakfast", None, WEEKDAYS)),
        ("周一到周五不要早餐", None, ("breakfast", None, WEEKDAYS)),
        ("take lunch off Monday to Friday", None, ("lunch", None, WEEKDAYS)),
        ("dinners with a soup on Wednesday and Friday", None, ("dinner", ["main", "vegetable", "soup"], [3, 5])),
        ("周三和周五晚饭加个汤", None, ("dinner", ["main", "vegetable", "soup"], [3, 5])),
        ("周三、周五不要配菜", None, ("dinner", ["main"], [3, 5])),
        ("dinners with a soup every day", None, ("dinner", ["main", "vegetable", "soup"], None)),
        ("整周不要早餐", None, ("breakfast", None, None)),
        ("每天晚餐加个汤", None, ("dinner", ["main", "vegetable", "soup"], None)),
        # The verb after the meal or dish, and verbs beyond "add" and "no".
        ("周日的早餐不用排了", None, ("breakfast", None, [7])),
        ("早饭就不做了", None, ("breakfast", None, None)),
        ("午饭也帮我们安排上", None, ("lunch", ["main"], None)),
        ("午饭也排上吧", None, ("lunch", ["main"], None)),
        ("以后午饭就煮一道就好", None, ("lunch", ["main"], None)),
        ("晚饭的配菜去掉", None, ("dinner", ["main"], None)),
        ("汤加上", None, ("dinner", ["main", "vegetable", "soup"], None)),
        ("We won't need dinner on Saturday, please take it off", None, ("dinner", None, [6])),
        # Just one dish of a kind.
        ("周五晚饭只做一道主菜就行", None, ("dinner", ["main"], [5])),
        ("lunch can be just a main", None, ("lunch", ["main"], None)),
        ("just one main at dinner on Friday", None, ("dinner", ["main"], [5])),
        # Not shape changes: a food, a swap, a skip, company, a lock.
        ("no pork for dinner", None, None),
        ("no pork on weekends", None, None),
        ("swap Friday's dinner for fish", None, None),
        ("swap the weekend dinners for fish", None, None),
        ("skip dinner tomorrow", [2], None),
        ("lunch with the kids on Saturday", None, None),
        ("lock Monday to Friday", None, None),
    ],
)
def test_reads_the_shape_change_a_message_asks_for(message, days, expected):
    assert roles(message, days) == expected


@pytest.mark.parametrize(
    "message", ["这周晚饭的汤就不用煮了", "汤都免了吧", "别做汤了", "leave the soup out", "remove the soup from dinner"]
)
def test_takes_the_soup_out_of_a_dinner_that_has_one(message):
    assert roles(message, plan=WITH_SOUP) == ("dinner", ["main", "vegetable"], None)
    assert roles(message) is None  # no soup to take out


def test_just_one_main_is_one_main_not_the_meals_one_dish_preset():
    assert intent("lunch can be just a main").request.roles[0].courses == ["main"]
    assert intent("lunch just one dish").request.roles[0].courses == ["main", "salad", "soup"]


@pytest.mark.parametrize(
    ("message", "summary"),
    [
        ("add a soup on weekends", "Dinner with a soup on Saturday and Sunday"),
        ("take lunch off Monday to Friday", "No lunch on weekdays"),
        ("周三、周五不要配菜", "Dinner without the vegetable on Wednesday and Friday"),
        ("周五晚饭只做一道主菜就行", "Dinner as one main on Friday"),
        ("午饭也帮我们安排上", "Lunch added for the rest of this week"),
        ("以后午饭就煮一道就好", "Lunch as one dish for the rest of this week"),
    ],
)
def test_says_what_it_understood_and_when(message, summary):
    assert intent(message).summary == summary
