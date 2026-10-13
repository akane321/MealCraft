from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.data.catalog import CATALOG_REFRESH_MARKER
from app.models.agent import AgentRun, AgentSession
from app.models.meal_plan import MealPlan
from app.models.platform import OperationRun
from app.models.recipe import CatalogImport
from app.planning.product_path import ProductPlanningError


@dataclass(frozen=True)
class OperationsOverviewSnapshot:
    queued: int
    running: int
    failures: dict[str, int]
    provider_modes: dict[str, int]
    catalog_version: str | None


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
        # Assistant turns fail too. One the planner failed is left out: the planning run it started
        # records that failure under the planner's own code.
        for error_code, count in self.session.execute(
            select(AgentRun.error_code, func.count(AgentRun.id))
            .where(AgentRun.status == "failed", AgentRun.created_at >= since)
            .group_by(AgentRun.error_code)
        ).all():
            if error_code != ProductPlanningError.__name__:
                failures[f"assistant: {error_code or 'unclassified'}"] = count
        # A turn in flight counts as running, as the task list shows it.
        running_turns = self.session.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "running")) or 0
        provider_modes = dict(
            self.session.execute(
                select(OperationRun.provider_mode, func.count(OperationRun.id))
                .where(OperationRun.created_at >= since, OperationRun.provider_mode.is_not(None))
                .group_by(OperationRun.provider_mode)
            ).all()
        )

        return OperationsOverviewSnapshot(
            queued=status_counts.get("queued", 0),
            running=status_counts.get("running", 0) + running_turns,
            failures=failures,
            provider_modes=provider_modes,
            # The data release loaded last. A run's catalog_version is a digest of its own candidates, and the
            # refresh marker only tells API processes the catalog changed.
            catalog_version=self.session.scalar(
                select(CatalogImport.release_version)
                .where(CatalogImport.release_version != CATALOG_REFRESH_MARKER)
                .order_by(CatalogImport.imported_at.desc())
                .limit(1)
            ),
        )

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

    def plan_warnings(self, plan_id: int) -> list[str] | None:
        """The plan's warnings while it is still as its planning run saved it; a later change replaces them."""
        return self.session.scalar(select(MealPlan.warnings).where(MealPlan.id == plan_id, MealPlan.revision == 1))
