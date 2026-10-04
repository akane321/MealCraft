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
PLANNING_EXPERIMENT_REQUEST = {
    "evaluation": "planning-components",
    "label": "component sweep",
    "parameters": {"repeats": 2, "width": 16, "max_expansions": 500, "repair_rounds": 1},
    "confirm": True,
}


@pytest.fixture
def job_client(monkeypatch) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    # Synthetic evidence must not depend on whether this test runs in a Git checkout or a Docker image.
    monkeypatch.setenv("CODE_COMMIT", "0123456789abcdef0123456789abcdef01234567")
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


def _complete_planning_experiment(
    factory: sessionmaker[Session], run_id: int, *, passed_audit_count: int = 4, code_commit: str | None = None
) -> None:
    now = datetime.now(UTC)
    with factory() as database:
        run = database.get(OperationRun, run_id)
        data = dict(run.artifact_references[0]["data"])
        data["metrics"] = {"case_count": 5, "passed_audit_count": passed_audit_count}
        data["conditions"] = {
            **data["conditions"],
            "dataset": {
                **data["conditions"]["dataset"],
                "file_sha256": "b" * 64,
                "semantic_sha256": "c" * 64,
            },
            "code_source": {"sha256": "d" * 64},
            "product_snapshot_sha256": "e" * 64,
            "duration_seconds": 1.25,
            "failure_mechanisms": {"purchase_budget": 1},
            "conditions_complete": True,
        }
        failures = [] if passed_audit_count >= 4 else [{"code": "purchase_budget", "status": "failed"}]
        data["report"] = {
            "protocol": "planning-component-ablation-dev-v2",
            "runs": [
                {
                    "case_id": "budget-edge",
                    "preset": "beam",
                    "repeat": 0,
                    "status": "feasible" if not failures else "infeasible",
                    "failures": failures,
                }
            ],
        }
        run.artifact_references = [{"kind": "planning_experiment", "data": data}]
        if code_commit is not None:
            run.code_commit = code_commit
        run.status = "succeeded"
        run.started_at = now - timedelta(seconds=2)
        run.finished_at = now
        database.commit()


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


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 404),
        (SystemRole.OPERATOR, 404),
        (SystemRole.ADMIN, 201),
    ],
)
def test_every_role_is_checked_when_queueing_a_planning_experiment(
    job_client, role: SystemRole, expected_status: int
) -> None:
    client, factory = job_client
    _set_role(factory, role)

    response = client.post(
        "/api/ops/experiments",
        json=PLANNING_EXPERIMENT_REQUEST,
        headers={"Idempotency-Key": f"planning-role-{role.value}"},
    )

    assert response.status_code == expected_status
    if expected_status == 404:
        assert response.json() == {"detail": "Not Found"}
        assert _count(factory, OperationRun) == 0
        assert _count(factory, AuditEvent) == 0
    else:
        assert response.json()["status"] == "queued"


def test_planning_experiment_is_idempotent_and_records_reproducible_inputs(job_client) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, SystemRole.ADMIN)
    headers = {"Idempotency-Key": "planning-repeat"}

    missing_key = client.post("/api/ops/experiments", json=PLANNING_EXPERIMENT_REQUEST)
    assert missing_key.status_code == 422
    assert missing_key.json()["detail"] == "Idempotency-Key is required for planning experiments"

    first = client.post("/api/ops/experiments", json=PLANNING_EXPERIMENT_REQUEST, headers=headers)
    replay = client.post("/api/ops/experiments", json=PLANNING_EXPERIMENT_REQUEST, headers=headers)

    assert (first.status_code, replay.status_code) == (201, 200)
    assert first.json()["id"] == replay.json()["id"]
    conditions = first.json()["conditions"]
    assert conditions["dataset"]["registry_key"] == "planning-components"
    assert conditions["seed"] is None
    assert conditions["repeats"] == 2
    assert conditions["paid_model"] == {"used": False, "budget_usd": 0, "usage_usd": 0}
    assert conditions["conditions_complete"] is False
    with factory() as database:
        run = database.get(OperationRun, first.json()["id"])
        assert run.triggered_by_user_id == actor_id
        assert run.run_type == "planning_experiment"
        assert run.provider_mode == "fixture"
        assert len(run.input_digest) == 64
        audit = database.scalars(select(AuditEvent)).one()
        assert audit.action == "planning_experiment.queued"
        assert "path" not in audit.details


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 404),
        (SystemRole.OPERATOR, 404),
        (SystemRole.ADMIN, 200),
    ],
)
def test_every_role_is_checked_when_opening_experiment_evidence(
    job_client, role: SystemRole, expected_status: int
) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)
    queued = client.post(
        "/api/ops/experiments",
        json=PLANNING_EXPERIMENT_REQUEST,
        headers={"Idempotency-Key": f"detail-{role.value}"},
    )
    run_id = queued.json()["id"]
    _complete_planning_experiment(factory, run_id)
    _set_role(factory, role)

    response = client.get(f"/api/ops/experiments/{run_id}")

    assert response.status_code == expected_status
    if expected_status == 404:
        assert response.json() == {"detail": "Not Found"}
    else:
        detail = response.json()
        assert detail["reproducibility"] == {
            "complete": True,
            "citation_allowed": True,
            "claim_scope": "developer_diagnostic_only",
            "missing": [],
            "warnings": ["Developer diagnostics do not support held-out or production-performance claims."],
        }
        assert detail["report"]["protocol"] == "planning-component-ablation-dev-v2"
        assert detail["conditions"]["failure_mechanisms"] == {"purchase_budget": 1}


def test_experiment_detail_rejects_non_experiment_rows(job_client) -> None:
    client, factory = job_client
    actor_id = _set_role(factory, SystemRole.ADMIN)
    job_id = _enqueue(factory, actor_id, suffix="not-an-experiment")

    response = client.get(f"/api/ops/experiments/{job_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Experiment not found"}


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        (SystemRole.ORDINARY_USER, 404),
        (SystemRole.DATA_REVIEWER, 404),
        (SystemRole.OPERATOR, 404),
        (SystemRole.ADMIN, 200),
    ],
)
def test_every_role_is_checked_when_comparing_experiments(job_client, role: SystemRole, expected_status: int) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)
    first = client.post(
        "/api/ops/experiments",
        json=PLANNING_EXPERIMENT_REQUEST,
        headers={"Idempotency-Key": f"compare-a-{role.value}"},
    ).json()
    second_payload = {
        **PLANNING_EXPERIMENT_REQUEST,
        "label": "wider beam",
        "parameters": {**PLANNING_EXPERIMENT_REQUEST["parameters"], "width": 32},
    }
    second = client.post(
        "/api/ops/experiments",
        json=second_payload,
        headers={"Idempotency-Key": f"compare-b-{role.value}"},
    ).json()
    _complete_planning_experiment(factory, first["id"], passed_audit_count=3)
    _complete_planning_experiment(factory, second["id"], passed_audit_count=4)
    _set_role(factory, role)

    response = client.get(f"/api/ops/experiments/compare?ids={first['id']},{second['id']}")

    assert response.status_code == expected_status
    if expected_status == 404:
        assert response.json() == {"detail": "Not Found"}
    else:
        comparison = response.json()
        assert comparison["compatible"] is True
        assert comparison["reasons"] == []
        assert next(row for row in comparison["metrics"] if row["key"] == "passed_audit_count")["delta"] == 1
        assert next(row for row in comparison["configurations"] if row["key"] == "width")["matches"] is False
        assert comparison["case_differences"] == [
            {
                "case_id": "budget-edge",
                "condition": "beam repeat 0",
                "a_status": "infeasible",
                "b_status": "feasible",
                "failures_gained": [],
                "failures_lost": ["purchase_budget"],
            }
        ]
        assert comparison["claim_scope"] == "developer_diagnostic_only"


@pytest.mark.parametrize("drift", ["code_commit", "code_source"])
def test_experiment_comparison_suppresses_deltas_when_evidence_drifted(job_client, drift: str) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)
    run_ids = []
    for suffix in ("drift-a", "drift-b"):
        response = client.post(
            "/api/ops/experiments",
            json={**PLANNING_EXPERIMENT_REQUEST, "label": suffix},
            headers={"Idempotency-Key": suffix},
        )
        run_ids.append(response.json()["id"])
    _complete_planning_experiment(factory, run_ids[0], passed_audit_count=3, code_commit="a" * 40)
    _complete_planning_experiment(
        factory, run_ids[1], passed_audit_count=4, code_commit=("b" if drift == "code_commit" else "a") * 40
    )
    if drift == "code_source":
        with factory() as database:
            run = database.get(OperationRun, run_ids[1])
            artifact = {**run.artifact_references[0]}
            data = {**artifact["data"]}
            data["conditions"] = {**data["conditions"], "code_source": {"sha256": "f" * 64}}
            run.artifact_references = [{**artifact, "data": data}]
            database.commit()

    response = client.get(f"/api/ops/experiments/compare?ids={run_ids[0]},{run_ids[1]}")

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["compatible"] is False
    assert comparison["reasons"] == [
        "Code revision differs or is missing."
        if drift == "code_commit"
        else "Implementation fingerprint differs or is missing."
    ]
    assert all(row["delta"] is None for row in comparison["metrics"])
    assert comparison["claim_scope"] == "not_comparable"


@pytest.mark.parametrize(
    "payload",
    [
        {**PLANNING_EXPERIMENT_REQUEST, "confirm": False},
        {**PLANNING_EXPERIMENT_REQUEST, "evaluation": "heldout-planning"},
        {**PLANNING_EXPERIMENT_REQUEST, "overrides": {"dataset": "private.json"}},
        {**PLANNING_EXPERIMENT_REQUEST, "parameters": {"width": 0}},
        {
            **PLANNING_EXPERIMENT_REQUEST,
            "evaluation": "planning-final-gate",
            "parameters": {"repeats": 2},
        },
    ],
)
def test_planning_experiment_rejects_unregistered_or_unsafe_inputs(job_client, payload: dict) -> None:
    client, factory = job_client
    _set_role(factory, SystemRole.ADMIN)

    response = client.post(
        "/api/ops/experiments",
        json=payload,
        headers={"Idempotency-Key": "invalid-planning"},
    )

    assert response.status_code == 422
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
