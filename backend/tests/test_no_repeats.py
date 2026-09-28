"""A household that asks for no repeats gets it as a hard rule: request, search, validator and conversation."""

from collections import Counter

import pytest

from app.planning.final_scope_validator import FinalPlanningValidator
from app.schemas.planning_v2 import PlanningAssignment
from tests.test_planning_capability import COMPOSITION, _dish, composed_client, dish_client  # noqa: F401
from tests.test_planning_meal_composition import failed, three_days, validate
from tests.test_recipes import recipe_client  # noqa: F401

WEEK = {
    "start_date": "2026-09-28",
    "household_size": 4,
    "max_cooking_time_minutes": 90,
    "pricing_mode": "fixture",
    "plan_shape": {"meals": {"dinner": COMPOSITION[:2]}},
}


@pytest.fixture
def varied_client(monkeypatch):
    """Seven mains and seven vegetables: enough for a week where no dish comes back."""
    mains = [
        ("salmon-bake", "salmon_fillet"),
        ("chicken-roast", "chicken_breast"),
        ("tofu-stirfry", "firm_tofu"),
        ("tuna-pasta", "canned_tuna"),
        ("chickpea-curry", "chickpea"),
        ("lentil-stew", "red_lentil"),
        ("bean-chili", "black_bean"),
    ]
    sides = [
        ("broccoli-stirfry", "broccoli"),
        ("spinach-saute", "baby_spinach"),
        ("mushroom-saute", "mushroom"),
        ("sweet-potato-mash", "sweet_potato"),
        ("zucchini-salad", "zucchini"),
        ("tomato-salad", "cherry_tomato"),
        ("cucumber-salad", "cucumber"),
    ]
    dishes = [_dish(slug, "main", ingredient, 400, calories=450) for slug, ingredient in mains]
    dishes += [
        _dish(slug, "salad" if slug.endswith("salad") else "side", ingredient, 300, calories=90)
        for slug, ingredient in sides
    ]
    with dish_client(monkeypatch, dishes) as client:
        yield client


def test_the_validator_fails_a_week_that_serves_a_dish_more_often_than_allowed():
    mains, vegetables = ("chicken", "beef", "chicken"), ("greens", "beans", "greens")
    twice = [
        PlanningAssignment(slot_id=f"d{i}", role_id=role, recipe_id=recipe_id)
        for i in range(3)
        for role, recipe_id in (("main", mains[i]), ("vegetable", vegetables[i]))
    ]

    report, _ = validate(three_days(repetition_rules={"max_uses_per_recipe": 1}), twice)
    assert "repetition_rule" in failed(report)
    assert {c.detail for c in report.checks if c.code == "repetition_rule"} == {
        "chicken used 2 times, the household allows 1",
        "greens used 2 times, the household allows 1",
    }

    allowed, _ = validate(three_days(repetition_rules={"max_uses_per_recipe": 2}), twice)
    assert "repetition_rule" not in failed(allowed)


def test_a_stated_cap_reaches_the_problem_as_its_repetition_rule(composed_client, monkeypatch):  # noqa: F811
    seen = []
    original = FinalPlanningValidator.validate

    def spy(self, problem, assignments, shopping):
        seen.append(problem.repetition_rules)
        return original(self, problem, assignments, shopping)

    monkeypatch.setattr(FinalPlanningValidator, "validate", spy)

    response = composed_client.post("/api/plans/generate", json={**WEEK, "max_uses_per_recipe": 4})
    assert response.status_code == 201, response.text
    assert seen[0].max_uses_per_recipe == 4 and seen[0].recipe_counts == []
    assert max(Counter(d["recipe"]["slug"] for d in response.json()["days"]).values()) <= 4

    seen.clear()
    assert composed_client.post("/api/plans/generate", json=WEEK).status_code == 201
    assert seen[0] is None  # nothing stated: repeating stays a soft cost
    assert composed_client.post("/api/plans/generate", json={**WEEK, "max_uses_per_recipe": 0}).status_code == 422


def test_no_dish_twice_forces_a_week_of_distinct_dishes(varied_client):
    response = varied_client.post("/api/plans/generate", json={**WEEK, "max_uses_per_recipe": 1})

    assert response.status_code == 201, response.text
    slugs = [d["recipe"]["slug"] for d in response.json()["days"]]
    assert len(slugs) == 14 and len(set(slugs)) == 14


def test_no_dish_twice_is_refused_when_two_mains_cannot_fill_seven_dinners(composed_client):  # noqa: F811
    response = composed_client.post("/api/plans/generate", json={**WEEK, "max_uses_per_recipe": 1})

    assert response.status_code == 422, response.text
    assert "every limit" in response.json()["detail"]


def test_a_one_dish_week_holds_the_cap_too(recipe_client):  # noqa: F811
    request = {"start_date": "2026-09-28", "household_size": 2, "pricing_mode": "fixture"}

    # Two recipes fill seven dinners only as four and three.
    assert recipe_client.post("/api/plans/generate", json={**request, "max_uses_per_recipe": 3}).status_code == 422
    response = recipe_client.post("/api/plans/generate", json={**request, "max_uses_per_recipe": 4})
    assert response.status_code == 201, response.text
    uses = Counter(d["recipe"]["slug"] for d in response.json()["days"])
    assert sorted(uses.values()) == [3, 4]


def test_the_conversation_turns_no_repeats_into_a_week_without_a_dish_twice(varied_client):
    session = varied_client.post("/api/agent/sessions", json={"message": "Dinners for two this week"}).json()
    assert session["can_confirm"] and session["constraints"]["max_uses_per_recipe"] is None

    asked = varied_client.post(
        f"/api/agent/sessions/{session['id']}/messages", json={"message": "No repeats, please"}
    ).json()
    assert asked["constraints"]["max_uses_per_recipe"] == 1 and asked["can_confirm"]
    assert "no dish twice" in asked["messages"][-1]["content"]

    confirmed = varied_client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    slugs = [d["recipe"]["slug"] for d in confirmed.json()["plan"]["days"]]
    assert len(slugs) == 14 and len(set(slugs)) == 14
