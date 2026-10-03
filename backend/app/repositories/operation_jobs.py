from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from re import fullmatch
from string import hexdigits
from typing import Literal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.platform import OperationRun

JobTerminalStatus = Literal["succeeded", "degraded"]
JobFailureOutcome = Literal["queued", "failed"]


class JobIdempotencyConflictError(ValueError):
    """The same actor, job type and key were reused for different input."""


class OperationJobNotFoundError(LookupError):
    """No durable job has the requested identifier."""


class OperationJobNotCancellableError(ValueError):
    """A terminal durable job cannot be cancelled."""


@dataclass(frozen=True)
class ClaimedOperationJob:
    run_id: int
    trace_id: str
    run_type: str
    payload: dict
    attempt_count: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class CancelledOperationJob:
    run_id: int
    previous_status: Literal["queued", "running"]
    attempt_count: int


class OperationJobRepository:
    """Transactional access to the PostgreSQL-backed Operations job queue.

    The caller owns the surrounding transaction. A claim becomes visible to
    other workers only when that transaction commits. ``attempt_count`` is also
    the fencing token: a worker from an expired attempt cannot renew or finish
    a job after a newer attempt has claimed it.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        trace_id: str,
        run_type: str,
        triggered_by_user_id: int,
        input_digest: str,
        job_payload: dict,
        idempotency_key: str,
        code_commit: str | None = None,
    ) -> tuple[OperationRun, bool]:
        self._validate_enqueue(
            trace_id=trace_id,
            run_type=run_type,
            input_digest=input_digest,
            job_payload=job_payload,
            idempotency_key=idempotency_key,
        )
        existing = self._by_idempotency_key(
            triggered_by_user_id=triggered_by_user_id,
            run_type=run_type,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            self._require_same_input(existing, input_digest)
            return existing, False

        run = OperationRun(
            trace_id=trace_id,
            run_type=run_type,
            status="queued",
            triggered_by_user_id=triggered_by_user_id,
            input_digest=input_digest,
            code_commit=code_commit,
            job_payload=job_payload,
            idempotency_key=idempotency_key,
        )
        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
        except IntegrityError:
            concurrent = self._by_idempotency_key(
                triggered_by_user_id=triggered_by_user_id,
                run_type=run_type,
                idempotency_key=idempotency_key,
            )
            if concurrent is None:
                raise
            self._require_same_input(concurrent, input_digest)
            return concurrent, False
        return run, True

    def claim_next(
        self,
        *,
        now: datetime,
        lease_duration: timedelta,
        max_attempts: int,
    ) -> ClaimedOperationJob | None:
        self._require_policy(lease_duration=lease_duration, max_attempts=max_attempts)
        self._expire_exhausted(now=now, max_attempts=max_attempts)

        run = self.session.scalars(
            self._claimable_statement(now=now, max_attempts=max_attempts).with_for_update(skip_locked=True)
        ).first()
        if run is None:
            return None

        run.status = "running"
        run.attempt_count += 1
        run.lease_expires_at = now + lease_duration
        run.started_at = run.started_at or now
        run.finished_at = None
        run.error_code = None
        run.error_detail = None
        self.session.flush()
        return ClaimedOperationJob(
            run_id=run.id,
            trace_id=run.trace_id,
            run_type=run.run_type,
            payload=dict(run.job_payload),
            attempt_count=run.attempt_count,
            lease_expires_at=run.lease_expires_at,
        )

    def renew_lease(
        self,
        *,
        run_id: int,
        attempt_count: int,
        now: datetime,
        lease_duration: timedelta,
    ) -> datetime | None:
        self._require_policy(lease_duration=lease_duration, max_attempts=1)
        renewed_until = now + lease_duration
        result = self.session.execute(
            update(OperationRun)
            .where(*self._active_attempt(run_id=run_id, attempt_count=attempt_count, now=now))
            .values(lease_expires_at=renewed_until)
        )
        return renewed_until if result.rowcount == 1 else None

    def complete(
        self,
        *,
        run_id: int,
        attempt_count: int,
        now: datetime,
        status: JobTerminalStatus = "succeeded",
    ) -> bool:
        if status not in ("succeeded", "degraded"):
            raise ValueError("job completion status must be succeeded or degraded")
        result = self.session.execute(
            update(OperationRun)
            .where(*self._active_attempt(run_id=run_id, attempt_count=attempt_count, now=now))
            .values(status=status, lease_expires_at=None, finished_at=now)
        )
        return result.rowcount == 1

    def cancel(self, *, run_id: int, now: datetime) -> CancelledOperationJob:
        run = self.session.scalars(
            select(OperationRun)
            .where(OperationRun.id == run_id, OperationRun.idempotency_key.is_not(None))
            .with_for_update()
        ).one_or_none()
        if run is None:
            raise OperationJobNotFoundError
        if run.status not in ("queued", "running"):
            raise OperationJobNotCancellableError("only queued or running jobs can be cancelled")

        previous_status = run.status
        run.status = "cancelled"
        run.lease_expires_at = None
        run.finished_at = now
        run.error_code = None
        run.error_detail = None
        self.session.flush()
        return CancelledOperationJob(
            run_id=run.id,
            previous_status=previous_status,
            attempt_count=run.attempt_count,
        )

    def fail_or_retry(
        self,
        *,
        run_id: int,
        attempt_count: int,
        now: datetime,
        max_attempts: int,
        error_code: str,
    ) -> JobFailureOutcome | None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if fullmatch(r"[a-z][a-z0-9_.-]{0,119}", error_code) is None:
            raise ValueError("error_code must be a controlled lowercase identifier")

        run = self.session.scalars(
            select(OperationRun).where(*self._active_attempt(run_id=run_id, attempt_count=attempt_count, now=now))
        ).one_or_none()
        if run is None:
            return None

        run.lease_expires_at = None
        if run.attempt_count >= max_attempts:
            run.status = "failed"
            run.error_code = error_code
            run.finished_at = now
            outcome: JobFailureOutcome = "failed"
        else:
            run.status = "queued"
            run.warnings = [*run.warnings, f"attempt {run.attempt_count} failed ({error_code}); retry queued"]
            outcome = "queued"
        self.session.flush()
        return outcome

    def _expire_exhausted(self, *, now: datetime, max_attempts: int) -> int:
        result = self.session.execute(
            update(OperationRun)
            .where(
                OperationRun.idempotency_key.is_not(None),
                OperationRun.attempt_count >= max_attempts,
                or_(
                    OperationRun.status == "queued",
                    and_(
                        OperationRun.status == "running",
                        OperationRun.lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                status="failed",
                lease_expires_at=None,
                error_code="job_retry_exhausted",
                finished_at=now,
            )
        )
        return result.rowcount

    @staticmethod
    def _claimable_statement(*, now: datetime, max_attempts: int):
        return (
            select(OperationRun)
            .where(
                OperationRun.idempotency_key.is_not(None),
                OperationRun.attempt_count < max_attempts,
                or_(
                    OperationRun.status == "queued",
                    and_(
                        OperationRun.status == "running",
                        OperationRun.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(OperationRun.created_at, OperationRun.id)
            .limit(1)
        )

    @staticmethod
    def _active_attempt(*, run_id: int, attempt_count: int, now: datetime) -> tuple:
        return (
            OperationRun.id == run_id,
            OperationRun.status == "running",
            OperationRun.attempt_count == attempt_count,
            OperationRun.lease_expires_at > now,
        )

    @staticmethod
    def _require_policy(*, lease_duration: timedelta, max_attempts: int) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

    @staticmethod
    def _validate_enqueue(
        *,
        trace_id: str,
        run_type: str,
        input_digest: str,
        job_payload: dict,
        idempotency_key: str,
    ) -> None:
        if not trace_id or len(trace_id) > 80:
            raise ValueError("trace_id must contain between 1 and 80 characters")
        if not run_type or len(run_type) > 60:
            raise ValueError("run_type must contain between 1 and 60 characters")
        if len(input_digest) != 64 or any(character not in hexdigits for character in input_digest):
            raise ValueError("input_digest must be a 64-character hexadecimal SHA-256 digest")
        if not isinstance(job_payload, dict):
            raise ValueError("job_payload must be a prevalidated object")
        if not idempotency_key or len(idempotency_key) > 120:
            raise ValueError("idempotency_key must contain between 1 and 120 characters")

    def _by_idempotency_key(
        self,
        *,
        triggered_by_user_id: int,
        run_type: str,
        idempotency_key: str,
    ) -> OperationRun | None:
        return self.session.scalars(
            select(OperationRun).where(
                OperationRun.triggered_by_user_id == triggered_by_user_id,
                OperationRun.run_type == run_type,
                OperationRun.idempotency_key == idempotency_key,
            )
        ).one_or_none()

    @staticmethod
    def _require_same_input(run: OperationRun, input_digest: str) -> None:
        if run.input_digest != input_digest:
            raise JobIdempotencyConflictError("idempotency key was already used for different input")
