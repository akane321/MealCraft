from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.agent import AgentSession
from app.orchestration.contracts import AgentRunStatus, ToolEffect, ToolRunStatus
from app.orchestration.run_lifecycle import (
    AgentRunBudgetExceededError,
    AgentRunIdempotencyConflictError,
    AgentRunLifecycle,
    AgentRunLifecycleError,
    AgentRunReplayInProgressError,
    BudgetKind,
)
from app.repositories.agent_runs import AgentRunRepository


@pytest.fixture
def lifecycle() -> tuple[AgentRunLifecycle, Session, int]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Session(engine, expire_on_commit=False)
    agent_session = AgentSession(
        parser_provider="fixture",
        constraints={},
        missing_fields=[],
        clarification_questions=[],
        acknowledged_unknown_quantities=[],
        replan_draft={},
    )
    database.add(agent_session)
    database.commit()
    service = AgentRunLifecycle(AgentRunRepository(database))
    try:
        yield service, database, agent_session.id
    finally:
        database.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_run_lifecycle_persists_checkpoints_tools_and_budgets(lifecycle) -> None:
    service, database, session_id = lifecycle
    started = service.start(
        agent_session_id=session_id,
        idempotency_key="create-plan-1",
        intent="create_plan",
        input_payload={"household_size": 2},
        context_version=1,
    )

    run = service.transition(started.run, AgentRunStatus.RUNNING)
    run = service.checkpoint(
        run,
        stage="constraints_parsed",
        status="succeeded",
        state_payload={"context_version": 1, "missing_fields": []},
    )
    run = service.record_tool(
        run,
        tool_name="generate_plan_preview",
        effect=ToolEffect.PREVIEW,
        status=ToolRunStatus.SUCCEEDED,
        arguments={"candidate_count": 30},
        result_reference="meal-plan:7:revision:1",
        provider_mode="fixture",
    )
    run = service.record_tool(
        run,
        tool_name="save_plan_revision",
        effect=ToolEffect.COMMIT,
        status=ToolRunStatus.SUCCEEDED,
        arguments={"plan_id": 7},
        result_reference="meal-plan:7:revision:1",
    )
    run = service.transition(run, AgentRunStatus.COMMITTED, termination_reason_code="PLAN_SAVED")

    restored = service.repository.get(run.id)
    assert restored is not None
    assert restored.status == "committed"
    assert restored.checkpoint_version == 1
    assert restored.used_tool_calls == 2
    assert restored.used_planning_attempts == 1
    assert [item.sequence for item in restored.tool_executions] == [1, 2]
    assert restored.tool_executions[0].arguments_digest != ""
    assert database.get(AgentSession, session_id).latest_run_id == run.id


def test_idempotency_replays_terminal_run_and_rejects_conflicts(lifecycle) -> None:
    service, _, session_id = lifecycle
    original = service.start(
        agent_session_id=session_id,
        idempotency_key="same-request",
        intent="create_plan",
        input_payload={"message": "plan for two"},
        context_version=1,
    )

    with pytest.raises(AgentRunReplayInProgressError):
        service.start(
            agent_session_id=session_id,
            idempotency_key="same-request",
            intent="create_plan",
            input_payload={"message": "plan for two"},
            context_version=1,
        )

    run = service.transition(original.run, AgentRunStatus.RUNNING)
    service.transition(run, AgentRunStatus.READY_FOR_CONFIRMATION)
    replay = service.start(
        agent_session_id=session_id,
        idempotency_key="same-request",
        intent="create_plan",
        input_payload={"message": "plan for two"},
        context_version=1,
    )
    assert replay.replayed is True
    assert replay.run.id == original.run.id

    with pytest.raises(AgentRunIdempotencyConflictError):
        service.start(
            agent_session_id=session_id,
            idempotency_key="same-request",
            intent="create_plan",
            input_payload={"message": "different request"},
            context_version=1,
        )


def test_budget_deadline_and_cancellation_fail_closed(lifecycle) -> None:
    service, _, session_id = lifecycle
    now = datetime.now(UTC)
    started = service.start(
        agent_session_id=session_id,
        idempotency_key="bounded-run",
        intent="create_plan",
        input_payload={},
        context_version=1,
        max_tool_calls=1,
        max_wall_seconds=10,
        now=now,
    )
    run = service.transition(started.run, AgentRunStatus.RUNNING, now=now)
    run = service.consume_budget(run, BudgetKind.TOOL_CALL, now=now)
    with pytest.raises(AgentRunBudgetExceededError):
        service.consume_budget(run, BudgetKind.TOOL_CALL, now=now)
    failed_budget_run = service.repository.get(run.id)
    assert failed_budget_run is not None
    assert failed_budget_run.status == "failed"
    assert failed_budget_run.error_code == "TOOL_CALL_BUDGET_EXCEEDED"

    cancellable = service.start(
        agent_session_id=session_id,
        idempotency_key="cancellable-run",
        intent="create_plan",
        input_payload={},
        context_version=1,
    )
    cancelled = service.cancel(cancellable.run.id)
    assert cancelled.status == "cancelled"
    assert cancelled.termination_reason_code == "USER_CANCELLED"
    with pytest.raises(AgentRunLifecycleError):
        service.cancel(cancellable.run.id)

    expired = service.start(
        agent_session_id=session_id,
        idempotency_key="expired-run",
        intent="create_plan",
        input_payload={},
        context_version=1,
        max_wall_seconds=1,
        now=now - timedelta(seconds=5),
    )
    failed = service.transition(expired.run, AgentRunStatus.RUNNING, now=now)
    assert failed.status == "failed"
    assert failed.error_code == "WALL_TIME_BUDGET_EXCEEDED"
