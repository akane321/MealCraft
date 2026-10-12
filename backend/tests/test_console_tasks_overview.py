"""Console tasks, overview and services (ADR-0047): what a turn was given, Singapore days, what failed."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select

from app.auth.authorization import SystemRole
from app.core.clock import SINGAPORE
from app.core.paths import data_root
from app.models.agent import AgentMessage, AgentRun
from app.models.meal_plan import MealPlan
from app.models.recipe import CatalogImport
from app.planning.grocery_estimator import RELEASE_SNAPSHOT_FILE
from tests.test_operations_api import _add_agent_run, _add_run, _set_system_role, operations_client  # noqa: F401
from tests.test_operations_console_api import _planning_run_ids, console  # noqa: F401


def _singapore_midnight() -> datetime:
    return datetime.combine(datetime.now(SINGAPORE).date(), time.min, SINGAPORE)


# --- Tasks: an assistant turn shows its own input ---


def test_an_assistant_turn_shows_what_it_was_given_not_the_conversation_now(console) -> None:  # noqa: F811
    client, _ = console
    created = client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    budget = client.post(f"/api/agent/sessions/{created['id']}/messages", json={"message": "Budget S$120 for the week"})
    client.post(f"/api/agent/sessions/{created['id']}/messages", json={"message": "Cook in under 30 minutes"})

    first = client.get(f"/api/ops/tasks/agent/{created['latest_run']['id']}").json()["inputs"]
    second = client.get(f"/api/ops/tasks/agent/{budget.json()['latest_run']['id']}").json()["inputs"]

    # Each turn shows the messages up to its own reply and the constraints it produced, not later ones.
    assert [item["content"] for item in first["conversation"]] == [item["content"] for item in created["messages"]]
    assert first["understood_constraints"]["weekly_budget_sgd"] is None
    assert first["understood_constraints"]["max_cooking_time_minutes"] == 240
    assert [item["content"] for item in second["conversation"]] == [
        item["content"] for item in budget.json()["messages"]
    ]
    assert second["constraints_before"] == first["understood_constraints"]
    assert second["understood_constraints"]["weekly_budget_sgd"] == 120
    assert second["understood_constraints"]["max_cooking_time_minutes"] == 240
    assert "conversation_now" not in first


def test_a_run_without_its_own_record_labels_the_conversation_now(operations_client) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    run_id = _add_agent_run(database_factory, created_at=now, status="committed", parser="fixture")
    with database_factory() as database:
        session_id = database.scalar(select(AgentRun.agent_session_id).where(AgentRun.id == run_id))
        # A later turn's message, sent after this run ended.
        database.add(
            AgentMessage(
                session_id=session_id, role="user", content="Make it vegetarian", created_at=now + timedelta(hours=1)
            )
        )
        database.commit()

    inputs = client.get(f"/api/ops/tasks/agent/{run_id}").json()["inputs"]

    assert [item["content"] for item in inputs["conversation"]] == ["Dinners for two, S$90"]
    assert "understood_constraints" not in inputs
    assert inputs["conversation_now"] == {"constraints": {"household_size": 2}, "missing_fields": []}
    assert "no record of its own input" in inputs["note"]


# --- Tasks and overview: Singapore days ---


def test_since_without_an_offset_is_midnight_in_singapore(operations_client) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    midnight = _singapore_midnight()
    for name, moment in (
        ("early-today", midnight + timedelta(minutes=30)),
        ("late-yesterday", midnight - timedelta(minutes=30)),
    ):
        _add_run(database_factory, trace_id=name, run_type="planning", created_at=moment.astimezone(UTC))
    day = midnight.date().isoformat()

    for since in (f"{day}T00:00:00", f"{day}T00:00:00+08:00"):
        page = client.get("/api/ops/tasks", params={"since": since}).json()
        assert page["total"] == 1, since
    assert client.get("/api/ops/runs", params={"since": f"{day}T00:00:00"}).json()["total"] == 1


def test_series_counts_a_run_on_the_singapore_day_it_happened(operations_client) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    # 00:30 in Singapore is still the day before in UTC.
    early = (_singapore_midnight() + timedelta(minutes=30)).astimezone(UTC)
    _add_run(database_factory, trace_id="early", run_type="planning", created_at=early)

    today = client.get("/api/ops/overview/series").json()["days"][-1]

    assert today["day"] == datetime.now(SINGAPORE).date().isoformat()
    assert today["planning_runs"] == {"succeeded": 1}


# --- Overview: assistant turns and versions ---


def test_overview_counts_assistant_turns_in_flight_and_failed(operations_client) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    _add_agent_run(database_factory, created_at=now, status="running", parser="fixture")
    refused = _add_agent_run(database_factory, created_at=now, status="failed", parser="fixture")
    planner = _add_agent_run(database_factory, created_at=now, status="failed", parser="fixture")
    old = _add_agent_run(database_factory, created_at=now - timedelta(days=2), status="failed", parser="fixture")
    with database_factory() as database:
        for run_id, code in ((refused, "SESSION_NOT_READY"), (planner, "ProductPlanningError"), (old, "OLD")):
            database.get(AgentRun, run_id).error_code = code
        database.commit()
    # The planner's failure is recorded once, by the planning run the turn started.
    _add_run(
        database_factory, trace_id="planning-failed", run_type="planning", status="failed", error_code="needs_data"
    )

    runs = client.get("/api/ops/overview").json()["runs"]

    assert runs["running"] == 1
    assert runs["failures_last_24_hours"] == {"needs_data": 1, "assistant: SESSION_NOT_READY": 1}


def test_overview_names_the_loaded_release_and_running_commit(operations_client, monkeypatch) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    monkeypatch.setenv("CODE_COMMIT", "commit-running")
    now = datetime.now(UTC)
    with database_factory() as database:
        database.add_all(
            [
                CatalogImport(
                    release_version="v2.1", digest="a" * 64, recipe_count=1, ingredient_count=1, imported_at=now
                ),
                CatalogImport(
                    release_version="__catalog_refresh__",
                    digest="b" * 64,
                    recipe_count=1,
                    ingredient_count=1,
                    imported_at=now + timedelta(minutes=1),
                ),
            ]
        )
        database.commit()
    # A planning run's versions are digests of its own candidates and prices, not a release.
    _add_run(
        database_factory,
        trace_id="planning-digest",
        run_type="planning",
        catalog_version="1b1cd88c" * 8,
        product_snapshot_version="68294a0b" * 8,
    )
    release = json.loads((data_root() / RELEASE_SNAPSHOT_FILE).read_text(encoding="utf-8"))["snapshot_version"]

    versions = client.get("/api/ops/overview").json()["latest_recorded_versions"]

    assert versions == {"code_commit": "commit-running", "catalog_version": "v2.1", "product_snapshot_version": release}


# --- Services: OpenAI failures ---


def test_openai_failures_count_failed_model_requests_only(operations_client) -> None:  # noqa: F811
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    # The planner failed after the model answered: not an OpenAI failure.
    _add_agent_run(database_factory, created_at=now, status="failed", parser="openai", used_llm_calls=1)
    # A plan asked for too early sends no request at all.
    _add_agent_run(database_factory, created_at=now, status="failed", parser="openai")
    _add_agent_run(
        database_factory, created_at=now, status="degraded", parser="openai", used_llm_calls=2, fell_back=True
    )

    openai = next(item for item in client.get("/api/ops/services").json()["items"] if item["name"] == "openai")

    assert openai["recent"]["runs"] == 3
    assert openai["recent"]["failures"] == 1
    assert openai["recent"]["fallbacks"] == 1


# --- Tasks: a planning run's warnings ---


def test_planning_run_shows_the_warnings_of_the_plan_it_saved(console) -> None:  # noqa: F811
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
    assert plan.json()["warnings"]
    (run_id,) = _planning_run_ids(factory)

    assert client.get(f"/api/ops/tasks/planning/{run_id}").json()["warnings"] == plan.json()["warnings"]

    # Once the plan is changed its warnings are the change's, no longer this run's.
    with factory() as database:
        database.get(MealPlan, plan.json()["id"]).revision = 2
        database.commit()
    assert client.get(f"/api/ops/tasks/planning/{run_id}").json()["warnings"] == []
