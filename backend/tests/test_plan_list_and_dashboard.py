"""The plans list marks replaced weeks, and the dashboard lists dishes in the order they are eaten."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.services.meal_plan import WeeklyMealPlanService

NUTRITION = {"calories_kcal": 400, "protein_g": 20, "carbohydrate_g": 50, "fat_g": 10, "sodium_mg": 500, "sugar_g": 5}


def service(repository) -> WeeklyMealPlanService:
    return WeeklyMealPlanService(
        repository=repository,
        recipe_repository=None,
        recommendation_service=None,
        grocery_aggregator=None,
        selector=object(),
        planning_engine=object(),
    )


def plan(plan_id: int, start: date, *, made: int, days: int = 7, meals: tuple[str, ...] | None = None):
    # The meals it plans, as the repository's rows hold them; none named is a dinner plan.
    shape = {"plan_shape": {"meals": {meal: [{"role_id": "main", "courses": ["main"]}] for meal in meals or ()}}}
    return SimpleNamespace(
        id=plan_id,
        revision=1,
        household_profile_id=None,
        household_profile_version=None,
        replaces_plan_id=None,
        start_date=start,
        end_date=start + timedelta(days=days - 1),
        day_count=days,
        constraints=shape if meals else {},
        household_size=2,
        purchase_total_sgd=50,
        consumed_total_sgd=None,
        within_weekly_budget=True,
        created_at=datetime(2026, 10, 4, tzinfo=UTC) + timedelta(minutes=made),
    )


def test_only_the_newest_plan_for_some_dates_is_current():
    # Newest first, as the repository lists them.
    plans = [
        plan(5, date(2026, 10, 4), made=40),
        plan(4, date(2026, 10, 4), made=30),  # the same week planned again: replaced
        plan(3, date(2026, 10, 1), made=20),  # 1-7 Oct: 1-3 Oct are planned by no newer plan, so it stays current
        plan(2, date(2026, 9, 20), made=10),  # an earlier week nobody planned over: still its own
    ]
    listed = service(SimpleNamespace(list_recent=lambda limit: plans)).list_recent(limit=20)
    assert [(item.id, item.current) for item in listed.items] == [(5, True), (4, False), (3, True), (2, True)]


def listed(*plans):
    return service(SimpleNamespace(list_recent=lambda limit: list(plans))).list_recent(limit=20).items


def test_a_dinner_planned_again_inside_a_week_leaves_the_week_current():
    # 2026-10-04 is a Sunday: the week runs to the 10th, the dinner is for the 6th.
    dinner = plan(6, date(2026, 10, 6), made=50, days=1, meals=("dinner",))
    week = plan(5, date(2026, 10, 4), made=40)
    items = listed(dinner, week)
    assert [(item.id, item.day_count, item.current) for item in items] == [(6, 1, True), (5, 7, True)]


def test_a_week_is_replaced_only_when_newer_plans_together_hold_every_meal_of_it():
    week = plan(5, date(2026, 10, 4), made=40, meals=("lunch", "dinner"))
    first = plan(6, date(2026, 10, 4), made=50, days=4, meals=("lunch", "dinner"))
    second = plan(7, date(2026, 10, 8), made=60, days=3, meals=("lunch", "dinner"))
    # Four days of lunch and dinner leave three days of the week uncovered: the week is still current.
    assert [item.current for item in listed(first, week)] == [True, True]
    # Together they hold every day, so the week is replaced.
    assert [item.current for item in listed(second, first, week)] == [True, True, False]
    # A newer plan of dinners alone holds only half the places of a lunch and dinner week.
    dinners = plan(8, date(2026, 10, 4), made=70, meals=("dinner",))
    assert [item.current for item in listed(dinners, week)] == [True, True]


def entry(entry_id: int, day: int, meal: str):
    recipe = SimpleNamespace(
        id=entry_id,
        slug=f"r-{entry_id}",
        title=f"Dish {entry_id}",
        description="",
        cuisine="Home",
        meal_type=meal,
        servings=2,
        total_time_minutes=20,
        dietary_tags=[],
        nutrition=NUTRITION,
        course="main",
    )
    return SimpleNamespace(
        id=entry_id,
        day_index=day,
        planned_date=date(2026, 10, 3 + day),
        recipe=recipe,
        status="planned",
        is_locked=False,
        consumed_at=None,
        meal_type=meal,
        role_id="main",
        portion_share=1,
        # What the reason tags read (layer 08 section 7.2).
        recipe_id=entry_id,
        servings=None,
        consumed_cost_sgd=0,
        **NUTRITION,
    )


def test_the_dashboard_lists_a_day_breakfast_lunch_then_dinner_whatever_order_the_dishes_were_added_in():
    # A dinner week, then lunch and breakfast added in the conversation: stored by day, then by id.
    week = SimpleNamespace(
        id=9,
        revision=3,
        start_date=date(2026, 10, 4),
        end_date=date(2026, 10, 10),
        day_count=7,
        household_size=2,
        constraints={},
        entries=[
            entry(1, 1, "dinner"),
            entry(8, 1, "lunch"),
            entry(9, 1, "breakfast"),
            entry(2, 2, "dinner"),
            entry(10, 2, "lunch"),
        ],
    )
    # A household with no feedback (ADR-0087): the stub session holds no rows.
    repository = SimpleNamespace(
        get=lambda plan_id: week, session=SimpleNamespace(scalars=lambda _: []), household_id=1
    )
    dashboard = service(repository).dashboard(9)
    assert [(day.day_index, day.meal_type) for day in dashboard.days] == [
        (1, "breakfast"),
        (1, "lunch"),
        (1, "dinner"),
        (2, "lunch"),
        (2, "dinner"),
    ]
    assert dashboard.day_count == 7
