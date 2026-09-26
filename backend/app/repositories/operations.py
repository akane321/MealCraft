from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import AgentRun, AgentSession
from app.models.meal_plan import MealPlan
from app.models.platform import OperationRun


@dataclass(frozen=True)
class OperationsOverviewSnapshot:
    queued: int
    running: int
    failures: dict[str, int]
    provider_modes: dict[str, int]
    code_commit: str | None
    catalog_version: str | None
    product_snapshot_version: str | None


class OperationsRepository:
    """Read-only access to append-only operations evidence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_runs(
        self,
        *,
        run_type: str | None,
        status: str | None,
        since: datetime | None,
        limit: int,
    ) -> tuple[list[OperationRun], int]:
        filters = []
        if run_type is not None:
            filters.append(OperationRun.run_type == run_type)
        if status is not None:
            filters.append(OperationRun.status == status)
        if since is not None:
            filters.append(OperationRun.created_at >= since)

        total = self.session.scalar(select(func.count()).select_from(OperationRun).where(*filters)) or 0
        statement = (
            select(OperationRun)
            .where(*filters)
            .order_by(OperationRun.created_at.desc(), OperationRun.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement)), total

    def overview(self, *, since: datetime) -> OperationsOverviewSnapshot:
        status_counts = dict(
            self.session.execute(
                select(OperationRun.status, func.count(OperationRun.id))
                .where(OperationRun.status.in_(("queued", "running")))
                .group_by(OperationRun.status)
            ).all()
        )
        failures = {
            error_code or "unclassified": count
            for error_code, count in self.session.execute(
                select(OperationRun.error_code, func.count(OperationRun.id))
                .where(OperationRun.status == "failed", OperationRun.created_at >= since)
                .group_by(OperationRun.error_code)
            ).all()
        }
        provider_modes = dict(
            self.session.execute(
                select(OperationRun.provider_mode, func.count(OperationRun.id))
                .where(OperationRun.created_at >= since, OperationRun.provider_mode.is_not(None))
                .group_by(OperationRun.provider_mode)
            ).all()
        )

        return OperationsOverviewSnapshot(
            queued=status_counts.get("queued", 0),
            running=status_counts.get("running", 0),
            failures=failures,
            provider_modes=provider_modes,
            code_commit=self._latest_value(OperationRun.code_commit),
            catalog_version=self._latest_value(OperationRun.catalog_version),
            product_snapshot_version=self._latest_value(OperationRun.product_snapshot_version),
        )

    def _latest_value(self, field) -> str | None:
        statement = (
            select(field)
            .where(field.is_not(None))
            .order_by(OperationRun.created_at.desc(), OperationRun.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    # --- Console reads (ADR-0047): tasks, series and service history. ---

    def created_rows(self, model, *columns, since: datetime, where=()) -> list[tuple]:
        """Raw rows for bucketing in Python, which keeps day grouping identical on SQLite and Postgres."""

        statement = select(model.created_at, *columns).where(model.created_at >= since, *where)
        return [tuple(row) for row in self.session.execute(statement).all()]

    def task_page(
        self,
        model,
        *,
        where: list,
        status: str | None,
        since: datetime | None,
        until: datetime | None,
        fetch: int,
    ) -> tuple[list, int]:
        filters = list(where)
        if status is not None:
            filters.append(model.status == status)
        if since is not None:
            filters.append(model.created_at >= since)
        if until is not None:
            filters.append(model.created_at < until)
        total = self.session.scalar(select(func.count()).select_from(model).where(*filters)) or 0
        statement = select(model).where(*filters).order_by(model.created_at.desc(), model.id.desc()).limit(fetch)
        return list(self.session.scalars(statement)), total

    def agent_run(self, run_id: int) -> AgentRun | None:
        return self.session.scalars(
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(
                selectinload(AgentRun.session).selectinload(AgentSession.messages),
                selectinload(AgentRun.checkpoints),
                selectinload(AgentRun.tool_executions),
            )
        ).one_or_none()

    def planning_run(self, run_id: int) -> OperationRun | None:
        return self.session.scalars(
            select(OperationRun).where(OperationRun.id == run_id, OperationRun.run_type == "planning")
        ).one_or_none()

    def plan_constraints(self, plan_id: int) -> dict | None:
        return self.session.scalar(select(MealPlan.constraints).where(MealPlan.id == plan_id))
