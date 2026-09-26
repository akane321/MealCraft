"""Console slice 2 (ADR-0047): replay, runtime settings, experiments and users."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.agent import AgentRun, AgentRunCheckpoint, AgentSession
from app.models.meal_plan import MealPlan
from app.models.platform import AuditEvent, HouseholdMembership, OperationRun, User
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep


def _recipe(slug, title, ingredients, *, tags, minutes, nutrition) -> Recipe:
    return Recipe(
        slug=slug,
        title=title,
        description=f"{title} for the console tests.",
        cuisine="Test",
        meal_type="main",
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=minutes,
        dietary_tags=tags,
        nutrition=RecipeNutrition(**{key: Decimal(str(value)) for key, value in nutrition.items()}),
        recipe_ingredients=[
            RecipeIngredient(ingredient=item, quantity=Decimal(str(quantity)), unit=unit, sort_order=index)
            for index, (item, quantity, unit) in enumerate(ingredients, start=1)
        ],
        steps=[RecipeStep(step_number=1, instruction="Cook it.")],
    )


@pytest.fixture
def console() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database:
        chicken = Ingredient(normalized_name="chicken_breast", display_name="Chicken breast")
        lemon = Ingredient(normalized_name="lemon", display_name="Lemon")
        tofu = Ingredient(normalized_name="firm_tofu", display_name="Firm tofu", allergens=["soy"])
        soba = Ingredient(normalized_name="soba_noodle", display_name="Soba noodles", allergens=["gluten"])
        nutrition = {
            "calories_kcal": 500,
            "protein_g": 30,
            "carbohydrate_g": 50,
            "fat_g": 18,
            "sodium_mg": 600,
            "sugar_g": 6,
        }
        database.add_all(
            [
                _recipe(
                    "lemon-chicken",
                    "Lemon Chicken",
                    [(chicken, 300, "g"), (lemon, 1, "whole")],
                    tags=["high-protein"],
                    minutes=20,
                    nutrition=nutrition,
                ),
                _recipe(
                    "tofu-soba",
                    "Tofu Soba",
                    [(tofu, 300, "g"), (soba, 160, "g")],
                    tags=["vegetarian"],
                    minutes=25,
                    nutrition=nutrition,
                ),
            ]
        )
        database.commit()
    test_settings = Settings(environment="test", database_url="sqlite+pysqlite://", auth_cookie_secure=False)

    def override_database() -> Generator[Session, None, None]:
        with factory() as database:
            yield database

    app.dependency_overrides[get_db_session] = override_database
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"email": "ops@example.test", "display_name": "Ops", "password": "correct-horse-battery-staple"},
        )
        assert registered.status_code == 201
        client.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        with factory() as database:
            database.scalars(select(User)).one().system_role = "admin"
            database.commit()
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def _count(factory: sessionmaker, model, *where) -> int:
    with factory() as database:
        return database.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _planning_run_ids(factory: sessionmaker) -> list[int]:
    with factory() as database:
        return list(
            database.scalars(
                select(OperationRun.id).where(OperationRun.run_type == "planning").order_by(OperationRun.id)
            )
        )


# --- Debugging: replay ---


def test_agent_turn_replays_through_the_parser_without_saving_anything(console) -> None:
    client, factory = console
    created = client.post("/api/agent/sessions", json={"message": "Dinners for two, around S$90 this week"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    reply = client.post(f"/api/agent/sessions/{session_id}/messages", json={"message": "No peanuts please"})
    assert reply.status_code == 200
    follow_up = reply.json()["latest_run"]["id"]
    tasks_before = client.get("/api/ops/tasks").json()["total"]
    messages_before = len(reply.json()["messages"])

    response = client.post(f"/api/ops/replay/agent/{follow_up}", json={"parser": "fixture"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "agent"
    assert payload["overrides"] == {"parser": "fixture"}
    assert payload["original"]["message"] == "No peanuts please"
    # The follow-up is read against the constraints stored before it, so the household size is kept.
    assert payload["replay"]["constraints"]["household_size"] == 2
    assert payload["replay"]["constraints"] == payload["original"]["constraints"]
    assert payload["replay"]["assistant_message"] == payload["original"]["assistant_message"]
    assert payload["replay"]["parser"] == "fixture"

    assert _count(factory, AgentSession) == 1
    assert len(client.get(f"/api/agent/sessions/{session_id}").json()["messages"]) == messages_before
    assert client.get("/api/ops/tasks").json()["total"] == tasks_before
    listed = client.get("/api/ops/replays").json()["items"]
    assert [(item["kind"], item["source_id"]) for item in listed] == [("agent", follow_up)]
    assert client.get(f"/api/ops/replays/{listed[0]['id']}").json()["replay"] == payload["replay"]


def test_agent_replay_explains_what_cannot_be_replayed(console) -> None:
    client, factory = console
    created = client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    with factory() as database:
        now = datetime.now(UTC)
        run = AgentRun(
            agent_session_id=created["id"],
            idempotency_key="old-run",
            intent="create_plan",
            status="committed",
            input_digest="a" * 64,
            context_version=1,
            deadline_at=now + timedelta(minutes=2),
        )
        database.add(run)
        database.flush()
        database.add(
            AgentRunCheckpoint(
                agent_run_id=run.id, sequence=1, stage="turn_completed", status="ok", state_digest="b" * 64
            )
        )
        database.commit()
        old_id = run.id

    assert client.post(f"/api/ops/replay/agent/{old_id}").status_code == 409
    assert client.post("/api/ops/replay/agent/999999").status_code == 404
    # A live-model replay needs the key; without it the console says so instead of calling out.
    live = client.post(f"/api/ops/replay/agent/{created['latest_run']['id']}", json={"parser": "openai"})
    assert live.status_code == 409
    assert "OPENAI_API_KEY" in live.json()["detail"]


def test_planning_replay_uses_the_stored_request_and_saves_no_plan(console) -> None:
    client, factory = console
    plan = client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-01",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "weekly_budget_sgd": 40,
            "pricing_mode": "fixture",
        },
    )
    assert plan.status_code == 201
    failed = client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-01",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "weekly_budget_sgd": 5,
            "pricing_mode": "fixture",
        },
    )
    assert failed.status_code == 422
    succeeded_id, failed_id = _planning_run_ids(factory)

    same = client.post(f"/api/ops/replay/planning/{succeeded_id}", json={"beam_width": 4, "max_expansions": 500})
    assert same.status_code == 200
    body = same.json()
    assert body["original"]["status"] == body["replay"]["status"] == "feasible"
    assert len(body["replay"]["dishes"]) == 7
    assert {dish["recipe"] for dish in body["replay"]["dishes"]} <= {"Lemon Chicken", "Tofu Soba"}
    assert body["replay"]["settings"]["width"] == 4
    assert body["replay"]["total_cost_sgd"] <= 40

    # The failed run kept its full request in the trace, so it replays with a larger budget.
    fixed = client.post(f"/api/ops/replay/planning/{failed_id}", json={"weekly_budget_sgd": 40})
    assert fixed.status_code == 200
    assert fixed.json()["original"]["status"] != "feasible"
    assert fixed.json()["original"]["dishes"] == []
    assert fixed.json()["replay"]["status"] == "feasible"

    assert _count(factory, MealPlan) == 1
    assert _planning_run_ids(factory) == [succeeded_id, failed_id]
    assert _count(factory, OperationRun, OperationRun.run_type == "replay") == 2
    assert client.post(f"/api/ops/replay/planning/{failed_id}", json={"beam_width": 0}).status_code == 422
    assert client.post("/api/ops/replay/planning/999999").status_code == 404


def test_planning_run_without_a_stored_request_cannot_be_replayed(console) -> None:
    client, factory = console
    with factory() as database:
        database.add(
            OperationRun(
                trace_id="planning-old",
                run_type="planning",
                status="failed",
                artifact_references=[{"kind": "planning_trace", "data": {"status": "infeasible"}}],
            )
        )
        database.commit()
    (run_id,) = _planning_run_ids(factory)
    response = client.post(f"/api/ops/replay/planning/{run_id}")
    assert response.status_code == 409
    assert "nothing to replay" in response.json()["detail"]


# --- Experiments & configuration ---


def test_runtime_settings_change_is_audited_and_reaches_the_assistant(console) -> None:
    client, factory = console
    listed = {item["key"]: item for item in client.get("/api/ops/config").json()["items"]}
    assert set(listed) == {
        "agent_parser_provider",
        "openai_timeout_seconds",
        "pricing_mode",
        "planning_capability",
        "beam_width",
        "beam_max_expansions",
        "meal_options_per_slot",
    }
    assert (
        listed["agent_parser_provider"] | {"value": "fixture", "overridden": False, "wired": True}
        == listed["agent_parser_provider"]
    )
    assert listed["beam_width"]["default"] == 32
    assert listed["beam_width"]["wired"] is False

    changed = client.put("/api/ops/config/agent_parser_provider", json={"value": "openai"})
    assert changed.status_code == 200
    setting = next(item for item in changed.json()["items"] if item["key"] == "agent_parser_provider")
    assert (setting["value"], setting["overridden"]) == ("openai", True)
    # New conversations now ask for the live parser, which needs a key this server does not have.
    assert client.post("/api/agent/sessions", json={"message": "Dinners for two"}).status_code == 503

    assert client.put("/api/ops/config/agent_parser_provider", json={"value": None}).status_code == 200
    assert client.post("/api/agent/sessions", json={"message": "Dinners for two"}).status_code == 201
    assert client.put("/api/ops/config/beam_width", json={"value": 64}).status_code == 200

    history = client.get("/api/ops/config/history").json()["items"]
    assert [(item["key"], item["before"], item["after"], item["actor"]) for item in history] == [
        ("beam_width", 32, 64, "Ops"),
        ("agent_parser_provider", "openai", "fixture", "Ops"),
        ("agent_parser_provider", "fixture", "openai", "Ops"),
    ]
    assert _count(factory, AuditEvent, AuditEvent.target_type == "runtime_setting") == 3

    assert client.put("/api/ops/config/beam_width", json={"value": 0}).status_code == 422
    assert client.put("/api/ops/config/beam_width", json={"value": 2.5}).status_code == 422
    assert client.put("/api/ops/config/planning_capability", json={"value": "huge"}).status_code == 422
    assert client.put("/api/ops/config/invented", json={"value": 1}).status_code == 404


def test_experiments_run_developer_sets_under_a_recorded_configuration(console) -> None:
    client, _ = console
    planning = client.post(
        "/api/ops/experiments",
        json={"evaluation": "developer-planning", "label": "greedy", "overrides": {"planner": "greedy-baseline"}},
    )
    assert planning.status_code == 200
    planning = planning.json()
    assert planning["status"] == "succeeded"
    assert planning["configuration"]["planner"] == "greedy-baseline"
    assert planning["configuration"]["agent_parser_provider"] == "fixture"
    assert planning["metrics"]["scenario_count"] == 20
    assert planning["conditions"]["dataset"]["path"].endswith("dev/planning-v1.json")
    assert len(planning["conditions"]["dataset"]["sha256"]) == 64
    assert len(planning["conditions"]["parameter_digest"]) == 64
    assert (planning["conditions"]["seed"], planning["conditions"]["repeats"]) == (0, 1)

    agent = client.post("/api/ops/experiments", json={"evaluation": "agent-benchmark"}).json()
    assert agent["status"] == "succeeded"
    assert agent["metrics"]["case_count"] > 0

    listed = client.get("/api/ops/experiments").json()
    assert [item["id"] for item in listed["items"]] == [agent["id"], planning["id"]]
    assert {item["name"] for item in listed["evaluations"]} == {"developer-planning", "agent-benchmark"}
    assert "heldout" not in str(listed["evaluations"])

    assert client.post("/api/ops/experiments", json={"evaluation": "heldout-planning"}).status_code == 422
    unknown = client.post("/api/ops/experiments", json={"evaluation": "agent-benchmark", "overrides": {"api_key": "x"}})
    assert unknown.status_code == 422
    live = client.post(
        "/api/ops/experiments",
        json={"evaluation": "agent-benchmark", "overrides": {"agent_parser_provider": "openai"}},
    )
    assert live.status_code == 422
    assert "OPENAI_API_KEY" in live.json()["detail"]


# --- Users ---


def _second_account(factory: sessionmaker) -> int:
    with TestClient(app) as other:
        response = other.post(
            "/api/auth/register",
            json={"email": "bob@example.test", "display_name": "Bob", "password": "another-long-password-1"},
        )
        assert response.status_code == 201
        other.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})
        assert other.post("/api/agent/sessions", json={"message": "Dinners for three"}).status_code == 201
        plan = other.post(
            "/api/plans/generate",
            json={
                "household_size": 2,
                "max_cooking_time_minutes": 60,
                "weekly_budget_sgd": 40,
                "pricing_mode": "fixture",
            },
        )
        assert plan.status_code == 201
    with factory() as database:
        return database.scalar(select(User.id).where(User.normalized_email == "bob@example.test"))


def test_users_are_listed_searched_and_edited_with_an_audit_row(console) -> None:
    client, factory = console
    bob = _second_account(factory)

    everyone = client.get("/api/ops/users").json()
    assert everyone["total"] == 2
    found = client.get("/api/ops/users", params={"q": "BOB"}).json()
    assert [item["id"] for item in found["items"]] == [bob]
    summary = found["items"][0]
    assert (summary["conversations"], summary["plans"]) == (1, 1)
    assert summary["households"][0]["role"] == "owner"
    assert summary["last_seen_at"] is not None

    detail = client.get(f"/api/ops/users/{bob}").json()
    assert detail["recent_conversations"][0]["first_message"] == "Dinners for three"
    assert detail["recent_plans"][0]["total_sgd"] <= 40

    edited = client.patch(f"/api/ops/users/{bob}", json={"display_name": "Robert", "system_role": "admin"})
    assert edited.status_code == 200
    assert (edited.json()["display_name"], edited.json()["system_role"]) == ("Robert", "admin")
    with factory() as database:
        audit = database.scalars(select(AuditEvent).where(AuditEvent.action == "user.updated")).one()
        assert audit.details["before"] == {"display_name": "Bob", "system_role": "ordinary_user"}
    assert client.patch(f"/api/ops/users/{bob}", json={"system_role": "operator"}).status_code == 422

    me = client.get("/api/ops/users", params={"q": "ops@"}).json()["items"][0]["id"]
    assert client.patch(f"/api/ops/users/{me}", json={"system_role": "ordinary_user"}).status_code == 409
    assert client.get("/api/ops/users/999999").status_code == 404


def test_users_conversations_plans_and_accounts_can_be_deleted(console) -> None:
    client, factory = console
    bob = _second_account(factory)
    with factory() as database:
        household = database.scalar(select(HouseholdMembership.household_id).where(HouseholdMembership.user_id == bob))

    assert client.delete(f"/api/ops/users/{bob}/conversations").json() == {"deleted": 1}
    assert _count(factory, AgentSession, AgentSession.household_id == household) == 0
    assert client.delete(f"/api/ops/users/{bob}/plans").json() == {"deleted": 1}
    assert _count(factory, MealPlan, MealPlan.household_id == household) == 0

    assert client.delete(f"/api/ops/users/{bob}").status_code == 200
    assert client.get(f"/api/ops/users/{bob}").status_code == 404
    assert _count(factory, HouseholdMembership, HouseholdMembership.household_id == household) == 0
    assert _count(factory, AuditEvent, AuditEvent.target_type == "user") == 3

    me = client.get("/api/ops/users").json()["items"][0]["id"]
    assert client.delete(f"/api/ops/users/{me}").status_code == 409


def test_ordinary_accounts_cannot_reach_slice_two(console) -> None:
    client, factory = console
    with factory() as database:
        database.scalars(select(User)).one().system_role = "ordinary_user"
        database.commit()
    for path in (
        "/api/ops/replays",
        "/api/ops/config",
        "/api/ops/config/history",
        "/api/ops/experiments",
        "/api/ops/users",
    ):
        assert client.get(path).status_code == 404
    assert client.post("/api/ops/replay/planning/1").status_code == 404
    assert client.put("/api/ops/config/beam_width", json={"value": 4}).status_code == 404
