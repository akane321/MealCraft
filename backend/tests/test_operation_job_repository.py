from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.platform import OperationRun, User
from app.repositories.operation_jobs import JobIdempotencyConflictError, OperationJobRepository

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
LEASE = timedelta(seconds=30)


@pytest.fixture
def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _admin(database: Session, email: str = "worker@example.test") -> User:
    actor = User(normalized_email=email, display_name="Worker test", system_role="admin")
    database.add(actor)
    database.flush()
    return actor


def _enqueue(
    database: Session,
    *,
    actor_id: int,
    suffix: str,
    digest: str = "a" * 64,
) -> OperationRun:
    run, created = OperationJobRepository(database).enqueue(
        trace_id=f"job-{suffix}",
        run_type="catalog_import",
        triggered_by_user_id=actor_id,
        input_digest=digest,
        job_payload={"release": suffix},
        idempotency_key=f"request-{suffix}",
        code_commit="f" * 40,
    )
    assert created
    database.commit()
    return run


def test_enqueue_replays_same_input_and_rejects_conflicting_input(database: Session) -> None:
    actor = _admin(database)
    first = _enqueue(database, actor_id=actor.id, suffix="v2")
    repository = OperationJobRepository(database)

    replay, created = repository.enqueue(
        trace_id="unused-trace",
        run_type="catalog_import",
        triggered_by_user_id=actor.id,
        input_digest="a" * 64,
        job_payload={"release": "v2"},
        idempotency_key="request-v2",
    )

    assert not created
    assert replay.id == first.id
    assert len(database.scalars(select(OperationRun)).all()) == 1
    with pytest.raises(JobIdempotencyConflictError):
        repository.enqueue(
            trace_id="another-unused-trace",
            run_type="catalog_import",
            triggered_by_user_id=actor.id,
            input_digest="b" * 64,
            job_payload={"release": "v3"},
            idempotency_key="request-v2",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("trace_id", "", "trace_id"),
        ("run_type", "", "run_type"),
        ("input_digest", "not-a-digest", "SHA-256"),
        ("job_payload", [], "prevalidated object"),
        ("idempotency_key", "", "idempotency_key"),
    ],
)
def test_enqueue_rejects_malformed_job_metadata(database: Session, field: str, value, message: str) -> None:
    actor = _admin(database)
    payload = {
        "trace_id": "valid-trace",
        "run_type": "catalog_import",
        "triggered_by_user_id": actor.id,
        "input_digest": "a" * 64,
        "job_payload": {},
        "idempotency_key": "valid-key",
    }
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        OperationJobRepository(database).enqueue(**payload)


def test_claim_is_leased_once_until_it_expires(database: Session) -> None:
    actor = _admin(database)
    queued = _enqueue(database, actor_id=actor.id, suffix="once")
    repository = OperationJobRepository(database)

    first = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=3)
    database.commit()
    assert first is not None
    assert (first.run_id, first.attempt_count) == (queued.id, 1)
    assert first.payload == {"release": "once"}
    assert repository.claim_next(now=NOW + timedelta(seconds=10), lease_duration=LEASE, max_attempts=3) is None

    reclaimed = repository.claim_next(now=NOW + LEASE, lease_duration=LEASE, max_attempts=3)
    database.commit()
    assert reclaimed is not None
    assert (reclaimed.run_id, reclaimed.attempt_count) == (queued.id, 2)


def test_claim_ignores_non_job_operation_runs(database: Session) -> None:
    database.add(OperationRun(trace_id="planning-queued", run_type="planning", status="queued"))
    database.commit()

    assert OperationJobRepository(database).claim_next(now=NOW, lease_duration=LEASE, max_attempts=3) is None
    planning = database.scalar(select(OperationRun).where(OperationRun.trace_id == "planning-queued"))
    assert planning is not None
    assert planning.status == "queued"
    assert planning.attempt_count == 0


def test_attempt_count_fences_a_worker_after_reclaim(database: Session) -> None:
    actor = _admin(database)
    _enqueue(database, actor_id=actor.id, suffix="fenced")
    repository = OperationJobRepository(database)
    stale = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=3)
    database.commit()
    assert stale is not None
    current = repository.claim_next(now=NOW + LEASE, lease_duration=LEASE, max_attempts=3)
    database.commit()
    assert current is not None

    assert (
        repository.renew_lease(
            run_id=stale.run_id,
            attempt_count=stale.attempt_count,
            now=NOW + LEASE + timedelta(seconds=1),
            lease_duration=LEASE,
        )
        is None
    )
    assert not repository.complete(
        run_id=stale.run_id,
        attempt_count=stale.attempt_count,
        now=NOW + LEASE + timedelta(seconds=1),
    )
    assert repository.complete(
        run_id=current.run_id,
        attempt_count=current.attempt_count,
        now=NOW + LEASE + timedelta(seconds=1),
    )
    database.commit()
    finished = database.get(OperationRun, current.run_id)
    assert finished is not None
    assert finished.status == "succeeded"
    assert finished.lease_expires_at is None


def test_renewal_requires_the_current_unexpired_attempt(database: Session) -> None:
    actor = _admin(database)
    _enqueue(database, actor_id=actor.id, suffix="renew")
    repository = OperationJobRepository(database)
    lease = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=3)
    database.commit()
    assert lease is not None

    renewed = repository.renew_lease(
        run_id=lease.run_id,
        attempt_count=lease.attempt_count,
        now=NOW + timedelta(seconds=10),
        lease_duration=LEASE,
    )
    database.commit()
    assert renewed == NOW + timedelta(seconds=40)
    assert database.get(OperationRun, lease.run_id).lease_expires_at.replace(tzinfo=UTC) == renewed
    assert (
        repository.renew_lease(
            run_id=lease.run_id,
            attempt_count=lease.attempt_count,
            now=renewed,
            lease_duration=LEASE,
        )
        is None
    )


def test_failure_requeues_until_the_attempt_limit(database: Session) -> None:
    actor = _admin(database)
    _enqueue(database, actor_id=actor.id, suffix="retry")
    repository = OperationJobRepository(database)

    first = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=2)
    assert first is not None
    assert (
        repository.fail_or_retry(
            run_id=first.run_id,
            attempt_count=first.attempt_count,
            now=NOW + timedelta(seconds=1),
            max_attempts=2,
            error_code="temporary_provider_failure",
        )
        == "queued"
    )
    second = repository.claim_next(now=NOW + timedelta(seconds=2), lease_duration=LEASE, max_attempts=2)
    assert second is not None
    assert second.attempt_count == 2
    assert (
        repository.fail_or_retry(
            run_id=second.run_id,
            attempt_count=second.attempt_count,
            now=NOW + timedelta(seconds=3),
            max_attempts=2,
            error_code="temporary_provider_failure",
        )
        == "failed"
    )
    database.commit()

    failed = database.get(OperationRun, second.run_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "temporary_provider_failure"
    assert failed.warnings == ["attempt 1 failed (temporary_provider_failure); retry queued"]


def test_failure_rejects_free_form_error_details(database: Session) -> None:
    with pytest.raises(ValueError, match="controlled lowercase identifier"):
        OperationJobRepository(database).fail_or_retry(
            run_id=1,
            attempt_count=1,
            now=NOW,
            max_attempts=2,
            error_code="Authorization: Bearer secret-token",
        )


def test_expired_attempt_at_limit_is_failed_before_next_job_is_claimed(database: Session) -> None:
    actor = _admin(database)
    exhausted = _enqueue(database, actor_id=actor.id, suffix="exhausted")
    next_run = _enqueue(database, actor_id=actor.id, suffix="next")
    repository = OperationJobRepository(database)
    first = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=1)
    database.commit()
    assert first is not None
    assert first.run_id == exhausted.id

    following = repository.claim_next(now=NOW + LEASE, lease_duration=LEASE, max_attempts=1)
    database.commit()
    assert following is not None
    assert following.run_id == next_run.id
    failed = database.get(OperationRun, exhausted.id)
    assert failed is not None
    assert (failed.status, failed.error_code) == ("failed", "job_retry_exhausted")


def test_terminal_job_cannot_be_renewed_or_completed_again(database: Session) -> None:
    actor = _admin(database)
    _enqueue(database, actor_id=actor.id, suffix="terminal")
    repository = OperationJobRepository(database)
    lease = repository.claim_next(now=NOW, lease_duration=LEASE, max_attempts=3)
    assert lease is not None
    assert repository.complete(run_id=lease.run_id, attempt_count=1, now=NOW + timedelta(seconds=1))
    assert not repository.complete(run_id=lease.run_id, attempt_count=1, now=NOW + timedelta(seconds=2))
    assert (
        repository.renew_lease(
            run_id=lease.run_id,
            attempt_count=1,
            now=NOW + timedelta(seconds=2),
            lease_duration=LEASE,
        )
        is None
    )


def test_postgresql_claim_uses_skip_locked() -> None:
    statement = OperationJobRepository._claimable_statement(now=NOW, max_attempts=3).with_for_update(skip_locked=True)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in sql
