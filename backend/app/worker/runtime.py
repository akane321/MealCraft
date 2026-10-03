from __future__ import annotations

import logging
import multiprocessing
import signal
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from multiprocessing.connection import Connection
from threading import Event
from time import monotonic

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.operation_jobs import ClaimedOperationJob, OperationJobRepository
from app.worker.handlers import InvalidJobPayloadError, JobHandlerRegistry, PreparedHandler, UnknownJobTypeError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerPolicy:
    poll_seconds: float
    lease_seconds: float
    heartbeat_seconds: float
    timeout_seconds: float
    max_attempts: int

    def __post_init__(self) -> None:
        if min(self.poll_seconds, self.lease_seconds, self.heartbeat_seconds, self.timeout_seconds) <= 0:
            raise ValueError("worker timing values must be positive")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("worker heartbeat must be shorter than its lease")
        if self.max_attempts <= 0:
            raise ValueError("worker max attempts must be positive")


@dataclass(frozen=True)
class ChildResult:
    succeeded: bool
    error_code: str | None = None


def _execute_handler(connection: Connection, prepared: PreparedHandler, database_url: str) -> None:
    try:
        prepared.handler(prepared.payload, database_url)
        connection.send(ChildResult(succeeded=True))
    except Exception:
        connection.send(ChildResult(succeeded=False, error_code="job_handler_failed"))
    finally:
        connection.close()


class OperationWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        database_url: str,
        registry: JobHandlerRegistry,
        policy: WorkerPolicy,
        stop_event: Event | None = None,
        process_context: multiprocessing.context.BaseContext | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.database_url = database_url
        self.registry = registry
        self.policy = policy
        self.stop_event = stop_event or Event()
        self.process_context = process_context or multiprocessing.get_context("spawn")

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            if not self.run_once():
                self.stop_event.wait(self.policy.poll_seconds)

    def run_once(self) -> bool:
        claim = self._claim()
        if claim is None:
            return False

        try:
            prepared = self.registry.prepare(claim.run_type, claim.payload)
        except UnknownJobTypeError:
            self._fail(claim, "job_type_not_registered", retryable=False)
            return True
        except InvalidJobPayloadError:
            self._fail(claim, "job_payload_invalid", retryable=False)
            return True

        result = self._run_child(claim, prepared)
        if result is None:
            return True
        if result.succeeded:
            self._complete(claim)
        else:
            self._fail(claim, result.error_code or "job_handler_crashed", retryable=True)
        return True

    def _claim(self) -> ClaimedOperationJob | None:
        with self.session_factory() as session:
            claim = OperationJobRepository(session).claim_next(
                now=datetime.now(UTC),
                lease_duration=timedelta(seconds=self.policy.lease_seconds),
                max_attempts=self.policy.max_attempts,
            )
            session.commit()
            return claim

    def _run_child(self, claim: ClaimedOperationJob, prepared: PreparedHandler) -> ChildResult | None:
        receive, send = self.process_context.Pipe(duplex=False)
        process = self.process_context.Process(
            target=_execute_handler,
            args=(send, prepared, self.database_url),
            name=f"mealcraft-job-{claim.run_id}-{claim.attempt_count}",
        )
        process.start()
        send.close()
        deadline = monotonic() + self.policy.timeout_seconds
        next_heartbeat = monotonic() + self.policy.heartbeat_seconds
        try:
            while process.is_alive():
                now = monotonic()
                if self.stop_event.is_set():
                    # Leave the row running. Its lease is the durable hand-off:
                    # another worker will reclaim it after this process exits.
                    self._stop_process(process)
                    return None
                if now >= deadline:
                    self._stop_process(process)
                    self._fail(claim, "job_timeout", retryable=True)
                    return None
                if now >= next_heartbeat:
                    if not self._renew(claim):
                        self._stop_process(process)
                        logger.warning("job lease lost", extra={"run_id": claim.run_id})
                        return None
                    next_heartbeat = monotonic() + self.policy.heartbeat_seconds
                process.join(timeout=max(0, min(0.1, deadline - now, next_heartbeat - now)))

            process.join()
            if receive.poll():
                return receive.recv()
            return ChildResult(succeeded=False, error_code="job_handler_crashed")
        finally:
            receive.close()
            if process.is_alive():
                self._stop_process(process)
            process.close()

    def _renew(self, claim: ClaimedOperationJob) -> bool:
        with self.session_factory() as session:
            renewed = OperationJobRepository(session).renew_lease(
                run_id=claim.run_id,
                attempt_count=claim.attempt_count,
                now=datetime.now(UTC),
                lease_duration=timedelta(seconds=self.policy.lease_seconds),
            )
            session.commit()
            return renewed is not None

    def _complete(self, claim: ClaimedOperationJob) -> bool:
        with self.session_factory() as session:
            completed = OperationJobRepository(session).complete(
                run_id=claim.run_id,
                attempt_count=claim.attempt_count,
                now=datetime.now(UTC),
            )
            session.commit()
            return completed

    def _fail(self, claim: ClaimedOperationJob, error_code: str, *, retryable: bool) -> None:
        max_attempts = self.policy.max_attempts if retryable else claim.attempt_count
        with self.session_factory() as session:
            OperationJobRepository(session).fail_or_retry(
                run_id=claim.run_id,
                attempt_count=claim.attempt_count,
                now=datetime.now(UTC),
                max_attempts=max_attempts,
                error_code=error_code,
            )
            session.commit()

    @staticmethod
    def _stop_process(process: multiprocessing.Process) -> None:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()


def install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
