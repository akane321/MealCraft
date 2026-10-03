from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

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
