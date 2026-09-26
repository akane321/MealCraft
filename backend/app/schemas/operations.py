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


# --- Slice 2 (ADR-0047): debugging replays, runtime settings, experiments and users. ---


class ReplayAgentOverrides(BaseModel):
    parser: Literal["fixture", "openai"] | None = None


class ReplayPlanningOverrides(BaseModel):
    planner_strategy: Literal["beam", "greedy-baseline"] | None = None
    beam_width: int | None = Field(default=None, ge=1, le=512)
    max_expansions: int | None = Field(default=None, ge=1, le=1_000_000)
    pricing_mode: Literal["fixture", "live"] | None = None
    weekly_budget_sgd: float | None = Field(default=None, gt=0, le=7000)
    planning_capability: Literal["mvp", "full"] | None = None


class OperationsReplay(BaseModel):
    id: int
    kind: TaskKind
    source_id: int
    overrides: dict[str, Any]
    # Agent: constraints, assistant_message, status, missing_fields, parser.
    # Planning: status, evidence, message, dishes, total_cost_sgd, failed_checks, duration_seconds, settings.
    original: dict[str, Any] | None
    replay: dict[str, Any]
    triggered_by_user_id: int | None
    created_at: datetime


class OperationsReplaySummary(BaseModel):
    id: int
    kind: TaskKind
    source_id: int
    overrides: dict[str, Any]
    original_status: str | None
    replay_status: str | None
    created_at: datetime


class OperationsReplayCollection(BaseModel):
    items: list[OperationsReplaySummary]


class RuntimeSettingView(BaseModel):
    key: str
    label: str
    meaning: str
    choices: list[str] | None
    minimum: float | None
    maximum: float | None
    integer: bool
    default: Any
    value: Any
    overridden: bool
    wired: bool
    updated_at: datetime | None


class RuntimeSettingCollection(BaseModel):
    items: list[RuntimeSettingView]


class RuntimeSettingChange(BaseModel):
    # None goes back to the server default.
    value: Any = None


class RuntimeSettingHistoryItem(BaseModel):
    key: str
    before: Any
    after: Any
    actor: str | None
    created_at: datetime


class RuntimeSettingHistory(BaseModel):
    items: list[RuntimeSettingHistoryItem]


ExperimentName = Literal["developer-planning", "agent-benchmark"]


class ExperimentRequest(BaseModel):
    evaluation: ExperimentName
    label: str | None = Field(default=None, max_length=80)
    # Registered runtime keys and evaluation options that differ from the current configuration.
    overrides: dict[str, Any] = Field(default_factory=dict)


class ExperimentRun(BaseModel):
    id: int
    evaluation: ExperimentName
    label: str | None
    status: str
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    passed: bool | None
    conditions: dict[str, Any]
    error: str | None
    created_at: datetime
    duration_seconds: float | None


class ExperimentCollection(BaseModel):
    items: list[ExperimentRun]
    evaluations: list[dict[str, Any]]


class OpsUserHousehold(BaseModel):
    id: int
    name: str
    role: str
    members: int
    profile: dict[str, Any] | None


class OpsUserSummary(BaseModel):
    id: int
    email: str
    display_name: str
    system_role: str
    status: str
    households: list[OpsUserHousehold]
    conversations: int
    plans: int
    last_seen_at: datetime | None
    created_at: datetime


class OpsUserCollection(BaseModel):
    items: list[OpsUserSummary]
    total: int


class OpsUserDetail(OpsUserSummary):
    recent_conversations: list[dict[str, Any]]
    recent_plans: list[dict[str, Any]]


class OpsUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    # ADR-0047: one console level; "ordinary_user" is "none".
    system_role: Literal["admin", "ordinary_user"] | None = None


class OpsDeleted(BaseModel):
    deleted: int
