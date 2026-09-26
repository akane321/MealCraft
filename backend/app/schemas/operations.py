from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

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


class OperationsDayPoint(BaseModel):
    day: date
    agent_sessions: int = Field(ge=0)
    agent_runs: dict[str, int]
    planning_runs: dict[str, int]
    planning_median_seconds: float | None
    planning_p90_seconds: float | None


class OperationsSeriesResponse(BaseModel):
    days: list[OperationsDayPoint]
    # Price sources seen by planning runs in the window (fixture, fairprice, ...).
    provider_modes: dict[str, int]


TaskKind = Literal["agent", "planning"]


class OperationsTaskSummary(BaseModel):
    kind: TaskKind
    id: int
    label: str
    status: str
    error_code: str | None
    provider_mode: str | None
    created_at: datetime
    duration_seconds: float | None = Field(default=None, ge=0)


class OperationsTaskCollectionResponse(BaseModel):
    items: list[OperationsTaskSummary]
    total: int = Field(ge=0)


class OperationsTaskDetail(BaseModel):
    summary: OperationsTaskSummary
    # What the run was asked: the conversation and understood constraints, or the plan's constraints.
    inputs: dict[str, Any] | None
    trace: dict[str, Any] | None
    validation: Any
    evidence: dict[str, Any]
    model_configuration: dict[str, Any] | None
    timings: dict[str, Any]
    error_detail: str | None
    warnings: list[Any]


ServiceName = Literal["openai", "fairprice", "youtube"]


class OperationsServiceRecent(BaseModel):
    window_days: int
    calls: int = Field(ge=0)
    failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)


class OperationsServiceStatus(BaseModel):
    name: ServiceName
    label: str
    configured: bool
    mode: str
    recent: OperationsServiceRecent | None
    note: str | None = None


class OperationsServiceCollectionResponse(BaseModel):
    items: list[OperationsServiceStatus]


class OperationsServiceCheckResponse(BaseModel):
    name: ServiceName
    ok: bool
    latency_ms: int = Field(ge=0)
    error_kind: str | None
    detail: str
    checked_at: datetime
