from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.platform import OperationRun
from app.repositories.operation_jobs import OperationJobRepository
from tests.migrations.support import MigrationDatabase


def test_two_postgresql_workers_skip_each_others_locked_job(migration_database: MigrationDatabase) -> None:
    migration_database.upgrade()
    now = datetime.now(UTC)

    with Session(migration_database.engine) as database:
        repository = OperationJobRepository(database)
        first, _ = repository.enqueue(
            trace_id="postgres-job-first",
            run_type="catalog_import",
            triggered_by_user_id=1001,
            input_digest="a" * 64,
            job_payload={"release": "first"},
            idempotency_key="postgres-first",
        )
        second, _ = repository.enqueue(
            trace_id="postgres-job-second",
            run_type="catalog_import",
            triggered_by_user_id=1001,
            input_digest="b" * 64,
            job_payload={"release": "second"},
            idempotency_key="postgres-second",
        )
        database.commit()
        expected_ids = {first.id, second.id}

    worker_one = Session(migration_database.engine, expire_on_commit=False)
    worker_two = Session(migration_database.engine, expire_on_commit=False)
    try:
        first_claim = OperationJobRepository(worker_one).claim_next(
            now=now,
            lease_duration=timedelta(seconds=30),
            max_attempts=3,
        )
        second_claim = OperationJobRepository(worker_two).claim_next(
            now=now,
            lease_duration=timedelta(seconds=30),
            max_attempts=3,
        )

        assert first_claim is not None
        assert second_claim is not None
        assert {first_claim.run_id, second_claim.run_id} == expected_ids
        worker_two.commit()
        worker_one.commit()
    finally:
        worker_two.close()
        worker_one.close()


@pytest.mark.parametrize("max_attempts", [1, 3])
def test_cancel_committed_during_failure_cannot_be_overwritten(
    migration_database: MigrationDatabase, max_attempts: int
) -> None:
    migration_database.upgrade()
    now = datetime.now(UTC)
    with Session(migration_database.engine) as database:
        repository = OperationJobRepository(database)
        run, _ = repository.enqueue(
            trace_id="postgres-cancel-race",
            run_type="catalog_import",
            triggered_by_user_id=1001,
            input_digest="c" * 64,
            job_payload={},
            idempotency_key="postgres-cancel-race",
        )
        database.commit()
        run_id = run.id
        assert repository.claim_next(now=now, lease_duration=timedelta(seconds=30), max_attempts=max_attempts)
        database.commit()

    selected = Event()

    def report_failure():
        with Session(migration_database.engine) as database:
            # Simulate an identity-map value read before another transaction cancels.
            assert database.get(OperationRun, run_id).status == "running"
            selected.set()
            outcome = OperationJobRepository(database).fail_or_retry(
                run_id=run_id,
                attempt_count=1,
                now=now + timedelta(seconds=1),
                max_attempts=max_attempts,
                error_code="handler_failed",
            )
            database.commit()
            return outcome

    with Session(migration_database.engine) as cancellation, ThreadPoolExecutor(max_workers=1) as workers:
        cancellation.execute(
            update(OperationRun)
            .where(OperationRun.id == run_id)
            .values(status="cancelled", lease_expires_at=None, finished_at=now)
        )
        failure = workers.submit(report_failure)
        try:
            assert selected.wait(timeout=5)
            with pytest.raises(TimeoutError):
                failure.result(timeout=0.2)
        finally:
            cancellation.commit()
        assert failure.result(timeout=5) is None

    with Session(migration_database.engine) as database:
        run = database.scalars(select(OperationRun).where(OperationRun.id == run_id)).one()
        assert run.status == "cancelled"
        assert run.warnings == []
