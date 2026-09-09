from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.models.agent import AgentRun
from app.orchestration.contracts import AgentRunStatus, ToolEffect, ToolRunStatus
from app.repositories.agent_runs import AgentRunRepository


class AgentRunLifecycleError(ValueError):
    pass


class AgentRunNotFoundError(LookupError):
    pass


class AgentRunBudgetExceededError(AgentRunLifecycleError):
    pass


class AgentRunReplayInProgressError(AgentRunLifecycleError):
    pass


class AgentRunIdempotencyConflictError(AgentRunLifecycleError):
    pass


class BudgetKind(StrEnum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RETRIEVAL_RETRY = "retrieval_retry"
    PLANNING_ATTEMPT = "planning_attempt"


TERMINAL_STATUSES = {
    AgentRunStatus.NEEDS_CLARIFICATION,
    AgentRunStatus.READY_FOR_CONFIRMATION,
    AgentRunStatus.PREVIEW_READY,
    AgentRunStatus.COMMITTED,
    AgentRunStatus.DEGRADED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}

ALLOWED_TRANSITIONS: dict[AgentRunStatus, set[AgentRunStatus]] = {
    AgentRunStatus.CREATED: {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED, AgentRunStatus.FAILED},
    AgentRunStatus.RUNNING: {
        AgentRunStatus.NEEDS_CLARIFICATION,
        AgentRunStatus.READY_FOR_CONFIRMATION,
        AgentRunStatus.PREVIEW_READY,
        AgentRunStatus.COMMITTED,
        AgentRunStatus.DEGRADED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    },
    AgentRunStatus.PREVIEW_READY: set(),
    AgentRunStatus.NEEDS_CLARIFICATION: set(),
    AgentRunStatus.READY_FOR_CONFIRMATION: set(),
    AgentRunStatus.COMMITTED: set(),
    AgentRunStatus.DEGRADED: set(),
    AgentRunStatus.FAILED: set(),
    AgentRunStatus.CANCELLED: set(),
}


@dataclass(frozen=True)
class StartedRun:
    run: AgentRun
    replayed: bool


def stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AgentRunLifecycle:
    """Durable, deterministic state transitions for one bounded Agent operation."""

    def __init__(self, repository: AgentRunRepository) -> None:
        self.repository = repository

    def start(
        self,
        *,
        agent_session_id: int,
        idempotency_key: str,
        intent: str,
        input_payload: Any,
        context_version: int,
        plan_revision: int | None = None,
        scope_decision: dict | None = None,
        actor_user_id: int | None = None,
        household_id: int | None = None,
        max_llm_calls: int = 2,
        max_tool_calls: int = 8,
        max_retrieval_retries: int = 2,
        max_planning_attempts: int = 3,
        max_wall_seconds: int = 120,
        max_api_cost_usd: Decimal | None = None,
        now: datetime | None = None,
    ) -> StartedRun:
        input_digest = stable_digest(input_payload)
        existing = self.repository.get_by_idempotency_key(agent_session_id, idempotency_key)
        if existing is not None:
            if existing.input_digest != input_digest:
                raise AgentRunIdempotencyConflictError(
                    "This idempotency key was already used with a different request payload."
                )
            if AgentRunStatus(existing.status) not in TERMINAL_STATUSES:
                raise AgentRunReplayInProgressError("An Agent run with this idempotency key is still in progress.")
            return StartedRun(run=existing, replayed=True)

        moment = now or datetime.now(UTC)
        try:
            run = self.repository.create(
                agent_session_id=agent_session_id,
                actor_user_id=actor_user_id,
                household_id=household_id,
                idempotency_key=idempotency_key,
                intent=intent,
                input_digest=input_digest,
                context_version=context_version,
                plan_revision=plan_revision,
                scope_decision=scope_decision,
                max_llm_calls=max_llm_calls,
                max_tool_calls=max_tool_calls,
                max_retrieval_retries=max_retrieval_retries,
                max_planning_attempts=max_planning_attempts,
                max_wall_seconds=max_wall_seconds,
                max_api_cost_usd=max_api_cost_usd,
                deadline_at=moment + timedelta(seconds=max_wall_seconds),
            )
        except IntegrityError:
            self.repository.rollback()
            concurrent = self.repository.get_by_idempotency_key(agent_session_id, idempotency_key)
            if concurrent is None:
                raise
            if concurrent.input_digest != input_digest:
                raise AgentRunIdempotencyConflictError(
                    "This idempotency key was already used with a different request payload."
                ) from None
            if AgentRunStatus(concurrent.status) not in TERMINAL_STATUSES:
                raise AgentRunReplayInProgressError(
                    "An Agent run with this idempotency key is still in progress."
                ) from None
            return StartedRun(run=concurrent, replayed=True)
        return StartedRun(run=run, replayed=False)

    def transition(
        self,
        run: AgentRun,
        status: AgentRunStatus,
        *,
        termination_reason_code: str | None = None,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> AgentRun:
        current = AgentRunStatus(run.status)
        if status == current:
            return run
        if status not in ALLOWED_TRANSITIONS[current]:
            raise AgentRunLifecycleError(f"Invalid Agent run transition: {current} -> {status}")
        moment = now or datetime.now(UTC)
        if status is AgentRunStatus.RUNNING:
            if self._is_expired(run, moment):
                return self.repository.transition(
                    run,
                    status=AgentRunStatus.FAILED,
                    completed_at=moment,
                    termination_reason_code="WALL_TIME_BUDGET_EXCEEDED",
                    error_code="WALL_TIME_BUDGET_EXCEEDED",
                )
            return self.repository.transition(run, status=status, started_at=run.started_at or moment)
        return self.repository.transition(
            run,
            status=status,
            completed_at=moment if status in TERMINAL_STATUSES else None,
            termination_reason_code=termination_reason_code,
            error_code=error_code,
        )

    def checkpoint(
        self,
        run: AgentRun,
        *,
        stage: str,
        status: str,
        state_payload: dict,
        evidence_references: list[dict] | None = None,
    ) -> AgentRun:
        return self.repository.add_checkpoint(
            run,
            stage=stage,
            status=status,
            state_digest=stable_digest(state_payload),
            state_payload=state_payload,
            evidence_references=evidence_references or [],
        )

    def consume_budget(
        self,
        run: AgentRun,
        kind: BudgetKind,
        *,
        amount: int = 1,
        api_cost_usd: Decimal = Decimal("0"),
        now: datetime | None = None,
    ) -> AgentRun:
        if amount < 0 or api_cost_usd < 0:
            raise AgentRunLifecycleError("Budget consumption cannot be negative.")
        moment = now or datetime.now(UTC)
        if self._is_expired(run, moment):
            self._terminate_for_budget(run, code="WALL_TIME_BUDGET_EXCEEDED", moment=moment)
            raise AgentRunBudgetExceededError("Agent run wall-time budget exceeded.")
        counters = {
            BudgetKind.LLM_CALL: ("used_llm_calls", "max_llm_calls"),
            BudgetKind.TOOL_CALL: ("used_tool_calls", "max_tool_calls"),
            BudgetKind.RETRIEVAL_RETRY: ("used_retrieval_retries", "max_retrieval_retries"),
            BudgetKind.PLANNING_ATTEMPT: ("used_planning_attempts", "max_planning_attempts"),
        }
        used_name, max_name = counters[kind]
        if getattr(run, used_name) + amount > getattr(run, max_name):
            self._terminate_for_budget(run, code=f"{kind.value.upper()}_BUDGET_EXCEEDED", moment=moment)
            raise AgentRunBudgetExceededError(f"Agent run {kind} budget exceeded.")
        next_cost = Decimal(run.used_api_cost_usd) + api_cost_usd
        if run.max_api_cost_usd is not None and next_cost > Decimal(run.max_api_cost_usd):
            self._terminate_for_budget(run, code="API_COST_BUDGET_EXCEEDED", moment=moment)
            raise AgentRunBudgetExceededError("Agent run API cost budget exceeded.")
        return self.repository.consume_budget(
            run,
            counter_name=used_name,
            amount=amount,
            used_api_cost_usd=next_cost,
        )

    def record_tool(
        self,
        run: AgentRun,
        *,
        tool_name: str,
        effect: ToolEffect,
        status: ToolRunStatus,
        arguments: Any,
        result_reference: str | None = None,
        provider_mode: str | None = None,
        error_code: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AgentRun:
        moment = started_at or datetime.now(UTC)
        run = self.consume_budget(run, BudgetKind.TOOL_CALL, now=moment)
        if tool_name in {"generate_plan_preview", "generate_replan_preview"}:
            run = self.consume_budget(run, BudgetKind.PLANNING_ATTEMPT, now=moment)
        self.repository.add_tool_execution(
            run,
            tool_name=tool_name,
            effect=effect,
            status=status,
            arguments_digest=stable_digest(arguments),
            result_reference=result_reference,
            provider_mode=provider_mode,
            error_code=error_code,
            started_at=moment,
            completed_at=completed_at or datetime.now(UTC),
        )
        return run

    def cancel(self, run_id: int, *, reason_code: str = "USER_CANCELLED") -> AgentRun:
        run = self.repository.get(run_id)
        if run is None:
            raise AgentRunNotFoundError
        if AgentRunStatus(run.status) in TERMINAL_STATUSES:
            raise AgentRunLifecycleError("A terminal Agent run cannot be cancelled.")
        return self.transition(run, AgentRunStatus.CANCELLED, termination_reason_code=reason_code)

    def _terminate_for_budget(self, run: AgentRun, *, code: str, moment: datetime) -> AgentRun:
        current = self.repository.get(run.id) or run
        if AgentRunStatus(current.status) in TERMINAL_STATUSES:
            return current
        return self.repository.transition(
            current,
            status=AgentRunStatus.FAILED,
            completed_at=moment,
            termination_reason_code=code,
            error_code=code,
        )

    @staticmethod
    def _is_expired(run: AgentRun, moment: datetime) -> bool:
        deadline = run.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        return moment > deadline
