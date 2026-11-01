"""A halal household (docs/design/halal.md; Knowledge ADR-0104): the profile's switch, the chat's request, the offer
to save it, and the replans that keep it."""

import pytest
from sqlalchemy import update

from app.agent.parser import OpenAIConstraintParser, requests_halal
from app.models.meal_plan import MealPlan
from app.models.recipe import Recipe
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from tests.test_out_of_stock_swap import chat, mains, week
from tests.test_planning_capability import dish_client
from tests.test_planning_product_path import database
from tests.test_recipes import recipe_client as recipe_client
from tests.test_walkthrough_1004_planning import add

DINNER = {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}}
PROFILE = {
    "name": "Tan household",
    "members": [{"name": "Ann", "servings_per_meal": 1}, {"name": "Ben", "servings_per_meal": 1}],
    "plan_shape": DINNER,
    "requires_halal": False,
}
# Plant dishes only: none of them is meat, so none needs a certified product.
HALAL_DISHES = [
    ("chickpea-stew", "chickpea"),
    ("bean-chili", "black_bean"),
    ("mushroom-rice", "mushroom"),
    ("lentil-dal", "lentil"),
    ("spinach-bake", "spinach"),
    ("carrot-soup", "carrot"),
    ("tofu-stir-fry", "firm_tofu"),
]


def halal_mains(*pairs):
    dishes = mains(*pairs)
    for dish in dishes:
        dish.halal_status = "halal"
    return dishes


def halal_recipes(client):
    """Every recipe of the client's small catalog labelled halal, so a halal week can be planned from it."""
    with database() as session:
        session.execute(update(Recipe).values(halal_status="halal"))
        session.commit()


def stored_constraints(plan_id: int) -> dict:
    with database() as session:
        return session.get(MealPlan, plan_id).constraints


def profile(client) -> dict:
    return client.get("/api/household-profiles/current").json()


def start(client, message: str) -> dict:
    response = client.post("/api/agent/sessions", json={"message": message})
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, session: dict) -> dict:
    response = client.post(f"/api/agent/sessions/{session['id']}/confirm")
    assert response.status_code == 200, response.text
    return response.json()


def say(client, session: dict, message: str) -> dict:
    response = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def halal_week(client) -> dict:
    response = client.post(
        "/api/plans/generate",
        json={"requires_halal": True, "household_size": 4, "pricing_mode": "fixture", "plan_shape": DINNER},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_profile_keeps_the_halal_switch_with_each_version(recipe_client):
    created = recipe_client.post("/api/household-profiles", json=PROFILE).json()
    assert created["current"]["requires_halal"] is False
    update_body = {**PROFILE, "expected_version": 1}
    on = recipe_client.put(f"/api/household-profiles/{created['id']}", json={**update_body, "requires_halal": True})
    assert on.status_code == 200, on.text
    assert on.json()["current"]["requires_halal"] is True
    off = recipe_client.put(f"/api/household-profiles/{created['id']}", json={**update_body, "expected_version": 2})
    assert off.json()["current"]["requires_halal"] is False
    versions = recipe_client.get(f"/api/household-profiles/{created['id']}/versions").json()["items"]
    assert [(item["version"], item["requires_halal"]) for item in versions] == [(3, False), (2, True), (1, False)]


def test_a_halal_profile_plans_only_halal_dishes_and_no_override_turns_it_off(monkeypatch):
    with dish_client(monkeypatch, halal_mains(*HALAL_DISHES)) as client:
        add(*mains(("pork-belly-stew", "pork_belly")))  # in the catalog, but not halal (no status)
        saved = client.post("/api/household-profiles", json={**PROFILE, "requires_halal": True}).json()
        planned = client.post(
            f"/api/household-profiles/{saved['id']}/plans",
            json={"start_date": "2027-01-03", "overrides": {"requires_halal": False}},
        )
        assert planned.status_code == 201, planned.text
        plan = planned.json()["plan"]
        assert stored_constraints(plan["id"])["requires_halal"] is True
        assert "pork-belly-stew" not in {day["recipe"]["slug"] for day in plan["days"]}


def test_a_conversation_on_a_halal_profile_starts_halal_and_offers_nothing_to_save(monkeypatch):
    with dish_client(monkeypatch, halal_mains(*HALAL_DISHES)) as client:
        client.post("/api/household-profiles", json={**PROFILE, "requires_halal": True})
        session = start(client, "Dinners for two")
        assert session["constraints"]["requires_halal"] is True
        done = confirm(client, session)["session"]
        assert done["pending_interaction"] is None
        assert "halal too" not in done["messages"][-1]["content"]


def test_a_halal_request_plans_halal_and_the_profile_changes_only_on_a_yes(recipe_client):
    halal_recipes(recipe_client)
    recipe_client.post("/api/household-profiles", json=PROFILE)

    session = start(recipe_client, "Plan halal dinners for two.")
    assert session["constraints"]["requires_halal"] is True and session["can_confirm"]
    assert "halal" in session["messages"][-1]["content"] and "not supported" not in session["messages"][-1]["content"]
    done = confirm(recipe_client, session)
    assert done["session"]["pending_interaction"]["field_path"] == "requires_halal.keep"
    assert done["session"]["messages"][-1]["content"].endswith("Should new weeks be halal too?")
    assert stored_constraints(done["plan"]["id"])["requires_halal"] is True
    assert profile(recipe_client)["current"]["requires_halal"] is False  # nothing saved before a yes

    saved = say(recipe_client, done["session"], "Yes, keep it as our usual")
    assert "household is now halal" in saved["messages"][-1]["content"]
    assert saved["pending_interaction"] is None
    current = profile(recipe_client)
    assert (current["current_version"], current["current"]["requires_halal"]) == (2, True)
    # The next conversation starts halal, as the profile now is.
    assert start(recipe_client, "Dinners for two")["constraints"]["requires_halal"] is True


@pytest.mark.parametrize("answer", ["No, just this week", "no"])
def test_a_no_keeps_halal_to_this_week_and_the_profile_as_it_is(recipe_client, answer):
    halal_recipes(recipe_client)
    recipe_client.post("/api/household-profiles", json=PROFILE)
    done = confirm(recipe_client, start(recipe_client, "Plan halal dinners for two."))["session"]
    said = say(recipe_client, done, answer)
    assert "only this week is halal" in said["messages"][-1]["content"]
    assert said["pending_interaction"] is None
    current = profile(recipe_client)
    assert (current["current_version"], current["current"]["requires_halal"]) == (1, False)


def test_the_choice_buttons_save_halal_too(recipe_client):
    halal_recipes(recipe_client)
    recipe_client.post("/api/household-profiles", json=PROFILE)
    done = confirm(recipe_client, start(recipe_client, "我们要清真晚餐，两个人"))["session"]
    asked = done["pending_interaction"]
    assert asked["field_path"] == "requires_halal.keep"
    assert done["messages"][-1]["content"].endswith("以后每周也按清真安排吗？")
    answered = recipe_client.post(
        f"/api/agent/sessions/{done['id']}/interactions",
        json={"question_id": asked["question_id"], "option_ids": ["keep"], "context_version": asked["context_version"]},
    )
    assert answered.status_code == 200, answered.text
    assert "清真" in answered.json()["messages"][-1]["content"]
    assert profile(recipe_client)["current"]["requires_halal"] is True


@pytest.mark.parametrize("message", ["Dinners for two, no need for halal", "两个人吃晚餐，不需要清真"])
def test_a_negated_halal_mention_plans_ordinary_meals(recipe_client, message):
    session = start(recipe_client, message)
    assert session["constraints"].get("requires_halal", False) is False
    done = confirm(recipe_client, session)
    assert not stored_constraints(done["plan"]["id"]).get("requires_halal")


@pytest.mark.parametrize(
    ("message", "asked"),
    [
        ("halal", True),
        ("清真", True),
        ("make this week halal", True),
        ("we eat halal", True),
        ("要清真", True),
        ("Dinners for two, halal please", True),
        ("no need for halal", False),
        ("It doesn't need to be halal", False),
        ("no need to be halal", False),
        ("we don’t need halal", False),
        ("we do not need halal", False),
        ("no halal needed", False),
        ("no halal required", False),
        ("the plan doesn't have to be halal", False),
        ("the plan does not have to be halal", False),
        ("not halal", False),
        ("we're a non-halal household", False),
        ("non halal is fine", False),
        ("不用清真", False),
        ("不必清真", False),
        ("不要求清真", False),
        ("不一定要清真", False),
        ("不要清真", False),
        ("无需清真", False),
        ("不需要清真", False),
    ],
)
def test_a_halal_request_is_read_with_its_negations(message, asked):
    assert requests_halal(message) is asked


def test_a_new_week_of_a_halal_week_stays_halal_in_a_chat_that_is_not(monkeypatch):
    with dish_client(monkeypatch, halal_mains(*HALAL_DISHES)) as client:
        client.post("/api/household-profiles", json=PROFILE)  # not halal: the chat starts from ordinary constraints
        plan = halal_week(client)
        add(*mains(("pork-belly-stew", "pork_belly")))  # arrives after the week: no halal status
        session = chat(client, plan, "Is this fine?")
        assert not session["constraints"].get("requires_halal")
        changed = say(client, session, "Plan a new week with different dishes.")
        assert changed["plan_id"] != plan["id"]
        assert stored_constraints(changed["plan_id"])["requires_halal"] is True
        assert changed["constraints"]["requires_halal"] is True
        dishes = client.get(f"/api/plans/{changed['plan_id']}").json()["days"]
        assert "pork-belly-stew" not in {day["recipe"]["slug"] for day in dishes}


class ForgetfulModel:
    """A model that leaves requires_halal out whatever was said."""

    def invoke(self, prompt):
        return AgentConstraintExtraction(household_size=2)


@pytest.mark.parametrize(
    ("message", "expected"),
    [("Dinners for two, halal please", True), ("我们要清真晚餐", True), ("Dinners for two, no need for halal", None)],
)
def test_the_model_leaving_halal_out_does_not_drop_a_clear_request(message, expected):
    parser = OpenAIConstraintParser.__new__(OpenAIConstraintParser)
    parser.vocabulary, parser.model, parser.structured_model = None, "synthetic", ForgetfulModel()
    extraction = parser.parse(message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[])
    assert extraction.requires_halal is expected


def test_halal_asked_of_a_planned_week_replaces_it_with_a_halal_one(recipe_client):
    recipe_client.post("/api/household-profiles", json=PROFILE)
    session = start(recipe_client, "Dinners for two")
    first = confirm(recipe_client, session)["plan"]
    assert not stored_constraints(first["id"]).get("requires_halal")
    halal_recipes(recipe_client)

    changed = say(recipe_client, session, "Make this week halal")
    assert changed["constraints"]["requires_halal"] is True
    assert changed["plan_id"] != first["id"]
    assert stored_constraints(changed["plan_id"])["requires_halal"] is True
    assert changed["pending_interaction"]["field_path"] == "requires_halal.keep"


def test_a_question_about_a_dish_does_not_make_the_week_halal(recipe_client):
    session = start(recipe_client, "Dinners for two")
    plan = confirm(recipe_client, session)["plan"]
    asked = say(recipe_client, session, "Is the lemon chicken halal?")
    assert asked["plan_id"] == plan["id"] and not asked["constraints"].get("requires_halal")


def test_a_swap_on_a_halal_week_never_offers_a_dish_that_is_not_halal(monkeypatch):
    with dish_client(monkeypatch, halal_mains(*HALAL_DISHES)) as client:
        plan = halal_week(client)
        add(*mains(("pork-belly-stew", "pork_belly")))  # arrives after the week: no halal status
        for day in plan["days"]:
            preview = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={"event_type": "REPLACE_MEAL", "entry_id": day["entry_id"]},
            )
            assert preview.status_code in {201, 422}, preview.text
            if preview.status_code == 201:
                assert preview.json()["after_entry"]["recipe_slug"] != "pork-belly-stew"
        # An ordinary week of the same catalog is not halal-gated: the flag, not luck, kept the dish out.
        assert not stored_constraints(week(client)["id"]).get("requires_halal")


def test_a_cant_buy_message_on_a_halal_week_keeps_it_halal(monkeypatch):
    with dish_client(monkeypatch, halal_mains(*HALAL_DISHES)) as client:
        plan = halal_week(client)
        add(*mains(("pork-belly-stew", "pork_belly")))
        preview = chat(client, plan, "I can't buy chickpea this week")["pending_replan"]
        assert preview is None or preview["after_entry"]["recipe_slug"] != "pork-belly-stew"


def test_a_shape_change_on_a_halal_week_plans_only_halal_dishes(monkeypatch):
    soup = [{"role_id": "soup", "courses": ["soup"], "required": False}]
    roles = [*DINNER["meals"]["dinner"], *soup]
    dishes = halal_mains(*HALAL_DISHES, ("pork-bone-soup", "carrot"))
    dishes[-1].course = dishes[-1].meal_type = "soup"  # a soup, but not halal
    dishes[-1].halal_status = None
    with dish_client(monkeypatch, dishes) as client:
        plan = halal_week(client)
        preview = client.post(
            f"/api/plans/{plan['id']}/shape/preview", json={"meal_type": "dinner", "roles": roles, "day_indexes": [5]}
        )
        added = preview.json()["shape_change"]["added"] if preview.status_code == 201 else []
        assert "pork-bone-soup" not in {dish["recipe_slug"] for dish in added}, preview.text
        # An ordinary week of the same catalog takes that soup: the flag, not luck, kept it out.
        ordinary = week(client)
        ordinary_preview = client.post(
            f"/api/plans/{ordinary['id']}/shape/preview",
            json={"meal_type": "dinner", "roles": roles, "day_indexes": [5]},
        )
        assert ordinary_preview.status_code == 201, ordinary_preview.text
        assert "pork-bone-soup" in {dish["recipe_slug"] for dish in ordinary_preview.json()["shape_change"]["added"]}
