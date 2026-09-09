from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import AgentRun, AgentRunCheckpoint, AgentSession, AgentToolExecution
from app.orchestration.contracts import AgentRunStatus, ToolEffect, ToolRunStatus


class AgentRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _load_options():
        return (
            selectinload(AgentRun.checkpoints),
            selectinload(AgentRun.tool_executions),
        )

    def get(self, run_id: int) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(*self._load_options())
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_for_session(self, agent_session_id: int, run_id: int) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.agent_session_id == agent_session_id)
            .options(*self._load_options())
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_by_idempotency_key(self, agent_session_id: int, idempotency_key: str) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.agent_session_id == agent_session_id,
                AgentRun.idempotency_key == idempotency_key,
            )
            .options(*self._load_options())
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(statement).unique().one_or_none()

    def list_for_session(self, agent_session_id: int, *, limit: int = 20) -> list[AgentRun]:
        statement = (
            select(AgentRun)
            .where(AgentRun.agent_session_id == agent_session_id)
            .options(*self._load_options())
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return list(self.session.scalars(statement).unique().all())

    def create(self, **values) -> AgentRun:
        run = AgentRun(**values)
        self.session.add(run)
        self.session.flush()
        agent_session = self.session.get(AgentSession, run.agent_session_id)
        if agent_session is not None:
            agent_session.latest_run_id = run.id
        self.session.commit()
        return self.get(run.id) or run

    def rollback(self) -> None:
        self.session.rollback()

    def transition(
        self,
        run: AgentRun,
        *,
        status: AgentRunStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        termination_reason_code: str | None = None,
        error_code: str | None = None,
    ) -> AgentRun:
        run.status = status.value
        if started_at is not None:
            run.started_at = started_at
        if completed_at is not None:
            run.completed_at = completed_at
        if termination_reason_code is not None:
            run.termination_reason_code = termination_reason_code
        if error_code is not None:
            run.error_code = error_code
        self.session.commit()
        return self.get(run.id) or run

    def add_checkpoint(
        self,
        run: AgentRun,
        *,
        stage: str,
        status: str,
        state_digest: str,
        state_payload: dict,
        evidence_references: list[dict],
    ) -> AgentRun:
        sequence = run.checkpoint_version + 1
        self.session.add(
            AgentRunCheckpoint(
                agent_run_id=run.id,
                sequence=sequence,
                stage=stage,
                status=status,
                state_digest=state_digest,
                state_payload=state_payload,
                evidence_references=evidence_references,
            )
        )
        run.checkpoint_version = sequence
        self.session.commit()
        return self.get(run.id) or run

    def consume_budget(
        self,
        run: AgentRun,
        *,
        counter_name: str,
        amount: int,
        used_api_cost_usd: Decimal,
    ) -> AgentRun:
        setattr(run, counter_name, getattr(run, counter_name) + amount)
        run.used_api_cost_usd = used_api_cost_usd
        self.session.commit()
        return self.get(run.id) or run

    def add_tool_execution(
        self,
        run: AgentRun,
        *,
        tool_name: str,
        effect: ToolEffect,
        status: ToolRunStatus,
        arguments_digest: str,
        result_reference: str | None,
        provider_mode: str | None,
        error_code: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> AgentRun:
        latest_sequence = self.session.scalar(
            select(func.max(AgentToolExecution.sequence)).where(AgentToolExecution.agent_run_id == run.id)
        )
        sequence = (latest_sequence or 0) + 1
        self.session.add(
            AgentToolExecution(
                agent_run_id=run.id,
                sequence=sequence,
                tool_name=tool_name,
                effect=effect.value,
                status=status.value,
                arguments_digest=arguments_digest,
                result_reference=result_reference,
                provider_mode=provider_mode,
                error_code=error_code,
                started_at=started_at,
                completed_at=completed_at,
            )
        )
        self.session.commit()
        return self.get(run.id) or run
