from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import get_password_adapter
from app.auth.authorization import SystemRole
from app.auth.passwords import Argon2PasswordAdapter, Argon2PasswordPolicy
from app.core.config import Settings, get_settings
from app.data.admin_accounts import ensure_admin_accounts, parse_admin_accounts
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.agent import AgentMessage, AgentRun, AgentRunCheckpoint, AgentSession
from app.models.platform import AuditEvent, HouseholdMembership, OperationRun, User
from app.products.provider import FairPriceProductProvider, ProductProviderError


@pytest.fixture
def operations_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    database_factory = sessionmaker(bind=engine, expire_on_commit=False)
    test_settings = Settings(
        app_name="MealCraft Test",
        app_version="9.9.9",
        environment="test",
        database_url="sqlite+pysqlite://",
        auth_cookie_secure=False,
        auth_session_ttl_hours=24,
        auth_last_seen_interval_seconds=0,
        auth_login_max_failures=2,
        auth_login_lock_minutes=15,
    )
    fast_password_adapter = Argon2PasswordAdapter(
        Argon2PasswordPolicy(
            version="argon2id-test-v1",
            time_cost=1,
            memory_cost_kib=8_192,
            parallelism=1,
            hash_length=16,
            salt_length=16,
        )
    )

    def override_database() -> Generator[Session, None, None]:
        with database_factory() as database:
            yield database

    app.dependency_overrides[get_db_session] = override_database
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_password_adapter] = lambda: fast_password_adapter
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "email": "operator@example.test",
                "display_name": "Operations Tester",
                "password": "correct-horse-battery-staple",
            },
        )
        assert response.status_code == 201
        yield client, database_factory
    app.dependency_overrides.clear()
    engine.dispose()


def _set_system_role(database_factory: sessionmaker, role: SystemRole) -> int:
    with database_factory() as database:
        user = database.scalars(select(User)).one()
        user.system_role = role.value
        database.commit()
        return user.id


def _add_run(database_factory: sessionmaker, **values) -> None:
    defaults = {
        "trace_id": "trace-default",
        "run_type": "evaluation",
        "status": "succeeded",
        "created_at": datetime.now(UTC),
    }
    defaults.update(values)
    with database_factory() as database:
        database.add(OperationRun(**defaults))
        database.commit()


@pytest.mark.parametrize("endpoint", ["/api/ops/overview", "/api/ops/runs"])
@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 200),
        (SystemRole.OPERATOR, 200),
        (SystemRole.ADMIN, 200),
    ],
)
def test_each_operations_endpoint_enforces_every_system_role(
    operations_client,
    endpoint: str,
    role: SystemRole,
    expected_status: int,
) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, role)

    response = client.get(endpoint)

    assert response.status_code == expected_status
    if role is SystemRole.ORDINARY_USER:
        assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("endpoint", ["/api/ops/overview", "/api/ops/runs"])
def test_operations_endpoints_require_authentication(operations_client, endpoint: str) -> None:
    _, _database_factory = operations_client

    with TestClient(app) as anonymous:
        response = anonymous.get(endpoint)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_household_owner_has_no_implicit_operations_access(operations_client) -> None:
    client, database_factory = operations_client
    with database_factory() as database:
        user = database.scalars(select(User)).one()
        membership = database.scalars(select(HouseholdMembership)).one()
        assert membership.role == "owner"
        assert user.system_role == SystemRole.ORDINARY_USER.value

    response = client.get("/api/ops/overview")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_runs_are_filtered_ordered_bounded_and_redacted(operations_client) -> None:
    client, database_factory = operations_client
    user_id = _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    _add_run(
        database_factory,
        trace_id="trace-old",
        run_type="evaluation",
        status="failed",
        error_code="OLD_FAILURE",
        created_at=now - timedelta(days=2),
    )
    _add_run(
        database_factory,
        trace_id="trace-newer",
        run_type="evaluation",
        status="failed",
        triggered_by_user_id=user_id,
        input_digest="a" * 64,
        code_commit="commit-new",
        catalog_version="catalog-v2",
        product_snapshot_version="products-v3",
        provider_mode="fixture",
        error_code="SAFE_CLASSIFICATION",
        error_detail="token=must-not-leak",
        warnings=["internal warning is not a list-field contract"],
        artifact_references=[{"secret": "must-not-leak"}],
        created_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=4),
        finished_at=now - timedelta(minutes=3, seconds=55),
    )
    _add_run(
        database_factory,
        trace_id="trace-newest",
        run_type="catalog_import",
        status="queued",
        created_at=now - timedelta(minutes=1),
    )

    response = client.get(
        "/api/ops/runs",
        params={
            "type": "evaluation",
            "status": "failed",
            "since": (now - timedelta(hours=1)).isoformat(),
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["trace_id"] for item in payload["items"]] == ["trace-newer"]
    assert payload["items"][0]["duration_seconds"] == 5.0
    assert payload["items"][0]["triggered_by_user_id"] == user_id
    serialized = response.text
    assert "must-not-leak" not in serialized
    assert "error_detail" not in serialized
    assert "artifact_references" not in serialized
    assert "warnings" not in serialized


def test_overview_reports_recorded_evidence_without_guessing(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.DATA_REVIEWER)
    now = datetime.now(UTC)
    _add_run(
        database_factory,
        trace_id="trace-queued",
        run_type="catalog_import",
        status="queued",
        provider_mode="live",
        code_commit="commit-current",
        catalog_version="catalog-current",
        product_snapshot_version="products-current",
        created_at=now - timedelta(minutes=3),
    )
    _add_run(
        database_factory,
        trace_id="trace-running",
        run_type="evaluation",
        status="running",
        provider_mode="fixture",
        created_at=now - timedelta(minutes=2),
    )
    _add_run(
        database_factory,
        trace_id="trace-failed",
        run_type="retrieval",
        status="failed",
        provider_mode="degraded",
        error_code="PROVIDER_TIMEOUT",
        created_at=now - timedelta(minutes=1),
    )
    _add_run(
        database_factory,
        trace_id="trace-old-failed",
        run_type="retrieval",
        status="failed",
        provider_mode="cache",
        error_code="OLD_FAILURE",
        created_at=now - timedelta(days=2),
    )

    response = client.get("/api/ops/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_status"] == "ok"
    assert payload["database_status"] == "connected"
    assert payload["service"] == "MealCraft Test"
    assert payload["app_version"] == "9.9.9"
    assert payload["latest_recorded_versions"] == {
        "code_commit": "commit-current",
        "catalog_version": "catalog-current",
        "product_snapshot_version": "products-current",
    }
    assert payload["runs"] == {
        "queued": 1,
        "running": 1,
        "failures_last_24_hours": {"PROVIDER_TIMEOUT": 1},
        "provider_modes_last_24_hours": {"degraded": 1, "fixture": 1, "live": 1},
    }


def test_operations_reads_do_not_add_or_change_evidence(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.OPERATOR)
    _add_run(database_factory, trace_id="trace-immutable")

    with database_factory() as database:
        before_runs = database.scalar(select(func.count()).select_from(OperationRun))
        before_audits = database.scalar(select(func.count()).select_from(AuditEvent))

    assert client.get("/api/ops/overview").status_code == 200
    assert client.get("/api/ops/runs").status_code == 200

    with database_factory() as database:
        assert database.scalar(select(func.count()).select_from(OperationRun)) == before_runs
        assert database.scalar(select(func.count()).select_from(AuditEvent)) == before_audits


def test_runs_reject_invalid_status_and_unbounded_limit(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)

    assert client.get("/api/ops/runs", params={"status": "invented"}).status_code == 422
    assert client.get("/api/ops/runs", params={"limit": 201}).status_code == 422


# --- Console endpoints (ADR-0047) ---


def _add_agent_run(database_factory: sessionmaker, *, created_at: datetime, status: str, parser: str) -> int:
    with database_factory() as database:
        household_id = database.scalars(select(HouseholdMembership.household_id)).first()
        session = AgentSession(household_id=household_id, parser_provider=parser, constraints={"household_size": 2})
        database.add(session)
        database.flush()
        database.add(AgentMessage(session_id=session.id, role="user", content="Dinners for two, S$90"))
        run = AgentRun(
            agent_session_id=session.id,
            idempotency_key=f"key-{session.id}",
            intent="plan_week",
            status=status,
            input_digest="b" * 64,
            context_version=1,
            model_config={"parser": parser, "parser_model": "gpt-test", "api_key": "sk-must-not-leak"},
            deadline_at=created_at + timedelta(minutes=2),
            created_at=created_at,
            started_at=created_at,
            completed_at=created_at + timedelta(seconds=3),
        )
        database.add(run)
        database.flush()
        database.add(
            AgentRunCheckpoint(agent_run_id=run.id, sequence=1, stage="parse", status="done", state_digest="c" * 64)
        )
        database.commit()
        return run.id


def _planning_trace(**values) -> list[dict]:
    trace = {
        "status": "optimal",
        "algorithm": "beam",
        "requested_pricing_mode": "fixture",
        "validation": {"passed": True, "checks": ["budget"]},
        "shopping_digest": "d" * 64,
        "evidence": "complete",
    }
    trace.update(values)
    return [{"kind": "planning_trace", "data": trace}]


def test_series_buckets_fourteen_days_with_planning_latency(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    _add_agent_run(database_factory, created_at=now, status="committed", parser="fixture")
    for index, seconds in enumerate((1, 2, 10)):
        _add_run(
            database_factory,
            trace_id=f"planning-{index}",
            run_type="planning",
            status="succeeded",
            provider_mode="fairprice,fixture",
            created_at=now,
            started_at=now,
            finished_at=now + timedelta(seconds=seconds),
        )
    _add_run(database_factory, trace_id="planning-old", run_type="planning", created_at=now - timedelta(days=20))

    response = client.get("/api/ops/overview/series")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["days"]) == 14
    today = payload["days"][-1]
    assert today["day"] == now.date().isoformat()
    assert today["agent_sessions"] == 1
    assert today["agent_runs"] == {"committed": 1}
    assert today["planning_runs"] == {"succeeded": 3}
    assert today["planning_median_seconds"] == 2.0
    assert today["planning_p90_seconds"] == 10.0
    assert payload["provider_modes"] == {"fairprice": 3, "fixture": 3}


def test_tasks_merge_both_kinds_and_page(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    _add_agent_run(database_factory, created_at=now - timedelta(minutes=2), status="failed", parser="openai")
    _add_run(database_factory, trace_id="planning-a", run_type="planning", created_at=now - timedelta(minutes=1))
    _add_run(database_factory, trace_id="eval-a", run_type="evaluation", created_at=now)

    everything = client.get("/api/ops/tasks").json()
    assert everything["total"] == 2
    assert [item["kind"] for item in everything["items"]] == ["planning", "agent"]

    second = client.get("/api/ops/tasks", params={"offset": 1, "limit": 1}).json()
    assert [item["kind"] for item in second["items"]] == ["agent"]

    failed = client.get("/api/ops/tasks", params={"type": "agent", "status": "failed"}).json()
    assert failed["total"] == 1
    assert failed["items"][0]["provider_mode"] == "openai"
    assert client.get("/api/ops/tasks", params={"type": "invented"}).status_code == 422


def test_task_detail_returns_stored_run_without_keys(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    run_id = _add_agent_run(database_factory, created_at=now, status="committed", parser="openai")
    _add_run(
        database_factory,
        trace_id="planning-detail",
        run_type="planning",
        status="failed",
        error_code="infeasible",
        error_detail="No week fits the budget.",
        artifact_references=_planning_trace(settings={"width": 4}, openai_api_key="sk-must-not-leak"),
        created_at=now,
    )
    with database_factory() as database:
        planning_id = database.scalar(select(OperationRun.id).where(OperationRun.trace_id == "planning-detail"))

    agent = client.get(f"/api/ops/tasks/agent/{run_id}")
    assert agent.status_code == 200
    agent_payload = agent.json()
    assert agent_payload["inputs"]["conversation"][0]["content"] == "Dinners for two, S$90"
    assert agent_payload["inputs"]["understood_constraints"] == {"household_size": 2}
    assert agent_payload["model_configuration"] == {"parser": "openai", "parser_model": "gpt-test"}
    assert agent_payload["trace"]["checkpoints"][0]["stage"] == "parse"
    assert agent_payload["timings"]["duration_seconds"] == 3.0

    planning = client.get(f"/api/ops/tasks/planning/{planning_id}")
    assert planning.status_code == 200
    planning_payload = planning.json()
    assert planning_payload["validation"] == {"passed": True, "checks": ["budget"]}
    assert planning_payload["evidence"]["shopping_digest"] == "d" * 64
    assert planning_payload["model_configuration"]["settings"] == {"width": 4}
    assert planning_payload["error_detail"] == "No week fits the budget."
    assert "digest remains" in planning_payload["inputs"]["note"]

    assert "must-not-leak" not in agent.text + planning.text
    assert client.get("/api/ops/tasks/planning/999999").status_code == 404


def test_services_report_configuration_and_recent_fallbacks(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    now = datetime.now(UTC)
    _add_agent_run(database_factory, created_at=now, status="degraded", parser="openai")
    _add_agent_run(database_factory, created_at=now, status="committed", parser="fixture")
    _add_run(
        database_factory,
        trace_id="planning-live",
        run_type="planning",
        provider_mode="fixture",
        artifact_references=_planning_trace(requested_pricing_mode="live"),
        created_at=now,
    )

    response = client.get("/api/ops/services")

    assert response.status_code == 200
    services = {item["name"]: item for item in response.json()["items"]}
    assert services["openai"]["configured"] is False
    assert services["openai"]["recent"] == {"window_days": 7, "calls": 1, "failures": 0, "fallbacks": 1}
    assert services["fairprice"]["recent"] == {"window_days": 7, "calls": 1, "failures": 0, "fallbacks": 1}
    assert services["youtube"]["recent"] is None


def test_live_checks_report_missing_keys_without_calling_out(operations_client) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)

    for name in ("openai", "youtube"):
        payload = client.post(f"/api/ops/services/{name}/check").json()
        assert payload["ok"] is False
        assert payload["error_kind"] == "not_configured"
    assert client.post("/api/ops/services/invented/check").status_code == 422


def test_fairprice_live_check_uses_the_provider(operations_client, monkeypatch) -> None:
    client, database_factory = operations_client
    _set_system_role(database_factory, SystemRole.ADMIN)
    calls = []

    def fake_search(self, query, *, limit):
        calls.append((query, limit, self.timeout_seconds))
        raise ProductProviderError("FairPrice request failed: timed out")

    monkeypatch.setattr(FairPriceProductProvider, "search", fake_search)

    payload = client.post("/api/ops/services/fairprice/check").json()

    assert calls == [("rice", 1, 10.0)]
    assert payload["ok"] is False
    assert payload["error_kind"] == "unavailable"
    assert "timed out" in payload["detail"]


def test_ordinary_user_cannot_reach_console_endpoints(operations_client) -> None:
    client, _ = operations_client
    for path in ("/api/ops/overview/series", "/api/ops/tasks", "/api/ops/services"):
        assert client.get(path).status_code == 404
    assert client.post("/api/ops/services/openai/check").status_code == 404


def test_admin_accounts_are_created_updated_and_can_sign_in(operations_client) -> None:
    client, database_factory = operations_client
    passwords = app.dependency_overrides[get_password_adapter]()
    accounts = parse_admin_accounts("ops@example.test:first-password-123:Ops One; second@example.test:pw-two-long-1")
    assert [account.display_name for account in accounts] == ["Ops One", "second@example.test"]

    with database_factory() as database:
        assert ensure_admin_accounts(database, accounts, passwords) == 2
    renamed = parse_admin_accounts("ops@example.test:changed-password-123:Ops Renamed")
    with database_factory() as database:
        ensure_admin_accounts(database, renamed, passwords)
        users = {user.normalized_email: user for user in database.scalars(select(User))}
    assert users["ops@example.test"].system_role == "admin"
    assert users["ops@example.test"].display_name == "Ops Renamed"
    assert users["second@example.test"].system_role == "admin"

    with TestClient(app) as admin:
        login = admin.post("/api/auth/login", json={"email": "ops@example.test", "password": "changed-password-123"})
        assert login.status_code == 200
        assert admin.get("/api/auth/me").json()["user"]["system_role"] == "admin"
        assert admin.get("/api/ops/tasks").status_code == 200
    with pytest.raises(ValueError):
        parse_admin_accounts("no-password@example.test")
