"""Like, Dislike and Never again (ADR-0087): storage, the API, and Never again as a hard filter on every path."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import recipe_feedback as feedback_routes
from app.api.routes.agent import get_agent_service
from app.api.routes.household_profiles import get_household_profile_service
from app.api.routes.meal_plans import (
    build_meal_plan_service,
    build_replanning_service,
    get_meal_plan_service,
    get_replanning_service,
)
from app.core.clock import today as local_today
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import app
from app.models.meal_plan import MealPlan, MealPlanEntry
from app.models.platform import HouseholdMembership, User
from app.models.recipe import Recipe, RecipeFeedback
from app.planning import preview
from app.planning.product_path import ProductPlanningEngine
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.repositories.recipe_feedback import RecipeFeedbackRepository, with_never_again
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment
from app.services import meal_plan as meal_plan_module
from tests.test_operations_console_api import _planning_run_ids
from tests.test_operations_console_api import console as console
from tests.test_planning_capability import COMPOSITION, _dish, _week_ahead, composed_client, dish_client  # noqa: F401
from tests.test_planning_preview import packet

MAINS = ["tofu-bowl", "chickpea-stew", "salmon-bake", "chicken-roast"]
WEEK = {"household_size": 2, "pricing_mode": "fixture", "meal_composition": [{"role_id": "main", "courses": ["main"]}]}


def dishes():
    return [
        _dish("tofu-bowl", "main", "firm_tofu", 100, calories=400),
        _dish("chickpea-stew", "main", "chickpea", 100, calories=400),
        _dish("salmon-bake", "main", "salmon_fillet", 100, calories=400),
        _dish("chicken-roast", "main", "chicken_breast", 100, calories=400),
    ]


@pytest.fixture
def client(monkeypatch):
    with dish_client(monkeypatch, dishes()) as client:
        yield client


@contextmanager
def _session():
    database = app.dependency_overrides[get_db_session]()
    session = next(database)
    try:
        yield session
    finally:
        database.close()


def _ids() -> dict[str, int]:
    with _session() as session:
        return {recipe.slug: recipe.id for recipe in session.scalars(select(Recipe))}


def _household(email: str = "cook@example.test") -> int:
    with _session() as session:
        user = session.scalar(select(User.id).where(User.normalized_email == email))
        return session.scalar(select(HouseholdMembership.household_id).where(HouseholdMembership.user_id == user))


def _rows(recipe_id: int | None = None) -> int:
    with _session() as session:
        where = [RecipeFeedback.recipe_id == recipe_id] if recipe_id is not None else []
        return session.scalar(select(func.count()).select_from(RecipeFeedback).where(*where)) or 0


def _never_again(client, *slugs: str) -> None:
    for slug in slugs:
        response = client.put(f"/api/feedback/recipes/{_ids()[slug]}", json={"kind": "never_again"})
        assert response.status_code == 200, response.text


def _role(role: str) -> None:
    with _session() as session:
        session.scalars(select(HouseholdMembership)).one().role = role
        session.commit()


def _slugs(plan: dict) -> set[str]:
    return {day["recipe"]["slug"] for day in plan["days"]}


@contextmanager
def _planned(monkeypatch):
    """Every candidate list the planner is handed, by slug, and each search's request digest, catalog and dump."""
    seen: list[set[str]] = []
    digests: list[tuple[str, str]] = []
    plan = ProductPlanningEngine.plan

    def spy(self, constraints, recommendations, *args, **kwargs):
        seen.append({r.recipe.slug for r in recommendations})
        result = plan(self, constraints, recommendations, *args, **kwargs)
        # The packet's own digest also covers the product snapshot's time, so its candidate set stands for it.
        digests.append((result.trace["input_digest"], result.trace["catalog_version"], result.trace["request"]))
        return result

    monkeypatch.setattr(ProductPlanningEngine, "plan", spy)
    yield seen, digests


# --- Storage and API ---


def test_feedback_state_is_the_latest_row_and_undo_deletes_every_row(client):
    tofu = _ids()["tofu-bowl"]
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "like"}).json() == {
        "recipe_id": tofu,
        "kind": "like",
    }
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "like"}).status_code == 200
    assert _rows(tofu) == 1  # pressing the state again adds nothing
    client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "dislike"})
    client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"})
    client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"})
    assert _rows(tofu) == 3  # append-only: like, dislike, never again

    listed = client.get("/api/feedback/recipes", params={"kind": "never_again"}).json()["items"]
    assert [(item["recipe_id"], item["slug"], item["title"], item["kind"]) for item in listed] == [
        (tofu, "tofu-bowl", "Tofu Bowl", "never_again")
    ]
    assert listed[0]["created_at"]
    assert client.get("/api/feedback/recipes", params={"kind": "like"}).json()["items"] == []

    assert client.delete(f"/api/feedback/recipes/{tofu}").status_code == 204
    assert _rows(tofu) == 0
    assert client.delete(f"/api/feedback/recipes/{tofu}").status_code == 204  # undo again is safe
    assert client.get("/api/feedback/recipes").json()["items"] == []
    assert client.put("/api/feedback/recipes/999999", json={"kind": "like"}).status_code == 404
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "love"}).status_code == 422


def test_like_or_dislike_after_never_again_lets_the_dish_be_planned_again(client):
    _never_again(client, "tofu-bowl")
    with _session() as session:
        assert RecipeFeedbackRepository(session, household_id=_household()).never_again_slugs() == ["tofu-bowl"]
    client.put(f"/api/feedback/recipes/{_ids()['tofu-bowl']}", json={"kind": "like"})
    with _session() as session:
        assert RecipeFeedbackRepository(session, household_id=_household()).never_again_slugs() == []


def test_any_member_may_give_or_undo_feedback_but_a_viewer_or_a_request_without_csrf_may_not(client):
    tofu = _ids()["tofu-bowl"]
    token = client.headers.pop("X-CSRF-Token")
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"}).status_code == 403
    assert client.delete(f"/api/feedback/recipes/{tofu}").status_code == 403
    client.headers["X-CSRF-Token"] = token

    client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"})  # the owner's
    _role("member")  # check-in only: may still replace or undo it (owner decision 2026-10-23)
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "like"}).status_code == 200
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"}).status_code == 200
    assert client.delete(f"/api/feedback/recipes/{tofu}").status_code == 204

    client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "never_again"})
    _role("viewer")
    assert client.put(f"/api/feedback/recipes/{tofu}", json={"kind": "like"}).status_code == 403
    assert client.delete(f"/api/feedback/recipes/{tofu}").status_code == 403
    assert [item["slug"] for item in client.get("/api/feedback/recipes").json()["items"]] == ["tofu-bowl"]


def test_a_household_never_sees_or_undoes_another_household_s_feedback(client):
    tofu = _ids()["tofu-bowl"]
    _never_again(client, "tofu-bowl")
    with TestClient(app) as other:
        registered = other.post(
            "/api/auth/register",
            json={"email": "bob@example.test", "password": "another long password 1", "display_name": "Bob"},
        )
        other.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        assert other.get("/api/feedback/recipes").json()["items"] == []
        assert other.delete(f"/api/feedback/recipes/{tofu}").status_code == 204
        assert other.put(f"/api/feedback/recipes/{tofu}", json={"kind": "like"}).status_code == 200
    assert _rows(tofu) == 2
    assert [item["kind"] for item in client.get("/api/feedback/recipes").json()["items"]] == ["never_again"]
    with _session() as session:
        assert RecipeFeedbackRepository(session, household_id=_household("bob@example.test")).states() == {tofu: "like"}


def test_never_again_is_capped_at_what_a_planning_request_carries(client, monkeypatch):
    monkeypatch.setattr(feedback_routes, "NEVER_AGAIN_LIMIT", 1)
    _never_again(client, "tofu-bowl")
    refused = client.put(f"/api/feedback/recipes/{_ids()['chicken-roast']}", json={"kind": "never_again"})
    assert refused.status_code == 422 and "At most 1" in refused.json()["detail"]
    assert client.put(f"/api/feedback/recipes/{_ids()['tofu-bowl']}", json={"kind": "never_again"}).status_code == 200


def test_the_dashboard_shows_each_dish_s_feedback(client):
    plan = client.post("/api/plans/generate", json={"requires_halal": False, **WEEK}).json()
    first = plan["days"][0]["recipe"]
    client.put(f"/api/feedback/recipes/{first['id']}", json={"kind": "never_again"})
    days = client.get(f"/api/plans/{plan['id']}/dashboard").json()["days"]
    assert {day["feedback"] for day in days if day["recipe"]["id"] == first["id"]} == {"never_again"}
    assert {day["feedback"] for day in days if day["recipe"]["id"] != first["id"]} == {None}
    # The saved week is never rewritten: the dish stays where it was planned.
    assert first["slug"] in _slugs(client.get(f"/api/plans/{plan['id']}").json())


# --- Never again on every planning path ---


def test_a_never_again_dish_is_never_planned_and_the_engine_says_why(client):
    _never_again(client, "tofu-bowl", "chickpea-stew")
    plan = client.post("/api/plans/generate", json={"requires_halal": False, **WEEK})
    assert plan.status_code == 201, plan.text
    assert _slugs(plan.json()) <= {"salmon-bake", "chicken-roast"}
    with _session() as session:
        stored = session.get(MealPlan, plan.json()["id"]).constraints
        tofu = session.scalar(select(Recipe).where(Recipe.slug == "tofu-bowl"))
        request = WeeklyMealPlanRequest.model_validate(stored)
        reasons = RecipeRecommendationEngine()._exclusion_reasons(tofu, request, [])
    assert stored["never_again_recipes"] == ["chickpea-stew", "tofu-bowl"]
    assert reasons == ["You asked not to plan this dish again."]


def test_a_week_checked_before_a_never_again_is_not_the_week_saved_after_it(client):
    request = WeeklyMealPlanRequest.model_validate(WEEK)
    with _session() as session:
        service = build_meal_plan_service(session, _household(), live_feedback=True)
        assert service.check(request) is None
        before = service._found_key(service._live(request))
        _never_again(client, *MAINS[:3])
        after = service._found_key(service._live(request))
        assert before != after
        plan = service.generate(request)
    assert {day.recipe.slug for day in plan.days} == {"chicken-roast"}


def test_the_cheapest_week_and_week_floor_offers_leave_the_dish_out(client, monkeypatch):
    _never_again(client, "tofu-bowl")
    floors = []
    original = meal_plan_module.week_floor

    def floor_spy(constraints, recommendations, recipes):
        floors.append({r.recipe.slug for r in recommendations})
        return original(constraints, recommendations, recipes)

    monkeypatch.setattr(meal_plan_module, "week_floor", floor_spy)
    request = WeeklyMealPlanRequest.model_validate({**WEEK, "weekly_budget_sgd": 100})
    with _planned(monkeypatch) as (seen, _), _session() as session:
        service = build_meal_plan_service(session, _household(), live_feedback=True)
        service.week_floor(request)
        assert service.cheapest_week(request) > 0
        assert service.cheapest_week(request, minimum_distinct_dishes=3) > 0
    assert floors and seen
    assert all("tofu-bowl" not in pool and pool for pool in floors + seen)


def test_broadened_candidates_leave_the_dish_out(client, monkeypatch):
    _never_again(client, "tofu-bowl")
    # Nothing is ready in 5 minutes, so the search broadens its candidates past the time limit.
    request = WeeklyMealPlanRequest.model_validate({**WEEK, "max_cooking_time_minutes": 5})
    with _planned(monkeypatch) as (seen, _), _session() as session:
        build_meal_plan_service(session, _household(), live_feedback=True).check(request)
    assert seen and any(seen) and all("tofu-bowl" not in pool for pool in seen)


def test_a_shared_dish_week_covering_each_member_leaves_the_dish_out(client):
    _never_again(client, "chickpea-stew")
    members = [{"name": "Ann", "servings": 1, "excluded_ingredients": ["firm_tofu"]}, {"name": "Ben", "servings": 1}]
    plan = client.post(
        "/api/plans/generate", json={"requires_halal": False, **{**WEEK, "household": {"members": members}}}
    )
    assert plan.status_code == 201, plan.text
    assert "chickpea-stew" not in _slugs(plan.json())


def test_a_swap_never_proposes_a_never_again_dish(client):
    plan = client.post("/api/plans/generate", json={"requires_halal": False, **WEEK}).json()
    entry = plan["days"][0]
    others = [slug for slug in MAINS if slug != entry["recipe"]["slug"]]
    _never_again(client, *others)

    def swap():
        return client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": entry["entry_id"], "event_type": "REPLACE_MEAL"},
        )

    assert swap().status_code == 422  # every other dish is Never again: nothing to swap to
    client.delete(f"/api/feedback/recipes/{_ids()[others[0]]}")
    allowed = swap()
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["after_entry"]["recipe_slug"] == others[0]


def test_a_variety_preview_never_brings_a_never_again_dish(client):
    _never_again(client, "salmon-bake", "chicken-roast")
    plan = client.post(
        "/api/plans/generate", json={"requires_halal": False, **{**WEEK, "start_date": local_today().isoformat()}}
    ).json()
    assert _slugs(plan) == {"tofu-bowl", "chickpea-stew"}  # two dishes over seven days: repeats
    client.delete(f"/api/feedback/recipes/{_ids()['salmon-bake']}")
    with _session() as session:
        changes = build_replanning_service(session, _household(), live_feedback=True)
        event, _, _ = changes.preview_variety(plan_id=plan["id"])
    assert event is not None
    assert {dish.recipe_slug for dish in event.shape_change.added} == {"salmon-bake"}


def test_a_preview_made_before_a_never_again_cannot_be_confirmed_after_it(client):
    _never_again(client, "salmon-bake", "chicken-roast")
    plan = client.post(
        "/api/plans/generate", json={"requires_halal": False, **{**WEEK, "start_date": local_today().isoformat()}}
    ).json()
    client.delete(f"/api/feedback/recipes/{_ids()['salmon-bake']}")  # leaves the variety preview a dish to bring
    entry = plan["days"][0]
    swap = client.post(
        f"/api/plans/{plan['id']}/replan/preview", json={"entry_id": entry["entry_id"], "event_type": "REPLACE_MEAL"}
    ).json()
    with _session() as session:
        variety, _, _ = build_replanning_service(session, _household(), live_feedback=True).preview_variety(
            plan_id=plan["id"]
        )
    assert variety is not None
    # Pressed in another tab while both previews are open: neither may bring the dish in.
    _never_again(client, swap["after_entry"]["recipe_slug"], *(dish.recipe_slug for dish in variety.shape_change.added))
    for event_id in (swap["id"], variety.id):
        refused = client.post(f"/api/plans/{plan['id']}/replan/{event_id}/confirm")
        assert refused.status_code == 409, refused.text
        assert "Generate a new preview" in refused.json()["detail"]
    assert client.get(f"/api/plans/{plan['id']}").json()["days"] == plan["days"]


def test_a_meal_change_replans_a_meal_holding_a_never_again_dish(composed_client):  # noqa: F811
    plan = _week_ahead(composed_client, COMPOSITION[:2])
    friday_main = next(d["recipe"] for d in plan["days"] if d["day_index"] == 5 and d["role_id"] == "main")
    before = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in plan["days"]}
    assert (
        composed_client.put(f"/api/feedback/recipes/{friday_main['id']}", json={"kind": "never_again"}).status_code
        == 200
    )

    preview_ = composed_client.post(
        f"/api/plans/{plan['id']}/shape/preview",
        json={"meal_type": "dinner", "roles": COMPOSITION, "day_indexes": [5]},
    )
    assert preview_.status_code == 201, preview_.text
    # The Never-again main cannot stay with the meal: it drops out and the whole dinner is planned again.
    change = preview_.json()["shape_change"]
    assert change["kept"] < 2
    applied = composed_client.post(f"/api/plans/{plan['id']}/replan/{preview_.json()['id']}/confirm").json()["plan"]
    assert friday_main["slug"] not in {d["recipe"]["slug"] for d in applied["days"] if d["day_index"] == 5}
    # Every other meal stays as saved, the same dish on other days included.
    others = {(d["day_index"], d["role_id"]): d["recipe"]["slug"] for d in applied["days"] if d["day_index"] != 5}
    assert others == {key: slug for key, slug in before.items() if key[0] != 5}


def test_a_replan_leaves_locked_and_cooked_never_again_dishes_as_they_are(client):
    start = (local_today() + timedelta(days=1)).isoformat()
    plan = client.post("/api/plans/generate", json={"requires_halal": False, **{**WEEK, "start_date": start}}).json()
    locked, cooked, target = plan["days"][0], plan["days"][1], plan["days"][2]
    with _session() as session:
        session.get(MealPlanEntry, locked["entry_id"]).is_locked = True
        done = session.get(MealPlanEntry, cooked["entry_id"])
        done.status, done.consumed_at = "completed", datetime.now(UTC)
        session.commit()
    _never_again(client, locked["recipe"]["slug"], cooked["recipe"]["slug"])

    preview_ = client.post(
        f"/api/plans/{plan['id']}/replan/preview", json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"}
    )
    assert preview_.status_code == 201, preview_.text
    assert preview_.json()["after_entry"]["recipe_slug"] not in {locked["recipe"]["slug"], cooked["recipe"]["slug"]}
    confirmed = client.post(f"/api/plans/{plan['id']}/replan/{preview_.json()['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    after = {day["entry_id"]: day["recipe"]["slug"] for day in confirmed.json()["plan"]["days"]}
    assert after[locked["entry_id"]] == locked["recipe"]["slug"]
    assert after[cooked["entry_id"]] == cooked["recipe"]["slug"]
    for entry in (locked, cooked):
        refused = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={"entry_id": entry["entry_id"], "event_type": "REPLACE_MEAL"},
        )
        assert refused.status_code == 422  # locked and cooked entries are never planned again


def test_the_validator_rejects_a_never_again_dish_even_in_a_locked_slot():
    problem = packet()
    solution = preview.preview_plan(problem).solution
    assignments = [PlanningAssignment(slot_id=slot, recipe_id=recipe) for slot, recipe in solution.choices]
    assert preview.validate_mixed_shopping(problem, assignments, solution.shopping) == ()
    problem.never_again_recipes = [assignments[0].recipe_id]
    assert preview.validate_mixed_shopping(problem, assignments, solution.shopping) == ("excluded_recipe",)
    problem.slots[0].locked_recipe_id = assignments[0].recipe_id  # no exemption
    assert preview.validate_mixed_shopping(problem, assignments, solution.shopping) == ("excluded_recipe",)
    assert not preview.preview_plan(problem).validated


# --- An empty list changes nothing; evaluations and replays plan as stored ---


def test_an_empty_never_again_list_leaves_dumps_and_digests_byte_identical(client, monkeypatch):
    request = WeeklyMealPlanRequest.model_validate(WEEK)
    assert "never_again_recipes" not in request.model_dump()
    assert request.model_dump_json() == request.model_copy(update={"never_again_recipes": []}).model_dump_json()
    problem = packet()
    assert "never_again_recipes" not in problem.model_dump()
    assert (
        problem.model_dump_json()
        == FinalPlanningProblem.model_validate({**problem.model_dump(), "never_again_recipes": []}).model_dump_json()
    )
    with _session() as session:
        assert with_never_again(request, session, _household()) is request

    with _planned(monkeypatch) as (_, digests):
        stored = [client.post("/api/plans/generate", json={"requires_halal": False, **WEEK}).json()["id"]]
        with _session() as session:
            stored.append(build_meal_plan_service(session, _household()).generate(request).id)
    assert digests[0] == digests[1] and "never_again_recipes" not in digests[0][2]
    with _session() as session:
        first, second = (session.get(MealPlan, plan_id).constraints for plan_id in stored)
    assert first == second and "never_again_recipes" not in first


def test_evaluation_services_ignore_the_household_s_live_feedback(client, monkeypatch):
    request = WeeklyMealPlanRequest.model_validate(WEEK)
    with _planned(monkeypatch) as (seen, digests), _session() as session:
        build_meal_plan_service(session, _household()).generate(request)
        _never_again(client, *MAINS)
        # As every evaluation builds it: the same packet, whatever the household pressed since.
        build_meal_plan_service(session, _household()).generate(request)
        assert not build_replanning_service(session, _household()).live_feedback
    assert digests[0] == digests[1] and seen[0] == seen[1]


def test_every_product_entry_point_plans_with_live_feedback(client):
    with _session() as session:
        household = _household()
        current = SimpleNamespace(
            active_membership=SimpleNamespace(household_id=household),
            user=SimpleNamespace(id=session.scalar(select(User.id))),
        )
        plans = get_meal_plan_service(session, current)
        changes = get_replanning_service(session, current)
        profiles = get_household_profile_service(session, current)
        agent = get_agent_service(session, get_settings(), current)  # chat's new week, swaps and checks
    assert plans.live_feedback and changes.live_feedback and changes.meal_plan_service.live_feedback
    assert profiles.meal_plan_service.live_feedback
    assert agent.meal_plan_service.live_feedback and agent.replanning_service.live_feedback


def test_the_console_replay_plans_a_stored_request_as_stored_after_a_never_again(console):  # noqa: F811
    client, factory = console
    plan = client.post("/api/plans/generate", json={"requires_halal": False, **{**WEEK, "start_date": "2026-09-01"}})
    assert plan.status_code == 201, plan.text
    (run_id,) = _planning_run_ids(factory)
    for slug in _slugs(plan.json()):
        recipe = next(day["recipe"]["id"] for day in plan.json()["days"] if day["recipe"]["slug"] == slug)
        assert client.put(f"/api/feedback/recipes/{recipe}", json={"kind": "never_again"}).status_code == 200

    replay = client.post(f"/api/ops/replay/planning/{run_id}", json={})
    assert replay.status_code == 200, replay.text
    assert replay.json()["replay"]["dishes"] == replay.json()["original"]["dishes"]
