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
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.platform import AuditEvent, HouseholdMembership, OperationRun, User


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
