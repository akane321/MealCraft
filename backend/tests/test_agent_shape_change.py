"""Shape changes read from the conversation (ADR-0046 section 2)."""

from types import SimpleNamespace

import pytest

from app.agent.shape_change import read_shape_change
from app.schemas.meal_plan import default_plan_shape

PLAN = SimpleNamespace(plan_shape=default_plan_shape(), days=[])  # dinner: main + vegetable


def roles(message, day=None):
    intent = read_shape_change(message, plan=PLAN, day_index=day)
    if intent is None:
        return None
    request = intent.request
    ids = None if request.roles is None else [role.role_id for role in request.roles]
    return request.meal_type, ids, request.day_indexes


@pytest.mark.parametrize(
    ("message", "day", "expected"),
    [
        ("Also plan lunch", None, ("lunch", ["main"], None)),
        ("也安排午餐", None, ("lunch", ["main"], None)),
        # Read even though breakfast is not planned; the preview then says so.
        ("no breakfast please", None, ("breakfast", None, None)),
        ("Dinners with a soup", None, ("dinner", ["main", "vegetable", "soup"], None)),
        ("add a soup on Friday", 5, ("dinner", ["main", "vegetable", "soup"], [5])),
        ("周五晚餐加个汤", 5, ("dinner", ["main", "vegetable", "soup"], [5])),
        ("no side dish tonight", 1, ("dinner", ["main"], [1])),
        ("今晚不要配菜", 1, ("dinner", ["main"], [1])),
        ("add another meat dish", None, ("dinner", ["main", "vegetable", "main-2"], None)),
        ("lunch just one dish", None, ("lunch", ["main"], None)),
        ("no dinner on Sunday", 7, ("dinner", None, [7])),
        # Not shape changes: a food, a swap, a skip.
        ("no pork for dinner", None, None),
        ("swap Friday's dinner for fish", 5, None),
        ("skip dinner tomorrow", 2, None),
    ],
)
def test_reads_the_shape_change_a_message_asks_for(message, day, expected):
    assert roles(message, day) == expected
