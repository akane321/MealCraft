from __future__ import annotations

import math
import time as clock
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import Settings
from app.models.agent import AgentRun, AgentSession
from app.models.platform import OperationRun
from app.products.provider import FairPriceProductProvider, ProductProviderError
from app.repositories.operations import OperationsRepository
from app.retrieval.tutorials import TutorialProviderError, YouTubeDataApiProvider
from app.schemas.operations import (
    OperationsCountSummary,
    OperationsDayPoint,
    OperationsOverviewResponse,
    OperationsRunCollectionResponse,
    OperationsRunSummary,
    OperationsSeriesResponse,
    OperationsServiceCheckResponse,
    OperationsServiceCollectionResponse,
    OperationsServiceRecent,
    OperationsServiceStatus,
    OperationsTaskCollectionResponse,
    OperationsTaskDetail,
    OperationsTaskSummary,
    OperationsVersionSummary,
    ServiceName,
    TaskKind,
)

SERIES_DAYS = 14
SERVICE_WINDOW_DAYS = 7
# A live check is one small call; a slow provider must not hold the console.
LIVE_CHECK_TIMEOUT_SECONDS = 10.0
# Keys are never stored in runs today; this keeps it that way if one ever slips into a trace.
SECRET_KEY_PARTS = ("api_key", "apikey", "secret", "password", "authorization")


class LiveCheckError(RuntimeError):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind


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

    # --- Console (ADR-0047) ---

    def series(self) -> OperationsSeriesResponse:
        today = datetime.now(UTC).date()
        first = today - timedelta(days=SERIES_DAYS - 1)
        since = datetime.combine(first, time.min, UTC)
        days = {first + timedelta(days=offset): _DayBucket() for offset in range(SERIES_DAYS)}
        provider_modes: dict[str, int] = {}

        for (created_at,) in self.repository.created_rows(AgentSession, since=since):
            if bucket := days.get(_aware(created_at).date()):
                bucket.sessions += 1
        for created_at, status in self.repository.created_rows(AgentRun, AgentRun.status, since=since):
            if bucket := days.get(_aware(created_at).date()):
                bucket.agent[status] = bucket.agent.get(status, 0) + 1
        planning = self.repository.created_rows(
            OperationRun,
            OperationRun.status,
            OperationRun.started_at,
            OperationRun.finished_at,
            OperationRun.provider_mode,
            since=since,
            where=(OperationRun.run_type == "planning",),
        )
        for created_at, status, started_at, finished_at, provider_mode in planning:
            for source in filter(None, (provider_mode or "").split(",")):
                provider_modes[source] = provider_modes.get(source, 0) + 1
            if bucket := days.get(_aware(created_at).date()):
                bucket.planning[status] = bucket.planning.get(status, 0) + 1
                if (seconds := _duration(started_at, finished_at)) is not None:
                    bucket.durations.append(seconds)

        return OperationsSeriesResponse(
            days=[
                OperationsDayPoint(
                    day=day,
                    agent_sessions=bucket.sessions,
                    agent_runs=bucket.agent,
                    planning_runs=bucket.planning,
                    planning_median_seconds=_percentile(bucket.durations, 0.5),
                    planning_p90_seconds=_percentile(bucket.durations, 0.9),
                )
                for day, bucket in days.items()
            ],
            provider_modes=provider_modes,
        )

    def tasks(
        self,
        *,
        kind: TaskKind | None,
        status: str | None,
        since: datetime | None,
        until: datetime | None,
        offset: int,
        limit: int,
    ) -> OperationsTaskCollectionResponse:
        # ponytail: two tables merged in memory, so a deep page reads offset+limit rows from each;
        # a union query when the console pages past a few thousand runs.
        fetch = offset + limit
        items: list[OperationsTaskSummary] = []
        total = 0
        if kind in (None, "agent"):
            runs, count = self.repository.task_page(
                AgentRun, where=[], status=status, since=since, until=until, fetch=fetch
            )
            items += [_agent_summary(run) for run in runs]
            total += count
        if kind in (None, "planning"):
            runs, count = self.repository.task_page(
                OperationRun,
                where=[OperationRun.run_type == "planning"],
                status=status,
                since=since,
                until=until,
                fetch=fetch,
            )
            items += [_planning_summary(run) for run in runs]
            total += count
        items.sort(key=lambda item: (_aware(item.created_at), item.id), reverse=True)
        return OperationsTaskCollectionResponse(items=items[offset:fetch], total=total)

    def task_detail(self, kind: TaskKind, task_id: int) -> OperationsTaskDetail | None:
        if kind == "agent":
            run = self.repository.agent_run(task_id)
            return _agent_detail(run) if run is not None else None
        run = self.repository.planning_run(task_id)
        if run is None:
            return None
        plan_id = next(
            (ref.get("id") for ref in run.artifact_references or [] if ref.get("kind") == "meal_plan"),
            None,
        )
        constraints = self.repository.plan_constraints(plan_id) if plan_id is not None else None
        return _planning_detail(run, plan_id=plan_id, constraints=constraints)

    def services(self) -> OperationsServiceCollectionResponse:
        since = datetime.now(UTC) - timedelta(days=SERVICE_WINDOW_DAYS)
        settings = self.settings

        # OpenAI: agent runs whose recorded parser was openai; a degraded run fell back.
        openai_runs = [
            status
            for _, status, config in self.repository.created_rows(
                AgentRun, AgentRun.status, AgentRun.model_config, since=since
            )
            if (config or {}).get("parser") == "openai"
        ]
        # FairPrice: planning runs that asked for live prices; one priced without FairPrice fell back.
        # ponytail: reads whole traces for the window; a requested_mode column if this gets slow.
        live_runs = [
            (status, set(filter(None, (provider_mode or "").split(","))))
            for _, status, provider_mode, references in self.repository.created_rows(
                OperationRun,
                OperationRun.status,
                OperationRun.provider_mode,
                OperationRun.artifact_references,
                since=since,
                where=(OperationRun.run_type == "planning",),
            )
            if _planning_trace(references).get("requested_pricing_mode") == "live"
        ]
        youtube_key = _secret(settings.youtube_api_key)

        return OperationsServiceCollectionResponse(
            items=[
                OperationsServiceStatus(
                    name="openai",
                    label="OpenAI",
                    configured=_secret(settings.openai_api_key) is not None,
                    mode=f"{settings.agent_parser_provider} parser, model {settings.openai_model}",
                    recent=OperationsServiceRecent(
                        window_days=SERVICE_WINDOW_DAYS,
                        calls=len(openai_runs),
                        failures=sum(status == "failed" for status in openai_runs),
                        fallbacks=sum(status == "degraded" for status in openai_runs),
                    ),
                ),
                OperationsServiceStatus(
                    name="fairprice",
                    label="FairPrice",
                    configured=bool(settings.fairprice_base_url),
                    mode="fixture prices unless a plan asks for live prices",
                    recent=OperationsServiceRecent(
                        window_days=SERVICE_WINDOW_DAYS,
                        calls=len(live_runs),
                        failures=sum(status == "failed" for status, _ in live_runs),
                        fallbacks=sum("fairprice" not in sources for _, sources in live_runs),
                    ),
                ),
                OperationsServiceStatus(
                    name="youtube",
                    label="YouTube",
                    configured=youtube_key is not None,
                    mode="live" if youtube_key else "fixture",
                    recent=None,
                    note="Tutorial lookups are not stored yet, so there is no call history.",
                ),
            ]
        )

    def check_service(self, name: ServiceName) -> OperationsServiceCheckResponse:
        started = clock.perf_counter()
        try:
            detail = LIVE_CHECKS[name](self.settings)
            ok, kind = True, None
        except LiveCheckError as error:
            ok, kind, detail = False, error.kind, str(error)
        return OperationsServiceCheckResponse(
            name=name,
            ok=ok,
            latency_ms=round((clock.perf_counter() - started) * 1000),
            error_kind=kind,
            detail=detail,
            checked_at=datetime.now(UTC),
        )


class _DayBucket:
    def __init__(self) -> None:
        self.sessions = 0
        self.agent: dict[str, int] = {}
        self.planning: dict[str, int] = {}
        self.durations: list[float] = []


def _aware(moment: datetime) -> datetime:
    # SQLite hands back naive datetimes; they were written in UTC.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _duration(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    return max((_aware(finished_at) - _aware(started_at)).total_seconds(), 0.0)


def _percentile(values: list[float], share: float) -> float | None:
    """Nearest-rank percentile: always a duration that was really observed."""

    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(math.ceil(share * len(ordered)) - 1, 0)], 3)


def _secret(value) -> str | None:
    raw = value.get_secret_value() if value is not None else None
    return raw or None


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact(item)
            for key, item in value.items()
            if not any(part in str(key).casefold() for part in SECRET_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _planning_trace(references: list[dict] | None) -> dict:
    for reference in references or []:
        if reference.get("kind") == "planning_trace" and isinstance(reference.get("data"), dict):
            return reference["data"]
    return {}


def _agent_summary(run: AgentRun) -> OperationsTaskSummary:
    return OperationsTaskSummary(
        kind="agent",
        id=run.id,
        label=f"Conversation {run.agent_session_id}: {run.intent.replace('_', ' ')}",
        status=run.status,
        error_code=run.error_code,
        provider_mode=(run.model_config or {}).get("parser"),
        created_at=run.created_at,
        duration_seconds=_duration(run.started_at, run.completed_at),
    )


def _planning_summary(run: OperationRun) -> OperationsTaskSummary:
    return OperationsTaskSummary(
        kind="planning",
        id=run.id,
        label=f"Planning run ({run.algorithm_version or 'unknown planner'})",
        status=run.status,
        error_code=run.error_code,
        provider_mode=run.provider_mode,
        created_at=run.created_at,
        duration_seconds=_duration(run.started_at, run.finished_at),
    )


def _agent_detail(run: AgentRun) -> OperationsTaskDetail:
    checkpoints = [
        {
            "sequence": item.sequence,
            "stage": item.stage,
            "status": item.status,
            "state_digest": item.state_digest,
            "state": item.state_payload,
            "evidence_references": item.evidence_references,
            "created_at": item.created_at,
        }
        for item in run.checkpoints
    ]
    tools = [
        {
            "sequence": item.sequence,
            "tool": item.tool_name,
            "effect": item.effect,
            "status": item.status,
            "provider_mode": item.provider_mode,
            "error_code": item.error_code,
            "arguments_digest": item.arguments_digest,
            "result_reference": item.result_reference,
            "seconds": _duration(item.started_at, item.completed_at),
        }
        for item in run.tool_executions
    ]
    return OperationsTaskDetail(
        summary=_agent_summary(run),
        inputs=_redact(
            {
                "intent": run.intent,
                "conversation": [
                    {"role": message.role, "content": message.content, "at": message.created_at}
                    for message in run.session.messages
                ],
                "understood_constraints": run.session.constraints,
                "missing_fields": run.session.missing_fields,
                "scope_decision": run.scope_decision,
                "context_version": run.context_version,
                "plan_revision": run.plan_revision,
            }
        ),
        trace=_redact({"checkpoints": checkpoints, "tool_executions": tools}),
        validation=None,
        evidence={
            "input_digest": run.input_digest,
            "checkpoint_digests": [item["state_digest"] for item in checkpoints],
            "tool_argument_digests": [item["arguments_digest"] for item in tools],
        },
        model_configuration=_redact(run.model_config),
        timings={
            "created_at": run.created_at,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "deadline_at": run.deadline_at,
            "duration_seconds": _duration(run.started_at, run.completed_at),
            "termination_reason": run.termination_reason_code,
            "llm_calls": f"{run.used_llm_calls} of {run.max_llm_calls}",
            "tool_calls": f"{run.used_tool_calls} of {run.max_tool_calls}",
            "planning_attempts": f"{run.used_planning_attempts} of {run.max_planning_attempts}",
            "retrieval_retries": f"{run.used_retrieval_retries} of {run.max_retrieval_retries}",
            "api_cost_usd": str(run.used_api_cost_usd),
        },
        error_detail=None,
        warnings=[],
    )


def _planning_detail(run: OperationRun, *, plan_id: int | None, constraints: dict | None) -> OperationsTaskDetail:
    trace = _redact(_planning_trace(run.artifact_references))
    evidence: dict[str, Any] = {key: value for key, value in trace.items() if "digest" in key}
    evidence.update(
        {
            "evidence_state": trace.get("evidence"),
            "observed_sources": trace.get("observed_sources"),
            "code_commit": run.code_commit,
            "catalog_version": run.catalog_version,
            "product_snapshot_version": run.product_snapshot_version,
            "policy_version": run.policy_version,
            "algorithm_version": run.algorithm_version,
        }
    )
    inputs: dict[str, Any] = {"input_digest": run.input_digest, "plan_id": plan_id}
    if constraints is not None:
        inputs["constraints"] = _redact(constraints)
    else:
        inputs["note"] = "Constraints are kept with a saved plan; this run saved none, so only their digest remains."
    return OperationsTaskDetail(
        summary=_planning_summary(run),
        inputs=inputs,
        trace=trace or None,
        validation=trace.get("validation"),
        evidence=evidence,
        model_configuration={
            key: trace.get(key)
            for key in ("algorithm", "settings", "seed", "candidate_limit", "requested_pricing_mode", "policy_version")
        },
        timings={
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "duration_seconds": _duration(run.started_at, run.finished_at),
            "timeout_seconds": trace.get("timeout_seconds"),
        },
        error_detail=run.error_detail,
        warnings=list(run.warnings or []),
    )


def _check_openai(settings: Settings) -> str:
    key = _secret(settings.openai_api_key)
    if key is None:
        raise LiveCheckError("not_configured", "OPENAI_API_KEY is not set.")
    # Reading one model's record costs no tokens and proves both the key and the model name.
    request = Request(
        f"https://api.openai.com/v1/models/{quote(settings.openai_model)}",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urlopen(request, timeout=LIVE_CHECK_TIMEOUT_SECONDS) as response:  # noqa: S310
            response.read()
    except HTTPError as error:
        kind = {401: "auth", 403: "auth", 404: "model_not_found", 429: "rate_limited"}.get(error.code, "http_error")
        raise LiveCheckError(kind, f"OpenAI answered HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError) as error:
        raise LiveCheckError(_network_kind(error), f"OpenAI could not be reached: {type(error).__name__}.") from None
    return f"The key works and model {settings.openai_model} is available."


def _check_youtube(settings: Settings) -> str:
    key = _secret(settings.youtube_api_key)
    if key is None:
        raise LiveCheckError("not_configured", "YOUTUBE_API_KEY is not set.")
    provider = YouTubeDataApiProvider(
        api_key=key, timeout_seconds=min(settings.youtube_timeout_seconds, LIVE_CHECK_TIMEOUT_SECONDS)
    )
    try:
        found = provider.search("chicken rice recipe", limit=1)
    except TutorialProviderError as error:
        message = str(error)
        kind = "quota" if "quota" in message else "unreachable" if "reached" in message else "provider_error"
        raise LiveCheckError(kind, message) from None
    return f"One search returned {len(found)} video{'' if len(found) == 1 else 's'}."


def _check_fairprice(settings: Settings) -> str:
    provider = FairPriceProductProvider(
        base_url=settings.fairprice_base_url,
        timeout_seconds=min(settings.fairprice_timeout_seconds, LIVE_CHECK_TIMEOUT_SECONDS),
    )
    try:
        found = provider.search("rice", limit=1)
    except ProductProviderError as error:
        raise LiveCheckError(error.kind, str(error)) from None
    if not found:
        raise LiveCheckError("empty", "FairPrice answered but the search returned no products.")
    return f"One search returned {found[0].name}."


def _network_kind(error: Exception) -> str:
    reason = getattr(error, "reason", error)
    return "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason) else "unreachable"


LIVE_CHECKS = {"openai": _check_openai, "youtube": _check_youtube, "fairprice": _check_fairprice}
