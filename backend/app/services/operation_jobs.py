from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.code_version import code_commit
from app.models.platform import AuditEvent, OperationRun
from app.orchestration.run_lifecycle import stable_digest
from app.repositories.operation_jobs import (
    JobIdempotencyConflictError,
    OperationJobNotCancellableError,
    OperationJobNotFoundError,
    OperationJobRepository,
)
from app.schemas.operation_jobs import (
    OperationJobCancellationView,
    OperationJobRequest,
    OperationJobView,
)


@dataclass(frozen=True)
class EnqueuedJob:
    view: OperationJobView
    created: bool


class OperationJobsService:
    def __init__(self, database: Session, *, actor_user_id: int) -> None:
        self.database = database
        self.actor_user_id = actor_user_id
        self.repository = OperationJobRepository(database)

    def enqueue(self, request: OperationJobRequest, *, idempotency_key: str) -> EnqueuedJob:
        arguments = request.arguments.model_dump(mode="json")
        input_digest = stable_digest({"name": request.name, "arguments": arguments})
        run, created = self.repository.enqueue(
            trace_id=f"job-{uuid4().hex}",
            run_type=request.name,
            triggered_by_user_id=self.actor_user_id,
            input_digest=input_digest,
            job_payload=arguments,
            idempotency_key=idempotency_key,
            code_commit=code_commit(),
        )
        if created:
            evidence = {
                "operation_run_id": run.id,
                "job_name": request.name,
                "source": request.arguments.source,
            }
            self.database.add(
                AuditEvent(
                    actor_user_id=self.actor_user_id,
                    action="operation_job.enqueued",
                    target_type="operation_run",
                    target_id=str(run.id),
                    after_digest=stable_digest(evidence),
                    details=evidence,
                )
            )
        self.database.commit()
        return EnqueuedJob(view=_job_view(run, created=created), created=created)

    def cancel(self, run_id: int) -> OperationJobCancellationView:
        now = datetime.now(UTC)
        cancelled = self.repository.cancel(run_id=run_id, now=now)
        evidence = {
            "target_run_id": run_id,
            "previous_status": cancelled.previous_status,
            "target_status": "cancelled",
            "attempt_count": cancelled.attempt_count,
        }
        cancellation = OperationRun(
            trace_id=f"job-cancel-{uuid4().hex}",
            run_type="job_cancellation",
            status="succeeded",
            triggered_by_user_id=self.actor_user_id,
            input_digest=stable_digest(evidence),
            code_commit=code_commit(),
            job_payload={"target_run_id": run_id},
            warnings=[],
            created_at=now,
            started_at=now,
            finished_at=now,
        )
        self.database.add(cancellation)
        self.database.flush()
        self.database.add(
            AuditEvent(
                actor_user_id=self.actor_user_id,
                action="operation_job.cancelled",
                target_type="operation_run",
                target_id=str(run_id),
                before_digest=stable_digest({"status": cancelled.previous_status}),
                after_digest=stable_digest({"status": "cancelled"}),
                details={**evidence, "cancellation_run_id": cancellation.id},
            )
        )
        self.database.commit()
        return OperationJobCancellationView(
            id=cancellation.id,
            trace_id=cancellation.trace_id,
            target_run_id=run_id,
            previous_status=cancelled.previous_status,
            target_status="cancelled",
            created_at=cancellation.created_at,
        )


def _job_view(run: OperationRun, *, created: bool) -> OperationJobView:
    return OperationJobView(
        id=run.id,
        trace_id=run.trace_id,
        name=run.run_type,
        arguments=run.job_payload,
        status=run.status,
        attempt_count=run.attempt_count,
        created=created,
        created_at=run.created_at,
    )


__all__ = [
    "JobIdempotencyConflictError",
    "OperationJobNotCancellableError",
    "OperationJobNotFoundError",
    "OperationJobsService",
]
