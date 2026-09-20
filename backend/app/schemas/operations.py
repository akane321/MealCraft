from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.platform import OperationStatus


class OperationsRunSummary(BaseModel):
    trace_id: str
    run_type: str
    status: OperationStatus
    triggered_by_user_id: int | None
    input_digest: str | None
    code_commit: str | None
    catalog_version: str | None
    product_snapshot_version: str | None
    policy_version: str | None
    algorithm_version: str | None
    provider_mode: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None = Field(default=None, ge=0)


class OperationsRunCollectionResponse(BaseModel):
    items: list[OperationsRunSummary]
    total: int = Field(ge=0)


class OperationsVersionSummary(BaseModel):
    code_commit: str | None
    catalog_version: str | None
    product_snapshot_version: str | None


class OperationsCountSummary(BaseModel):
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    failures_last_24_hours: dict[str, int]
    provider_modes_last_24_hours: dict[str, int]


class OperationsOverviewResponse(BaseModel):
    api_status: str
    database_status: str
    service: str
    app_version: str
    generated_at: datetime
    latest_recorded_versions: OperationsVersionSummary
    runs: OperationsCountSummary
