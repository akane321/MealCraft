from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.platform import OperationRun, User


@pytest.fixture
def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _admin(database: Session, email: str = "ops@example.test") -> User:
    user = User(
        normalized_email=email,
        display_name="Operations",
        system_role="admin",
    )
    database.add(user)
    database.flush()
    return user


def test_operation_run_persists_durable_job_fields(database: Session) -> None:
    actor = _admin(database)
    lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
    run = OperationRun(
        trace_id="job-catalog-import-1",
        run_type="catalog_import",
        status="running",
        triggered_by_user_id=actor.id,
        input_digest="a" * 64,
        job_payload={"release": "v2.1", "source": "approved_registry"},
        idempotency_key="catalog-import-2026-10-03",
        attempt_count=1,
        lease_expires_at=lease_expires_at,
    )
    database.add(run)
    database.commit()
    database.refresh(run)

    assert run.job_payload == {"release": "v2.1", "source": "approved_registry"}
    assert run.idempotency_key == "catalog-import-2026-10-03"
    assert run.attempt_count == 1
    # SQLite drops timezone metadata; PostgreSQL preserves the timezone-aware value.
    assert run.lease_expires_at == lease_expires_at.replace(tzinfo=None)


def test_non_job_operation_run_gets_safe_job_defaults(database: Session) -> None:
    run = OperationRun(trace_id="planning-1", run_type="planning", status="succeeded")
    database.add(run)
    database.commit()
    database.refresh(run)

    assert run.job_payload == {}
    assert run.idempotency_key is None
    assert run.attempt_count == 0
    assert run.lease_expires_at is None


def test_job_idempotency_key_is_unique_per_actor_and_run_type(database: Session) -> None:
    actor = _admin(database)
    database.add(
        OperationRun(
            trace_id="job-evaluation-1",
            run_type="evaluation",
            triggered_by_user_id=actor.id,
            idempotency_key="evaluation-request-1",
        )
    )
    database.commit()

    database.add(
        OperationRun(
            trace_id="job-evaluation-2",
            run_type="evaluation",
            triggered_by_user_id=actor.id,
            idempotency_key="evaluation-request-1",
        )
    )
    with pytest.raises(IntegrityError):
        database.commit()


def test_attempt_count_cannot_be_negative(database: Session) -> None:
    database.add(
        OperationRun(
            trace_id="job-invalid-attempt",
            run_type="catalog_import",
            attempt_count=-1,
        )
    )

    with pytest.raises(IntegrityError):
        database.commit()
