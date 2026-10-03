from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.platform import OperationRun, User
from app.models.recipe import Ingredient, Recipe
from app.repositories.operation_jobs import OperationJobRepository
from app.worker.handlers import (
    HandlerSpec,
    InvalidJobPayloadError,
    JobHandlerRegistry,
    UnknownJobTypeError,
    production_registry,
)
from app.worker.runtime import OperationWorker, WorkerPolicy


class SleepPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: float = Field(ge=0, le=5)


def sleep_handler(payload: dict, _database_url: str) -> None:
    time.sleep(SleepPayload.model_validate(payload).seconds)


def immediate_handler(payload: dict, _database_url: str) -> None:
    SleepPayload.model_validate(payload)


@pytest.fixture
def worker_database(tmp_path: Path):
    database_path = tmp_path / "worker.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield database_url, factory
    engine.dispose()


def _enqueue(factory: sessionmaker[Session], *, suffix: str, run_type: str, payload: dict) -> int:
    with factory() as session:
        actor = session.scalar(select(User).where(User.normalized_email == "worker@example.test"))
        if actor is None:
            actor = User(normalized_email="worker@example.test", display_name="Worker", system_role="admin")
            session.add(actor)
            session.flush()
        run, _ = OperationJobRepository(session).enqueue(
            trace_id=f"worker-{suffix}",
            run_type=run_type,
            triggered_by_user_id=actor.id,
            input_digest=suffix[0] * 64,
            job_payload=payload,
            idempotency_key=f"key-{suffix}",
        )
        session.commit()
        return run.id


def _worker(
    database_url: str,
    factory: sessionmaker[Session],
    *,
    registry: JobHandlerRegistry,
    timeout: float = 5,
    lease: float = 1,
    heartbeat: float = 0.1,
    max_attempts: int = 2,
    stop_event: Event | None = None,
) -> OperationWorker:
    return OperationWorker(
        session_factory=factory,
        database_url=database_url,
        registry=registry,
        policy=WorkerPolicy(
            poll_seconds=0.01,
            lease_seconds=lease,
            heartbeat_seconds=heartbeat,
            timeout_seconds=timeout,
            max_attempts=max_attempts,
        ),
        stop_event=stop_event,
    )


def test_registry_rejects_unknown_jobs_and_undeclared_arguments() -> None:
    registry = production_registry()

    with pytest.raises(UnknownJobTypeError):
        registry.prepare("shell", {"command": "whoami"})
    with pytest.raises(InvalidJobPayloadError):
        registry.prepare("catalog_import", {"source": "reference", "path": "../private"})
    with pytest.raises(InvalidJobPayloadError):
        registry.prepare("catalog_import", {"source": "release_v2", "force": True})


def test_unknown_job_fails_without_retrying(worker_database) -> None:
    database_url, factory = worker_database
    run_id = _enqueue(factory, suffix="a-unknown", run_type="arbitrary_command", payload={})

    assert _worker(database_url, factory, registry=production_registry()).run_once()

    with factory() as session:
        run = session.get(OperationRun, run_id)
        assert run is not None
        assert (run.status, run.attempt_count, run.error_code) == ("failed", 1, "job_type_not_registered")


def test_timeout_is_retried_only_to_the_attempt_limit(worker_database) -> None:
    database_url, factory = worker_database
    run_id = _enqueue(factory, suffix="b-timeout", run_type="sleep", payload={"seconds": 1})
    registry = JobHandlerRegistry({"sleep": HandlerSpec(payload_model=SleepPayload, handler=sleep_handler)})
    worker = _worker(database_url, factory, registry=registry, timeout=0.05)

    assert worker.run_once()
    with factory() as session:
        first = session.get(OperationRun, run_id)
        assert first is not None
        assert (first.status, first.attempt_count) == ("queued", 1)

    assert worker.run_once()
    with factory() as session:
        second = session.get(OperationRun, run_id)
        assert second is not None
        assert (second.status, second.attempt_count, second.error_code) == ("failed", 2, "job_timeout")


def test_heartbeat_keeps_a_slow_attempt_owned(worker_database) -> None:
    database_url, factory = worker_database
    run_id = _enqueue(factory, suffix="c-heartbeat", run_type="sleep", payload={"seconds": 0.5})
    registry = JobHandlerRegistry({"sleep": HandlerSpec(payload_model=SleepPayload, handler=sleep_handler)})

    assert _worker(
        database_url,
        factory,
        registry=registry,
        timeout=3,
        lease=0.25,
        heartbeat=0.05,
    ).run_once()

    with factory() as session:
        run = session.get(OperationRun, run_id)
        assert run is not None
        assert (run.status, run.attempt_count, run.lease_expires_at) == ("succeeded", 1, None)


def test_stopped_worker_leaves_job_for_lease_reclaim(worker_database) -> None:
    database_url, factory = worker_database
    run_id = _enqueue(factory, suffix="d-reclaim", run_type="restart_probe", payload={"seconds": 2})
    stop_event = Event()
    slow_registry = JobHandlerRegistry(
        {"restart_probe": HandlerSpec(payload_model=SleepPayload, handler=sleep_handler)}
    )
    first_worker = _worker(
        database_url,
        factory,
        registry=slow_registry,
        timeout=5,
        lease=0.3,
        heartbeat=0.05,
        stop_event=stop_event,
    )
    thread = Thread(target=first_worker.run_once)
    thread.start()

    deadline = time.monotonic() + 3
    observed_running = False
    while time.monotonic() < deadline:
        with factory() as session:
            if session.get(OperationRun, run_id).status == "running":
                observed_running = True
                break
        time.sleep(0.01)
    assert observed_running
    stop_event.set()
    thread.join(timeout=3)
    assert not thread.is_alive()

    time.sleep(0.35)
    resumed_registry = JobHandlerRegistry(
        {"restart_probe": HandlerSpec(payload_model=SleepPayload, handler=immediate_handler)}
    )
    assert _worker(database_url, factory, registry=resumed_registry).run_once()

    with factory() as session:
        run = session.get(OperationRun, run_id)
        assert run is not None
        assert (run.status, run.attempt_count) == ("succeeded", 2)


def test_cancelling_a_running_job_stops_the_worker_without_rewriting_history(worker_database) -> None:
    database_url, factory = worker_database
    run_id = _enqueue(factory, suffix="e-cancel", run_type="sleep", payload={"seconds": 2})
    registry = JobHandlerRegistry({"sleep": HandlerSpec(payload_model=SleepPayload, handler=sleep_handler)})
    worker = _worker(
        database_url,
        factory,
        registry=registry,
        timeout=5,
        lease=0.3,
        heartbeat=0.05,
    )
    thread = Thread(target=worker.run_once)
    thread.start()

    deadline = time.monotonic() + 3
    observed_running = False
    while time.monotonic() < deadline:
        with factory() as session:
            run = session.get(OperationRun, run_id)
            if run is not None and run.status == "running":
                observed_running = True
                break
        time.sleep(0.01)
    assert observed_running

    with factory() as session:
        cancelled = OperationJobRepository(session).cancel(run_id=run_id, now=datetime.now(UTC))
        session.commit()
        assert (cancelled.previous_status, cancelled.attempt_count) == ("running", 1)

    thread.join(timeout=3)
    assert not thread.is_alive()
    with factory() as session:
        run = session.get(OperationRun, run_id)
        assert run is not None
        assert (run.status, run.attempt_count, run.lease_expires_at) == ("cancelled", 1, None)


def test_reference_catalog_handler_is_idempotent_when_executed_twice(worker_database) -> None:
    database_url, factory = worker_database
    first_id = _enqueue(
        factory,
        suffix="f-catalog",
        run_type="catalog_import",
        payload={"source": "reference"},
    )
    second_id = _enqueue(
        factory,
        suffix="a-catalog-second",
        run_type="catalog_import",
        payload={"source": "reference"},
    )
    worker = _worker(database_url, factory, registry=production_registry(), timeout=30, lease=5, heartbeat=0.5)

    assert worker.run_once()
    assert worker.run_once()

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Ingredient)) == 34
        assert session.scalar(select(func.count()).select_from(Recipe)) == 30
        assert session.get(OperationRun, first_id).status == "succeeded"
        assert session.get(OperationRun, second_id).status == "succeeded"
