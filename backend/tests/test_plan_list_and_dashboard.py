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


def plan(plan_id: int, start: date, *, made: int):
    return SimpleNamespace(
        id=plan_id,
        revision=1,
        household_profile_id=None,
        household_profile_version=None,
        replaces_plan_id=None,
        start_date=start,
        end_date=start + timedelta(days=6),
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
        plan(3, date(2026, 10, 1), made=20),  # 1-7 Oct overlaps the newest week: replaced
        plan(2, date(2026, 9, 20), made=10),  # an earlier week nobody planned over: still its own
    ]
    listed = service(SimpleNamespace(list_recent=lambda limit: plans)).list_recent(limit=20)
    assert [(item.id, item.current) for item in listed.items] == [(5, True), (4, False), (3, False), (2, True)]


def entry(entry_id: int, day: int, meal: str):
    recipe = SimpleNamespace(
        id=entry_id, slug=f"r-{entry_id}", title=f"Dish {entry_id}", description="", cuisine="Home",
        meal_type=meal, servings=2, total_time_minutes=20, dietary_tags=[], nutrition=NUTRITION, course="main",
    )
    return SimpleNamespace(
        id=entry_id, day_index=day, planned_date=date(2026, 10, 3 + day), recipe=recipe, status="planned",
        is_locked=False, consumed_at=None, meal_type=meal, role_id="main", portion_share=1, **NUTRITION,
    )


def test_the_dashboard_lists_a_day_breakfast_lunch_then_dinner_whatever_order_the_dishes_were_added_in():
    # A dinner week, then lunch and breakfast added in the conversation: stored by day, then by id.
    week = SimpleNamespace(
        id=9, revision=3, start_date=date(2026, 10, 4), end_date=date(2026, 10, 10), household_size=2,
        constraints={},
        entries=[entry(1, 1, "dinner"), entry(8, 1, "lunch"), entry(9, 1, "breakfast"), entry(2, 2, "dinner"), entry(10, 2, "lunch")],
    )
    dashboard = service(SimpleNamespace(get=lambda plan_id: week)).dashboard(9)
    assert [(day.day_index, day.meal_type) for day in dashboard.days] == [
        (1, "breakfast"), (1, "lunch"), (1, "dinner"), (2, "lunch"), (2, "dinner"),
    ]
