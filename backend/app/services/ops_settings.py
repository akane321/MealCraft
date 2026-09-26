"""Runtime settings and developer evaluations for the operations console (ADR-0047).

Every settings change writes an audit row with its before and after values. Evaluations run only the
developer sets already in the repository; held-out sets are never offered here (ADR-0031 section 3).
"""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.paths import repository_root
from app.core.runtime_config import REGISTRY, runtime_value
from app.models.platform import AuditEvent, OperationRun, RuntimeSetting, User
from app.orchestration.run_lifecycle import stable_digest
from app.schemas.operations import (
    ExperimentCollection,
    ExperimentRequest,
    ExperimentRun,
    RuntimeSettingCollection,
    RuntimeSettingHistory,
    RuntimeSettingHistoryItem,
    RuntimeSettingView,
)
from app.services.operations import _duration

EXPERIMENT_RUN_TYPE = "experiment"
PLANNERS = ("mealcraft-planner", "greedy-baseline", "rule-only-baseline")

# Developer sets only. Held-out sets stay read-once and are not offered for tuning (ADR-0031 section 3).
EVALUATIONS: dict[str, dict[str, Any]] = {
    "developer-planning": {
        "label": "Developer planning set",
        "description": "20 planning scenarios on the curated catalog with fixture prices.",
        "dataset": "data/evaluation/dev/planning-v1.json",
        "options": {"planner": list(PLANNERS)},
        "keys": [],
    },
    "agent-benchmark": {
        "label": "Assistant benchmark",
        "description": "24 messages the assistant must read into constraints (developer set fixture-v1).",
        "dataset": "data/evaluation/agent/fixture-v1.json",
        "options": {},
        "keys": ["agent_parser_provider"],
    },
}


class SettingsService:
    def __init__(self, database: Session, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    # --- Runtime settings ---

    def list(self) -> RuntimeSettingCollection:
        stored = {row.key: row for row in self.database.scalars(select(RuntimeSetting))}
        items = []
        for key, entry in REGISTRY.items():
            row = stored.get(key)
            default = entry.default(self.settings)
            items.append(
                RuntimeSettingView(
                    key=key,
                    label=entry.label,
                    meaning=entry.meaning,
                    choices=list(entry.choices) if entry.choices else None,
                    minimum=entry.minimum,
                    maximum=entry.maximum,
                    integer=entry.integer,
                    default=default,
                    value=row.value if row is not None else default,
                    overridden=row is not None,
                    wired=entry.wired,
                    updated_at=row.updated_at if row is not None else None,
                )
            )
        return RuntimeSettingCollection(items=items)

    def change(self, key: str, value: Any, *, actor_user_id: int) -> RuntimeSettingCollection:
        entry = REGISTRY[key]
        before = runtime_value(key, self.settings, self.database)
        row = self.database.get(RuntimeSetting, key)
        if value is None:
            if row is not None:
                self.database.delete(row)
            after = entry.default(self.settings)
        else:
            after = entry.check(value)
            if row is None:
                self.database.add(RuntimeSetting(key=key, value=after, updated_by_user_id=actor_user_id))
            else:
                row.value = after
                row.updated_by_user_id = actor_user_id
                row.updated_at = datetime.now(UTC)
        self.database.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="runtime_setting.changed",
                target_type="runtime_setting",
                target_id=key,
                before_digest=stable_digest(before),
                after_digest=stable_digest(after),
                details={"before": before, "after": after, "reset": value is None},
            )
        )
        self.database.commit()
        return self.list()

    def history(self, limit: int) -> RuntimeSettingHistory:
        rows = self.database.execute(
            select(AuditEvent, User.display_name)
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.target_type == "runtime_setting")
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        ).all()
        return RuntimeSettingHistory(
            items=[
                RuntimeSettingHistoryItem(
                    key=event.target_id or "",
                    before=event.details.get("before"),
                    after=event.details.get("after"),
                    actor=name,
                    created_at=event.created_at,
                )
                for event, name in rows
            ]
        )

    # --- Experiments ---

    def experiments(self, limit: int) -> ExperimentCollection:
        rows = self.database.scalars(
            select(OperationRun)
            .where(OperationRun.run_type == EXPERIMENT_RUN_TYPE)
            .order_by(OperationRun.created_at.desc(), OperationRun.id.desc())
            .limit(limit)
        )
        return ExperimentCollection(
            items=[_experiment_view(row) for row in rows],
            evaluations=[
                {"name": name, **{k: v for k, v in item.items() if k != "keys"}} for name, item in EVALUATIONS.items()
            ],
        )

    def run_experiment(self, request: ExperimentRequest, *, actor_user_id: int) -> ExperimentRun:
        evaluation = EVALUATIONS[request.evaluation]
        configuration = {key: runtime_value(key, self.settings, self.database) for key in REGISTRY}
        configuration.update({name: choices[0] for name, choices in evaluation["options"].items()})
        for key, value in request.overrides.items():
            if key in evaluation["options"]:
                if value not in evaluation["options"][key]:
                    raise ValueError(f"{key} must be one of: {', '.join(evaluation['options'][key])}.")
                configuration[key] = value
            elif key in REGISTRY:
                configuration[key] = REGISTRY[key].check(value)
            else:
                raise ValueError(f"{key} is not a setting this evaluation can change.")
        live = request.evaluation == "agent-benchmark" and configuration["agent_parser_provider"] == "openai"
        if live and self.settings.openai_api_key is None:
            raise ValueError("The OpenAI parser needs OPENAI_API_KEY on the server.")

        now = datetime.now(UTC)
        row = OperationRun(
            trace_id=f"experiment-{uuid4().hex}",
            run_type=EXPERIMENT_RUN_TYPE,
            status="running",
            triggered_by_user_id=actor_user_id,
            input_digest=stable_digest({"evaluation": request.evaluation, "configuration": configuration}),
            code_commit=_code_commit(),
            provider_mode="openai" if live else "fixture",
            algorithm_version=configuration.get("planner"),
            artifact_references=[
                {
                    "kind": "experiment",
                    "data": {
                        "evaluation": request.evaluation,
                        "label": request.label,
                        "configuration": configuration,
                        "metrics": {},
                        "passed": None,
                        "conditions": {"seed": 0, "repeats": 1, "dataset": {"path": evaluation["dataset"]}},
                    },
                }
            ],
            warnings=[],
            created_at=now,
            started_at=now,
        )
        self.database.add(row)
        self.database.commit()
        if live:
            # A live-model run makes one call per case and can take minutes; the list shows it running.
            factory = sessionmaker(bind=self.database.get_bind(), expire_on_commit=False)
            threading.Thread(target=_finish_in_background, args=(factory, row.id, self.settings), daemon=True).start()
            return _experiment_view(row)
        _finish(self.database, row, self.settings)
        return _experiment_view(row)


def _finish_in_background(factory: sessionmaker, run_id: int, settings: Settings) -> None:
    with factory() as database:
        row = database.get(OperationRun, run_id)
        if row is not None:
            _finish(database, row, settings)


def _finish(database: Session, row: OperationRun, settings: Settings) -> None:
    data = dict(row.artifact_references[0]["data"])
    try:
        metrics, passed, dataset = _evaluate(data["evaluation"], data["configuration"], settings)
        data.update(metrics=metrics, passed=passed)
        data["conditions"] = {**data["conditions"], "dataset": dataset}
        row.status = "succeeded"
    except Exception as error:  # noqa: BLE001 - the run records its failure
        row.status = "failed"
        row.error_code = type(error).__name__
        row.error_detail = str(error)[:2000]
    row.artifact_references = [{"kind": "experiment", "data": data}]
    row.finished_at = datetime.now(UTC)
    database.commit()


def _evaluate(name: str, configuration: dict, settings: Settings) -> tuple[dict, bool | None, dict]:
    root = repository_root()
    dataset = root / EVALUATIONS[name]["dataset"]
    if name == "developer-planning":
        from app.evaluation.runner import evaluate  # noqa: PLC0415 - loads the evaluation stack only when run

        result = evaluate(
            ingredient_path=root / "data/ingredients/ingredients.json",
            recipe_path=root / "data/recipes/recipes.json",
            scenario_path=dataset,
            fixture_path=root / "data/fixtures/fairprice-products.json",
            system=configuration["planner"],
        )
        return result["metrics"], result["passed"], result["dataset"]
    from app.evaluation.agent_benchmark import evaluate_agent  # noqa: PLC0415

    provider = configuration["agent_parser_provider"]
    key = settings.openai_api_key.get_secret_value() if provider == "openai" and settings.openai_api_key else None
    result = evaluate_agent(
        dataset_path=dataset,
        provider=provider,
        allow_live_api=provider == "openai",
        api_key=key,
        model=settings.openai_model,
    )
    return result["metrics"], result["metrics"]["failure_case_count"] == 0, result["dataset"]


def _code_commit() -> str | None:
    if commit := os.getenv("CODE_COMMIT"):
        return commit[:64]
    try:
        found = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repository_root(),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.strip()[:64] or None


def _experiment_view(row: OperationRun) -> ExperimentRun:
    data = row.artifact_references[0]["data"]
    return ExperimentRun(
        id=row.id,
        evaluation=data["evaluation"],
        label=data.get("label"),
        status=row.status,
        configuration=data["configuration"],
        metrics=data.get("metrics") or {},
        passed=data.get("passed"),
        conditions={
            **data.get("conditions", {}),
            "code_commit": row.code_commit,
            "parameter_digest": row.input_digest,
        },
        error=row.error_detail,
        created_at=row.created_at,
        duration_seconds=_duration(row.started_at, row.finished_at),
    )
