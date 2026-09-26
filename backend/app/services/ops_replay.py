"""Replay one stored task through the current code (ADR-0047 Debugging).

A replay never saves a plan or a conversation: planning runs against a repository that keeps the
run in memory, and an assistant turn only calls the parser. Each replay is recorded as an operation
run of type "replay", which the product's task, series and service views do not count.
"""

from __future__ import annotations

import threading
import time as clock
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.parser import ConstraintParser
from app.core.config import get_settings
from app.models.platform import OperationRun
from app.models.recipe import Recipe
from app.orchestration.contracts import InteractionRequest
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.planning.beam_planner import BeamLimits
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.product_path import ProductPlanningEngine, ProductPlanningError
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.operations import OperationsRepository
from app.repositories.product import ProductSnapshotRepository
from app.repositories.recipe import RecipeRepository
from app.schemas.agent import AgentConstraintState, AgentMessageResponse
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.operations import (
    OperationsReplay,
    OperationsReplayCollection,
    OperationsReplaySummary,
    ReplayAgentOverrides,
    ReplayPlanningOverrides,
    TaskKind,
)
from app.services.meal_plan import WeeklyMealPlanService
from app.services.operations import _duration, _planning_trace
from app.services.product import create_product_search_service
from app.services.recommendation import RecipeRecommendationService

REPLAY_RUN_TYPE = "replay"


class ReplayNotFoundError(LookupError):
    pass


class ReplayUnavailableError(ValueError):
    """The task exists but did not keep what a replay needs."""


class _Captured(Exception):  # noqa: N818 - control flow, not an error
    pass


class _DryRunPlans:
    """Stands in for MealPlanRepository: the planning run stays in memory and no plan is saved."""

    household_id = None

    def __init__(self) -> None:
        self.run: OperationRun | None = None
        self.session = self

    def add(self, run: OperationRun) -> None:
        self.run = run

    def commit(self) -> None:
        pass

    def create(self, *, operation_run: OperationRun, **_: Any):
        self.run = operation_run
        raise _Captured


# ponytail: capability is read from the process-wide settings (app/planning/capability.py), so an
# override is set there for the replay's duration under a lock; product requests running at that moment
# see it too. Read it through app.core.runtime_config once planning is wired to the registry.
_CAPABILITY_LOCK = threading.Lock()


@contextmanager
def _capability(value: str | None):
    if value is None:
        yield
        return
    settings = get_settings()
    with _CAPABILITY_LOCK:
        before = settings.planning_capability
        settings.planning_capability = value
        try:
            yield
        finally:
            settings.planning_capability = before


class ReplayService:
    def __init__(self, database: Session, *, actor_user_id: int) -> None:
        self.database = database
        self.repository = OperationsRepository(database)
        self.actor_user_id = actor_user_id

    # --- Assistant turns ---

    def replay_agent(self, run_id: int, overrides: ReplayAgentOverrides, parser: ConstraintParser) -> OperationsReplay:
        run = self.repository.agent_run(run_id)
        if run is None:
            raise ReplayNotFoundError
        record = next(
            (
                item.state_payload["replay"]
                for item in reversed(run.checkpoints)
                if isinstance(item.state_payload, dict) and "replay" in item.state_payload
            ),
            None,
        )
        if record is None:
            raise ReplayUnavailableError(
                "This turn did not keep its input. Turns saved before replays were added, and plan "
                "confirmations or changes to a saved plan, cannot be replayed."
            )
        stored = record["input"]
        started = clock.perf_counter()
        try:
            outcome = BoundedAgentOrchestrator(parser).process(
                stored["message"],
                current=AgentConstraintState.model_validate(stored["current"]),
                acknowledged_unknowns=list(stored.get("acknowledged_unknowns") or []),
                history=[AgentMessageResponse.model_validate(item) for item in stored.get("history") or []],
                current_status=stored.get("current_status", "collecting"),
                current_missing_fields=list(stored.get("current_missing_fields") or []),
                current_questions=list(stored.get("current_questions") or []),
                context_version=stored.get("context_version", 0),
                pending_interaction=(
                    InteractionRequest.model_validate(stored["pending_interaction"])
                    if stored.get("pending_interaction")
                    else None
                ),
            )
            replay = outcome.model_dump(
                mode="json", include={"constraints", "assistant_message", "status", "missing_fields"}
            )
        except Exception as error:  # noqa: BLE001 - a replay reports the failure instead of raising it
            replay = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
        replay["parser"] = parser.provider
        replay["duration_seconds"] = round(clock.perf_counter() - started, 3)
        original = dict(record.get("outcome") or {"status": "failed", "error": run.error_code})
        original["message"] = stored["message"]
        original["parser"] = (run.model_config or {}).get("parser")
        original["duration_seconds"] = _duration(run.started_at, run.completed_at)
        return self._record("agent", run_id, overrides.model_dump(exclude_none=True), original, replay)

    # --- Planning runs ---

    def replay_planning(self, run_id: int, overrides: ReplayPlanningOverrides) -> OperationsReplay:
        source = self.repository.planning_run(run_id)
        if source is None:
            raise ReplayNotFoundError
        trace = _planning_trace(source.artifact_references)
        stored = trace.get("request")
        if stored is None:
            plan_id = next(
                (ref.get("id") for ref in source.artifact_references or [] if ref.get("kind") == "meal_plan"), None
            )
            stored = self.repository.plan_constraints(plan_id) if plan_id is not None else None
        if stored is None:
            raise ReplayUnavailableError(
                "This run saved no plan and was recorded before failed runs kept their request, "
                "so there is nothing to replay."
            )
        changes = overrides.model_dump(exclude_none=True)
        request = WeeklyMealPlanRequest.model_validate(stored).model_copy(
            update={
                key: changes[key] for key in ("planner_strategy", "pricing_mode", "weekly_budget_sgd") if key in changes
            }
        )
        default = BeamLimits()
        limits = BeamLimits(
            width=changes.get("beam_width", default.width),
            max_expansions=changes.get("max_expansions", default.max_expansions),
        )
        captured = self._dry_run(request, limits, changes.get("planning_capability"))
        titles = self._titles(trace, captured)
        return self._record(
            "planning",
            run_id,
            changes,
            _planning_outcome(source, titles),
            _planning_outcome(captured, titles),
        )

    def _dry_run(self, request: WeeklyMealPlanRequest, limits: BeamLimits, capability: str | None) -> OperationRun:
        recipes = RecipeRepository(self.database)
        products = create_product_search_service(ProductSnapshotRepository(self.database))
        plans = _DryRunPlans()
        service = WeeklyMealPlanService(
            repository=plans,  # type: ignore[arg-type]
            recipe_repository=recipes,
            recommendation_service=RecipeRecommendationService(recipes, grocery_estimator=GroceryEstimator(products)),
            grocery_aggregator=WeeklyGroceryAggregator(products),
            planning_engine=ProductPlanningEngine(limits=limits),
            actor_user_id=self.actor_user_id,
        )
        started_at = datetime.now(UTC)
        try:
            with _capability(capability):
                service.generate(request)
        except (_Captured, ProductPlanningError):
            pass
        except (WeeklyPlanSelectionError, ValueError) as error:
            plans.run = None
            return OperationRun(
                run_type="planning",
                status="failed",
                error_detail=str(error),
                artifact_references=[{"kind": "planning_trace", "data": {"status": "failed"}}],
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        if plans.run is None:
            raise ReplayUnavailableError("The planner stopped before it recorded a run.")
        return plans.run

    def _titles(self, trace: dict, run: OperationRun) -> dict[str, str]:
        slugs = {
            item["recipe_id"]
            for data in (trace, _planning_trace(run.artifact_references))
            for item in data.get("assignments") or []
        }
        if not slugs:
            return {}
        return dict(
            self.database.execute(select(Recipe.slug, Recipe.title).where(Recipe.slug.in_(slugs))).tuples().all()
        )

    # --- Records ---

    def _record(
        self, kind: TaskKind, source_id: int, overrides: dict, original: dict, replay: dict
    ) -> OperationsReplay:
        now = datetime.now(UTC)
        row = OperationRun(
            trace_id=f"replay-{uuid4().hex}",
            run_type=REPLAY_RUN_TYPE,
            status="succeeded",
            triggered_by_user_id=self.actor_user_id,
            algorithm_version=kind,
            artifact_references=[
                {
                    "kind": "replay",
                    "data": {
                        "task_kind": kind,
                        "source_id": source_id,
                        "overrides": overrides,
                        "original": original,
                        "replay": replay,
                    },
                }
            ],
            warnings=[],
            created_at=now,
            started_at=now,
            finished_at=now,
        )
        self.database.add(row)
        self.database.commit()
        return _replay_view(row)

    def list(self, limit: int) -> OperationsReplayCollection:
        rows, _ = self.repository.list_runs(run_type=REPLAY_RUN_TYPE, status=None, since=None, limit=limit)
        items = []
        for row in rows:
            view = _replay_view(row)
            items.append(
                OperationsReplaySummary(
                    id=view.id,
                    kind=view.kind,
                    source_id=view.source_id,
                    overrides=view.overrides,
                    original_status=(view.original or {}).get("status"),
                    replay_status=view.replay.get("status"),
                    created_at=view.created_at,
                )
            )
        return OperationsReplayCollection(items=items)

    def get(self, replay_id: int) -> OperationsReplay | None:
        row = self.database.get(OperationRun, replay_id)
        return _replay_view(row) if row is not None and row.run_type == REPLAY_RUN_TYPE else None


def _replay_view(row: OperationRun) -> OperationsReplay:
    data = next(ref["data"] for ref in row.artifact_references if ref.get("kind") == "replay")
    return OperationsReplay(
        id=row.id,
        kind=data["task_kind"],
        source_id=data["source_id"],
        overrides=data["overrides"],
        original=data["original"],
        replay=data["replay"],
        triggered_by_user_id=row.triggered_by_user_id,
        created_at=row.created_at,
    )


def _planning_outcome(run: OperationRun, titles: dict[str, str]) -> dict[str, Any]:
    """What a planning run produced, in the same shape for the stored run and its replay."""

    trace = _planning_trace(run.artifact_references)
    validation = trace.get("validation") or {}
    dishes = []
    for item in trace.get("assignments") or []:
        slot = str(item.get("slot_id", ""))
        day = int(slot.rsplit("-", 1)[-1]) + 1 if slot.rsplit("-", 1)[-1].isdigit() else None
        dishes.append(
            {
                "day": day,
                "meal": "dinner",
                "role": item.get("role_id") or "main",
                "recipe": titles.get(item["recipe_id"], item["recipe_id"]),
            }
        )
    return {
        "status": trace.get("status") or run.status,
        "evidence": trace.get("evidence"),
        "message": run.error_detail,
        "dishes": dishes,
        "total_cost_sgd": validation.get("purchase_total_sgd"),
        "failed_checks": [
            {"code": check.get("code"), "status": check.get("status")}
            for check in validation.get("checks") or []
            if check.get("status") != "passed"
        ],
        "duration_seconds": _duration(run.started_at, run.finished_at),
        "settings": {
            "planner": trace.get("algorithm"),
            "pricing_mode": trace.get("requested_pricing_mode"),
            **(trace.get("settings") or {}),
        },
    }
