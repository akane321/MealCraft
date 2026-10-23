"""Reason tags (layer 08 section 7.2, ADR-0087): each tag only when its fact holds, at most two, read from the week."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.clock import today as local_today
from app.planning.dish_reasons import cost_per_serving, dish_reasons
from tests.test_planning_capability import COMPOSITION, _dish, composed_client, dish_client  # noqa: F401
from tests.test_recipe_feedback import _ids

ENGINE_WORDING = ("limit", "scored", "rank", "benchmark", "chosen")


def entry(
    entry_id,
    recipe_id=None,
    *,
    role="main",
    meal="dinner",
    cost=10.0,
    servings=None,
    share=1.0,
    minutes=30,
    sodium=300.0,
    sugar=2.0,
    kcal=400.0,
    status="planned",
):
    recipe = SimpleNamespace(
        total_time_minutes=minutes,
        nutrition=SimpleNamespace(sodium_mg=sodium, sugar_g=sugar, calories_kcal=kcal),
    )
    return SimpleNamespace(
        id=entry_id,
        recipe_id=recipe_id if recipe_id is not None else entry_id,
        role_id=role,
        meal_type=meal,
        consumed_cost_sgd=cost,
        servings=servings,
        portion_share=share,
        status=status,
        recipe=recipe,
    )


def codes(entries, *, household_size=2, preferences=()):
    tags = dish_reasons(entries, household_size=household_size, health_preferences=preferences)
    return {key: [tag.code for tag in value] for key, value in tags.items()}


# --- Each rule and its boundary ---


def test_quick_is_twenty_minutes_or_less():
    tags = dish_reasons([entry(1, minutes=20), entry(2, minutes=21)], household_size=2, health_preferences=[])
    assert [tag.label for tag in tags[1]] == ["Ready in 20 min"]
    assert 2 not in tags


def test_cheapest_main_needs_four_different_mains():
    three = [entry(1, cost=2), entry(2, cost=10), entry(3, cost=12)]
    assert codes(three) == {}
    # The same dish twice is one main, not two.
    assert codes([*three, entry(4, recipe_id=3, cost=12)]) == {}
    four = [*three, entry(4, cost=14)]
    assert codes(four) == {1: ["cheap_main"]}
    # A skipped (cancelled) main is not cooked, so it neither counts toward the four nor gets the tag.
    assert codes([*three, entry(4, cost=14, status="skipped")]) == {}
    assert codes([entry(1, cost=2, status="skipped"), *four[1:], entry(5, cost=16)]) == {2: ["cheap_main"]}


def test_cheapest_main_is_the_cheapest_quarter_per_serving_and_ties_count_against_it():
    eight = [entry(i, cost=float(i)) for i in range(1, 9)]
    assert codes(eight) == {1: ["cheap_main"], 2: ["cheap_main"]}  # 25% of 8: the 3rd is out
    assert codes([entry(i, cost=5.0) for i in range(1, 5)]) == {}  # equal prices set nobody apart
    # Cost per serving, not per dish: 12 for 6 servings is cheaper than 4 for 1.
    per_serving = [entry(1, cost=12, servings=6), entry(2, cost=4, servings=1), entry(3, cost=8), entry(4, cost=9)]
    assert codes(per_serving) == {1: ["cheap_main"]}
    # A dish saved with no grocery estimate (0) has no price, so it is neither counted nor tagged.
    assert codes([entry(1, cost=0), *(entry(i, cost=float(i)) for i in range(2, 5))]) == {}


def test_cost_per_serving_uses_household_size_times_portion_share_when_servings_is_null():
    assert cost_per_serving(entry(1, cost=6.0, share=0.6), 5) == 2.0  # 6 / (5 x 0.6)
    assert cost_per_serving(entry(1, cost=6.0, servings=2, share=0.6), 5) == 3.0
    assert cost_per_serving(entry(1, cost=0), 2) is None


def test_breakfast_is_never_a_main():
    breakfast = entry(1, role="main", meal="breakfast", cost=0.5, sodium=100)
    mains = [entry(i, cost=float(i)) for i in range(2, 6)]
    tags = codes([breakfast, *mains], preferences=["low-sodium"])
    assert 1 not in tags  # no preference tag, and not counted among the cheapest
    assert tags[2] == ["preference", "cheap_main"]


def test_main_2_is_a_main_and_sides_never_get_a_preference_tag():
    week = [
        entry(1, role="main-2", meal="lunch"),
        entry(2, role="vegetable"),
        entry(3, role="staple"),
        entry(4, role="soup"),
    ]
    assert codes(week, preferences=["low-sodium"]) == {1: ["preference"]}


def test_a_preference_uses_the_score_s_own_benchmark():
    tags = dish_reasons(
        [entry(1, sodium=700), entry(2, sodium=701), entry(3, sodium=100, sugar=12, kcal=601)],
        household_size=2,
        health_preferences=["low-sodium", "low-sugar", "lower-calorie"],
    )
    assert [tag.label for tag in tags[1]] == ["Fits low-sodium, low-sugar, lower-calorie"]
    assert [tag.label for tag in tags[3]] == ["Fits low-sodium, low-sugar"]
    assert [tag.label for tag in tags[2]] == ["Fits low-sugar, lower-calorie"]  # 701 mg is over


def test_at_most_two_tags_and_none_when_nothing_holds():
    week = [entry(1, cost=1, minutes=15), *(entry(i, cost=float(i) * 5) for i in range(2, 6))]
    assert codes(week, preferences=["low-sodium"])[1] == ["preference", "cheap_main"]  # quick is the third
    assert codes([entry(1, sodium=900)], preferences=["low-sodium"]) == {}
    assert codes([entry(1)]) == {}


# --- The dashboard reads them from the saved week ---

QUICK = "quick-noodles"
SLOW = ["tofu-bowl", "chickpea-stew", "salmon-bake", "chicken-roast"]


@pytest.fixture
def client(monkeypatch):
    ingredients = ["firm_tofu", "chickpea", "salmon_fillet", "chicken_breast"]
    dishes = [_dish(slug, "main", item, 100, calories=400) for slug, item in zip(SLOW, ingredients, strict=True)]
    dishes.append(_dish(QUICK, "main", "egg", 100, calories=400, prep=5, cook=10))
    with dish_client(monkeypatch, dishes) as client:
        yield client


def _dashboard(client, plan_id):
    response = client.get(f"/api/plans/{plan_id}/dashboard")
    assert response.status_code == 200, response.text
    return {day["entry_id"]: day for day in response.json()["days"]}


def test_the_dashboard_carries_each_dish_s_tags_and_cost_per_serving(client):
    plan = client.post(
        "/api/plans/generate",
        json={"household_size": 2, "pricing_mode": "fixture", "health_preferences": ["low-sodium"]},
    )
    assert plan.status_code == 201, plan.text
    days = _dashboard(client, plan.json()["id"]).values()
    costs = {day["recipe"]["id"]: day["cost_per_serving_sgd"] for day in days}
    assert all(cost and cost > 0 for cost in costs.values())
    for day in days:
        # Every dish is a 300 mg main; the cheapest-mains tag follows the prices the dashboard itself shows.
        rank = sum(cost <= day["cost_per_serving_sgd"] for cost in costs.values())
        cheap = len(costs) >= 4 and rank <= len(costs) // 4
        expected = [
            "preference",
            *(["cheap_main"] if cheap else []),
            *(["quick"] if day["recipe"]["slug"] == QUICK else []),
        ]
        assert [tag["code"] for tag in day["reasons"]] == expected[:2]
        assert not any(word in tag["label"].lower() for tag in day["reasons"] for word in ENGINE_WORDING)


def test_a_confirmed_swap_shows_the_new_dish_s_tags(client):
    plan = client.post("/api/plans/generate", json={"household_size": 2, "pricing_mode": "fixture"}).json()
    entry_ = next(day for day in plan["days"] if day["recipe"]["slug"] != QUICK)
    assert "quick" not in {tag["code"] for tag in _dashboard(client, plan["id"])[entry_["entry_id"]]["reasons"]}
    # Every other slow dish is Never again, so the swap can only bring the quick one.
    for slug in SLOW:
        if slug != entry_["recipe"]["slug"]:
            client.put(f"/api/feedback/recipes/{_ids()[slug]}", json={"kind": "never_again"})
    preview = client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"entry_id": entry_["entry_id"], "event_type": "REPLACE_MEAL"},
    )
    assert preview.status_code == 201, preview.text
    assert preview.json()["after_entry"]["recipe_slug"] == QUICK
    confirmed = client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    swapped = _dashboard(client, plan["id"])[entry_["entry_id"]]
    assert swapped["recipe"]["slug"] == QUICK
    assert {"code": "quick", "label": "Ready in 15 min"} in swapped["reasons"]


def test_a_meal_change_tags_the_new_dishes_by_their_roles(composed_client):  # noqa: F811
    start = (local_today() + timedelta(days=1)).isoformat()
    plan = composed_client.post(
        "/api/plans/generate",
        json={
            "start_date": start,
            "household_size": 4,
            "max_cooking_time_minutes": 90,
            "pricing_mode": "fixture",
            "health_preferences": ["low-sodium"],
            "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
        },
    )
    assert plan.status_code == 201, plan.text
    preview = composed_client.post(
        f"/api/plans/{plan.json()['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [5]},
    )
    assert preview.status_code == 201, preview.text
    confirmed = composed_client.post(f"/api/plans/{plan.json()['id']}/replan/{preview.json()['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    friday = [day for day in _dashboard(composed_client, plan.json()["id"]).values() if day["day_index"] == 5]
    assert {day["role_id"] for day in friday} == {"main", "vegetable", "soup"}
    for day in friday:
        preference = "preference" in {tag["code"] for tag in day["reasons"]}
        assert preference == (day["role_id"] == "main")  # sides and soups never get it, all are 300 mg
        assert day["cost_per_serving_sgd"] and day["cost_per_serving_sgd"] > 0
