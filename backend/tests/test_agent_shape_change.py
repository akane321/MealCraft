"""Shape changes read from the conversation (ADR-0046 section 2)."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.agent.replanning import AgentReplanInterpreter
from app.agent.shape_change import read_shape_change
from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShape, default_plan_shape

# The course of the dish each role holds in these weeks.
COURSES = {"main": "main", "vegetable": "side", "soup": "soup"}


def week(shape: MealPlanShape, **extra: list[str]) -> SimpleNamespace:
    """A week from Monday 2026-09-28 planned to `shape`; `extra` gives a day ("d5") other dishes."""
    dishes = [
        SimpleNamespace(
            day_index=n,
            planned_date=date(2026, 9, 28) + timedelta(days=n - 1),
            meal_type=meal,
            role_id=role_id,
            status="planned",
            recipe=SimpleNamespace(course=COURSES[role_id.split("-")[0]]),
        )
        for n in range(1, 8)
        for meal, roles in shape.meals.items()
        for role_id in extra.get(f"d{n}", [role.role_id for role in roles])
    ]
    return SimpleNamespace(plan_shape=shape, days=dishes)


PLAN = week(default_plan_shape())  # dinner: main + vegetable
WITH_SOUP = week(
    MealPlanShape.model_validate({"meals": {"dinner": MEAL_PRESETS["dinner"]["main, vegetable and soup"]}})
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


# Friday got a soup from an earlier one-day change; the week's shape is still main + vegetable.
FRIDAY_SOUP = week(default_plan_shape(), d5=["main", "vegetable", "soup"])


@pytest.mark.parametrize(
    ("message", "plan", "expected"),
    [
        # Another soup beside the one Friday has, so the change is an addition that keeps Friday's dishes.
        ("周五晚餐加一个汤", FRIDAY_SOUP, ("dinner", ["main", "vegetable", "soup", "soup-2"], [5])),
        ("add another soup on Friday", FRIDAY_SOUP, ("dinner", ["main", "vegetable", "soup", "soup-2"], [5])),
        # Friday's soup can be taken off again.
        ("no soup on Friday", FRIDAY_SOUP, ("dinner", ["main", "vegetable"], [5])),
        # Days that differ (Friday has a soup, Saturday not) are read against the week's shape.
        ("add a soup on Friday and Saturday", FRIDAY_SOUP, ("dinner", ["main", "vegetable", "soup"], [5, 6])),
    ],
)
def test_a_named_day_is_read_with_the_dishes_it_has(message, plan, expected):
    assert roles(message, plan=plan) == expected


def test_a_skipped_dish_is_not_one_the_day_has():
    plan = week(default_plan_shape(), d5=["main", "vegetable", "soup"])
    next(d for d in plan.days if d.day_index == 5 and d.role_id == "soup").status = "skipped"
    assert roles("add a soup on Friday", plan=plan) == ("dinner", ["main", "vegetable", "soup"], [5])
    # The vegetable keeps the week's setting (optional), the new soup is asked for.
    assert [r.required for r in intent("add another soup on Friday", plan=FRIDAY_SOUP).request.roles] == [
        True,
        False,
        True,
        True,
    ]


def lunch_on_friday(shape: MealPlanShape, course: str) -> SimpleNamespace:
    """`shape`'s week with Friday's lunch one dish of `course`, planned for Friday alone."""
    plan = week(shape)
    plan.days = [d for d in plan.days if (d.day_index, d.meal_type) != (5, "lunch")]
    friday = next(d.planned_date for d in plan.days if d.day_index == 5)
    lunch = SimpleNamespace(course=course)
    plan.days.append(
        SimpleNamespace(
            day_index=5, planned_date=friday, meal_type="lunch", role_id="main", status="planned", recipe=lunch
        )
    )
    return plan


MAIN_AND_SIDE_LUNCHES = MealPlanShape.model_validate(
    {"meals": {"lunch": MEAL_PRESETS["lunch"]["main and vegetable"], "dinner": MEAL_PRESETS["dinner"]["main and vegetable"]}}
)


@pytest.mark.parametrize(
    ("plan", "main"),
    [
        # A lunch the week lacks, added for Friday with lunch's first preset ("one dish"): its main takes a main,
        # a salad or a soup. Read from every preset at once, the last one's main (a main only) was taken.
        (lunch_on_friday(default_plan_shape(), "main"), ["main", "salad", "soup"]),
        # Friday's lunch made one dish on a week of main-and-side lunches, and a salad came: its main holds it.
        (lunch_on_friday(MAIN_AND_SIDE_LUNCHES, "salad"), ["main", "salad"]),
    ],
)
def test_a_meal_is_read_with_the_roles_its_dishes_have(plan, main):
    request = intent("周五午餐加一个汤", plan=plan).request
    assert (request.meal_type, request.day_indexes) == ("lunch", [5])
    assert [(role.role_id, role.courses) for role in request.roles] == [("main", main), ("soup", ["soup"])]


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


# Weekday-only requests stay on weekdays (held-out run 2's diagnostics): every way of naming
# Monday to Friday, the meal before or after the days, adding or dropping.
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("no lunch on weekdays", ("lunch", None, WEEKDAYS)),
        ("lunch off during the week", ("lunch", None, WEEKDAYS)),
        ("weekdays only: no lunch", ("lunch", None, WEEKDAYS)),
        ("weekday lunches off", ("lunch", None, WEEKDAYS)),
        ("remove weekday lunches", ("lunch", None, WEEKDAYS)),
        ("Monday to Friday no lunch", ("lunch", None, WEEKDAYS)),
        ("no lunch from Monday through Friday", ("lunch", None, WEEKDAYS)),
        ("lunch not needed Mon-Fri", ("lunch", None, WEEKDAYS)),
        ("no lunch on workdays", ("lunch", None, WEEKDAYS)),
        ("no lunch on working days", ("lunch", None, WEEKDAYS)),
        ("no dinner on weeknights", ("dinner", None, WEEKDAYS)),
        ("no lunch except on weekends", ("lunch", None, WEEKDAYS)),
        ("add lunch on weekdays", ("lunch", ["main"], WEEKDAYS)),
        ("add soups to weekday dinners", ("dinner", ["main", "vegetable", "soup"], WEEKDAYS)),
        ("工作日不用做午饭", ("lunch", None, WEEKDAYS)),
        ("午饭工作日不用做", ("lunch", None, WEEKDAYS)),
        ("平日不需要午饭", ("lunch", None, WEEKDAYS)),
        ("上班日午饭免了", ("lunch", None, WEEKDAYS)),
        ("周一至周五不要午饭", ("lunch", None, WEEKDAYS)),
        ("星期一到星期五不要午餐", ("lunch", None, WEEKDAYS)),
        ("周一到五不做午饭", ("lunch", None, WEEKDAYS)),
        ("礼拜一至五午饭不要了", ("lunch", None, WEEKDAYS)),
        ("除了周末都不要午饭", ("lunch", None, WEEKDAYS)),
        ("工作日加上午饭", ("lunch", ["main"], WEEKDAYS)),
        ("平日晚饭加个汤", ("dinner", ["main", "vegetable", "soup"], WEEKDAYS)),
        # The weekend named only to say it stays as it is.
        ("no lunch on weekdays, weekends as usual", ("lunch", None, WEEKDAYS)),
        ("weekday lunches off; keep lunch on the weekend", ("lunch", None, WEEKDAYS)),
        ("no lunch Monday to Friday but keep Saturday and Sunday", ("lunch", None, WEEKDAYS)),
        (
            "weekends stay the same, but add a soup to weekday dinners",
            ("dinner", ["main", "vegetable", "soup"], WEEKDAYS),
        ),
        ("工作日不用做午饭，周末照常", ("lunch", None, WEEKDAYS)),
        ("周末照旧，周一到周五午饭不用做", ("lunch", None, WEEKDAYS)),
        # Weekends and single days still read as before.
        ("no weekend breakfasts", ("breakfast", None, [6, 7])),
        ("双休日不要早餐", ("breakfast", None, [6, 7])),
        ("no lunch during the weekend", ("lunch", None, [6, 7])),
        ("no dinner on Sunday", ("dinner", None, [7])),
        ("周六到周日不要午饭", ("lunch", None, [6, 7])),
        ("except Friday, add a soup to dinner", ("dinner", ["main", "vegetable", "soup"], [1, 2, 3, 4, 6, 7])),
    ],
)
def test_weekday_requests_stay_on_weekdays(message, expected):
    assert roles(message) == expected


# "The rest stays" is not a lock when another clause adds or drops a meal; a lock on its own still is.
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("工作日不要午饭，周末的午饭保留", ("lunch", None, WEEKDAYS)),
        ("工作日不用做午饭，周末保持不变", ("lunch", None, WEEKDAYS)),
        ("周末不要改，工作日不要午饭", ("lunch", None, WEEKDAYS)),
        ("no lunch on weekdays, keep the weekend lunches", ("lunch", None, WEEKDAYS)),
        ("no lunch on weekdays, don't change the weekend", ("lunch", None, WEEKDAYS)),
        ("add a soup to weekend dinners; weekdays keep unchanged", ("dinner", ["main", "vegetable", "soup"], [6, 7])),
    ],
)
def test_the_rest_staying_is_not_a_lock(message, expected):
    assert AgentReplanInterpreter._event_type(message.lower()) is None
    assert roles(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "保留周三的晚饭",
        "周三的晚饭保留，其他的换掉",
        "锁定周五的午饭",
        "keep Tuesday's dinner",
        "keep the lunch on Friday as it is",
        "don't change sunday",
        "lock Monday to Friday",
        # A lock of its own beside a shape change stays a lock.
        "lock Wednesday's dinner, and add a soup on weekdays",
    ],
)
def test_a_lock_is_still_a_lock(message):
    assert AgentReplanInterpreter._event_type(message.lower()) == "LOCK_MEAL"
