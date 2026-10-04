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
from app.models.platform import AuditEvent, OperationRun, User
from app.repositories.operation_jobs import OperationJobRepository

JOB_REQUEST = {"name": "catalog_import", "arguments": {"source": "reference"}, "confirm": True}


@pytest.fixture
def job_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(environment="test", database_url="sqlite+pysqlite://", auth_cookie_secure=False)
    password_adapter = Argon2PasswordAdapter(
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
        with factory() as database:
            yield database

    app.dependency_overrides[get_db_session] = override_database
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_password_adapter] = lambda: password_adapter
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "jobs@example.test",
                "display_name": "Job operator",
                "password": "correct-horse-battery-staple",
            },
        )
        assert registered.status_code == 201
        client.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def _set_role(factory: sessionmaker[Session], role: SystemRole) -> int:
    with factory() as database:
        user = database.scalars(select(User)).one()
        user.system_role = role.value
        database.commit()
        return user.id


def _enqueue(factory: sessionmaker[Session], actor_id: int, *, suffix: str = "target") -> int:
    with factory() as database:
        run, _ = OperationJobRepository(database).enqueue(
            trace_id=f"job-{suffix}",
            run_type="catalog_import",
            triggered_by_user_id=actor_id,
            input_digest="a" * 64,
            job_payload={"source": "reference"},
            idempotency_key=f"key-{suffix}",
        )
        database.commit()
        return run.id


def _count(factory: sessionmaker[Session], model) -> int:
    with factory() as database:
        return database.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 404),
        (SystemRole.OPERATOR, 404),
        (SystemRole.ADMIN, 201),
    ],
)
def test_every_role_is_checked_when_enqueuing(job_client, role: SystemRole, expected_status: int) -> None:
    client, factory = job_client
    _set_role(factory, role)

    response = client.post("/api/ops/jobs", json=JOB_REQUEST, headers={"Idempotency-Key": "role-check"})

    assert response.status_code == expected_status
    if expected_status == 404:
        assert response.json() == {"detail": "Not Found"}
        assert _count(factory, OperationRun) == 0
        assert _count(factory, AuditEvent) == 0


@pytest.mark.parametrize("role", [SystemRole.ORDINARY_USER, SystemRole.DATA_REVIEWER, SystemRole.OPERATOR])
def test_denied_roles_always_receive_a_generic_not_found(job_client, role: SystemRole) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, role)
    run_id = _enqueue(factory, actor_id, suffix=f"hidden-{role.value}")

    enqueue = client.post(
        "/api/ops/jobs",
        json={"name": "shell", "arguments": {"command": "whoami"}},
        headers={"X-CSRF-Token": "invalid"},
    )
    cancel = client.post(
        f"/api/ops/jobs/{run_id}/cancel",
        json={"confirm": False, "unexpected": "field"},
        headers={"X-CSRF-Token": "invalid"},
    )

    assert enqueue.status_code == 404
    assert enqueue.json() == {"detail": "Not Found"}
    assert cancel.status_code == 404
    assert cancel.json() == {"detail": "Not Found"}
    with factory() as database:
        assert database.get(OperationRun, run_id).status == "queued"
        assert database.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_enqueue_requires_authentication_csrf_confirmation_and_a_key(job_client) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)

    with TestClient(app) as anonymous:
        assert (
            anonymous.post("/api/ops/jobs", json=JOB_REQUEST, headers={"Idempotency-Key": "anonymous"}).status_code
            == 401
        )
    assert (
        client.post(
            "/api/ops/jobs",
            json=JOB_REQUEST,
            headers={"Idempotency-Key": "no-csrf", "X-CSRF-Token": ""},
        ).status_code
        == 403
    )
    assert client.post("/api/ops/jobs", json=JOB_REQUEST).status_code == 422
    assert (
        client.post(
            "/api/ops/jobs",
            json={"name": "catalog_import", "arguments": {"source": "reference"}},
            headers={"Idempotency-Key": "no-confirmation"},
        ).status_code
        == 422
    )
    assert _count(factory, OperationRun) == 0
    assert _count(factory, AuditEvent) == 0


def test_enqueue_is_idempotent_and_adds_one_safe_audit_event(job_client) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, SystemRole.ADMIN)
    headers = {"Idempotency-Key": "catalog-release-2026-10-03"}

    first = client.post("/api/ops/jobs", json=JOB_REQUEST, headers=headers)
    replay = client.post("/api/ops/jobs", json=JOB_REQUEST, headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["created"] is True
    assert replay.json()["created"] is False
    with factory() as database:
        run = database.scalars(select(OperationRun).where(OperationRun.run_type == "catalog_import")).one()
        audit = database.scalars(select(AuditEvent)).one()
        assert run.triggered_by_user_id == actor_id
        assert run.status == "queued"
        assert run.job_payload == {"source": "reference"}
        assert len(run.input_digest) == 64
        assert audit.action == "operation_job.enqueued"
        assert audit.target_id == str(run.id)
        assert audit.details == {
            "operation_run_id": run.id,
            "job_name": "catalog_import",
            "source": "reference",
        }
        assert audit.after_digest and len(audit.after_digest) == 64


def test_enqueue_rejects_key_reuse_and_arbitrary_execution_fields(job_client) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)
    headers = {"Idempotency-Key": "same-key"}
    assert client.post("/api/ops/jobs", json=JOB_REQUEST, headers=headers).status_code == 201

    conflict = client.post(
        "/api/ops/jobs",
        json={"name": "catalog_import", "arguments": {"source": "release_v2"}, "confirm": True},
        headers=headers,
    )
    arbitrary = client.post(
        "/api/ops/jobs",
        json={
            "name": "catalog_import",
            "arguments": {"source": "reference", "path": "../private", "sql": "select 1"},
            "confirm": True,
        },
        headers={"Idempotency-Key": "unsafe"},
    )
    shell = client.post(
        "/api/ops/jobs",
        json={"name": "shell", "arguments": {"command": "whoami"}, "confirm": True},
        headers={"Idempotency-Key": "shell"},
    )

    assert conflict.status_code == 409
    assert arbitrary.status_code == 422
    assert shell.status_code == 422
    assert _count(factory, OperationRun) == 1
    assert _count(factory, AuditEvent) == 1


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 404),
        (SystemRole.OPERATOR, 404),
        (SystemRole.ADMIN, 201),
    ],
)
def test_every_role_is_checked_when_cancelling(job_client, role: SystemRole, expected_status: int) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, role)
    run_id = _enqueue(factory, actor_id, suffix=role.value)

    response = client.post(f"/api/ops/jobs/{run_id}/cancel", json={"confirm": True})

    assert response.status_code == expected_status
    with factory() as database:
        target = database.get(OperationRun, run_id)
        if expected_status == 404:
            assert response.json() == {"detail": "Not Found"}
            assert target.status == "queued"
            assert database.scalar(select(func.count()).select_from(AuditEvent)) == 0
        else:
            assert target.status == "cancelled"
            assert target.finished_at is not None
            assert response.json()["previous_status"] == "queued"


def test_cancel_appends_a_command_and_audit_and_fences_the_worker(job_client) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, SystemRole.ADMIN)
    run_id = _enqueue(factory, actor_id)
    now = datetime.now(UTC)
    with factory() as database:
        claimed = OperationJobRepository(database).claim_next(
            now=now,
            lease_duration=timedelta(seconds=30),
            max_attempts=3,
        )
        database.commit()
        assert claimed is not None

    response = client.post(f"/api/ops/jobs/{run_id}/cancel", json={"confirm": True})

    assert response.status_code == 201
    with factory() as database:
        target = database.get(OperationRun, run_id)
        cancellation = database.get(OperationRun, response.json()["id"])
        audit = database.scalars(select(AuditEvent)).one()
        assert (target.status, target.lease_expires_at, target.attempt_count) == ("cancelled", None, 1)
        assert cancellation.run_type == "job_cancellation"
        assert cancellation.status == "succeeded"
        assert cancellation.idempotency_key is None
        assert cancellation.job_payload == {"target_run_id": run_id}
        assert audit.action == "operation_job.cancelled"
        assert audit.details == {
            "target_run_id": run_id,
            "previous_status": "running",
            "target_status": "cancelled",
            "attempt_count": 1,
            "cancellation_run_id": cancellation.id,
        }
        assert not OperationJobRepository(database).complete(
            run_id=run_id,
            attempt_count=1,
            now=now + timedelta(seconds=1),
        )
        assert (
            OperationJobRepository(database).claim_next(
                now=now + timedelta(seconds=31),
                lease_duration=timedelta(seconds=30),
                max_attempts=3,
            )
            is None
        )


def test_terminal_or_non_job_runs_cannot_be_cancelled(job_client) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, SystemRole.ADMIN)
    run_id = _enqueue(factory, actor_id)
    with factory() as database:
        run = database.get(OperationRun, run_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        evidence = OperationRun(trace_id="planning-evidence", run_type="planning", status="succeeded")
        database.add(evidence)
        database.commit()
        evidence_id = evidence.id

    assert client.post(f"/api/ops/jobs/{run_id}/cancel", json={"confirm": True}).status_code == 409
    assert client.post(f"/api/ops/jobs/{evidence_id}/cancel", json={"confirm": True}).status_code == 404
    assert _count(factory, OperationRun) == 2
    assert _count(factory, AuditEvent) == 0
