from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.models.platform import OperationRun
from app.repositories.operations import OperationsRepository
from app.schemas.operations import (
    OperationsCountSummary,
    OperationsOverviewResponse,
    OperationsRunCollectionResponse,
    OperationsRunSummary,
    OperationsVersionSummary,
)


class OperationsService:
    def __init__(self, repository: OperationsRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def overview(self) -> OperationsOverviewResponse:
        generated_at = datetime.now(UTC)
        snapshot = self.repository.overview(since=generated_at - timedelta(hours=24))
        return OperationsOverviewResponse(
            api_status="ok",
            database_status="connected",
            service=self.settings.app_name,
            app_version=self.settings.app_version,
            generated_at=generated_at,
            latest_recorded_versions=OperationsVersionSummary(
                code_commit=snapshot.code_commit,
                catalog_version=snapshot.catalog_version,
                product_snapshot_version=snapshot.product_snapshot_version,
            ),
            runs=OperationsCountSummary(
                queued=snapshot.queued,
                running=snapshot.running,
                failures_last_24_hours=snapshot.failures,
                provider_modes_last_24_hours=snapshot.provider_modes,
            ),
        )

    def list_runs(
        self,
        *,
        run_type: str | None,
        status: str | None,
        since: datetime | None,
        limit: int,
    ) -> OperationsRunCollectionResponse:
        runs, total = self.repository.list_runs(
            run_type=run_type,
            status=status,
            since=since,
            limit=limit,
        )
        return OperationsRunCollectionResponse(
            items=[self._run_summary(run) for run in runs],
            total=total,
        )

    @staticmethod
    def _run_summary(run: OperationRun) -> OperationsRunSummary:
        duration_seconds = None
        if run.started_at is not None and run.finished_at is not None:
            duration_seconds = max((run.finished_at - run.started_at).total_seconds(), 0.0)
        return OperationsRunSummary(
            trace_id=run.trace_id,
            run_type=run.run_type,
            status=run.status,
            triggered_by_user_id=run.triggered_by_user_id,
            input_digest=run.input_digest,
            code_commit=run.code_commit,
            catalog_version=run.catalog_version,
            product_snapshot_version=run.product_snapshot_version,
            policy_version=run.policy_version,
            algorithm_version=run.algorithm_version,
            provider_mode=run.provider_mode,
            error_code=run.error_code,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=duration_seconds,
        )
