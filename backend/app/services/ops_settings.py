"""Runtime settings and developer evaluations for the operations console (ADR-0047).

Every settings change writes an audit row with its before and after values. Evaluations run only the
developer sets already in the repository; held-out sets are never offered here (ADR-0031 section 3).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent import model_client
from app.core.code_version import code_commit
from app.core.config import Settings
from app.core.paths import repository_root
from app.core.runtime_config import REGISTRY, runtime_value
from app.models.platform import AuditEvent, OperationRun, RuntimeSetting, User
from app.orchestration.run_lifecycle import stable_digest
from app.schemas.operations import (
    ExperimentCollection,
    ExperimentComparison,
    ExperimentDetail,
    ExperimentRequest,
    ExperimentRun,
    RuntimeSettingCollection,
    RuntimeSettingHistory,
    RuntimeSettingHistoryItem,
    RuntimeSettingView,
)
from app.services.operations import _duration
from app.services.ops_planning_experiments import (
    PLANNING_EXPERIMENT_RUN_TYPE,
    planning_experiment_descriptors,
)

EXPERIMENT_RUN_TYPE = "experiment"
# The systems of the protocol-v1 runner (app.evaluation.runner) the console offers, and what each runs (kept
# with the run): the planner the product runs against both baselines. The runner's "mealcraft-planner" is the
# v1 weekly selector its recorded reports name, which the product no longer plans with, so it is not offered.
PLANNERS = {
    "product-planner": "ProductPlanningEngine, beam search: the planner the assistant plans weeks with",
    "greedy-baseline": "Protocol v1 greedy baseline: the top-ranked eligible recipe every night",
    "rule-only-baseline": "Protocol v1 strong rule-only baseline: cheapest, then fastest, no recipe twice in a row",
}

# Developer sets only. Held-out sets stay read-once and are not offered for tuning (ADR-0031 section 3).
EVALUATIONS: dict[str, dict[str, Any]] = {
    "developer-planning": {
        "label": "Developer planning set",
        "description": "Protocol v1: 20 weeks of one dish a dinner on the curated 30-recipe catalog with fixture"
        " prices, scored for each planner on the same candidates.",
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


class ExperimentNotFoundError(LookupError):
    """The requested row is not an experiment visible through this module."""


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
            .where(OperationRun.run_type.in_((EXPERIMENT_RUN_TYPE, PLANNING_EXPERIMENT_RUN_TYPE)))
            .order_by(OperationRun.created_at.desc(), OperationRun.id.desc())
            .limit(limit)
        )
        return ExperimentCollection(
            items=[experiment_view(row) for row in rows],
            evaluations=[
                {
                    "name": name,
                    **{k: v for k, v in item.items() if k != "keys"},
                    "execution_mode": "legacy_inline",
                }
                for name, item in EVALUATIONS.items()
            ]
            + planning_experiment_descriptors(),
        )

    def experiment(self, run_id: int) -> ExperimentDetail:
        row = self.database.get(OperationRun, run_id)
        if row is None or row.run_type not in (EXPERIMENT_RUN_TYPE, PLANNING_EXPERIMENT_RUN_TYPE):
            raise ExperimentNotFoundError(run_id)
        return experiment_detail(row)

    def compare_experiments(self, run_ids: list[int]) -> ExperimentComparison:
        if len(run_ids) != 2 or len(set(run_ids)) != 2 or any(run_id < 1 for run_id in run_ids):
            raise ValueError("comparison requires two distinct positive experiment ids")
        details = [self.experiment(run_id) for run_id in run_ids]
        return experiment_comparison(details[0], details[1])

    def run_experiment(self, request: ExperimentRequest, *, actor_user_id: int) -> ExperimentRun:
        evaluation = EVALUATIONS[request.evaluation]
        # Only what the evaluation reads: a switch it ignores would be recorded, and compared, as if it counted.
        configuration = {key: runtime_value(key, self.settings, self.database) for key in evaluation["keys"]}
        configuration.update({name: choices[0] for name, choices in evaluation["options"].items()})
        for key, value in request.overrides.items():
            if key in evaluation["options"]:
                if value not in evaluation["options"][key]:
                    raise ValueError(f"{key} must be one of: {', '.join(evaluation['options'][key])}.")
                configuration[key] = value
            elif key in evaluation["keys"]:
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
            code_commit=code_commit(),
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
            return experiment_view(row)
        _finish(self.database, row, self.settings)
        return experiment_view(row)


def _finish_in_background(factory: sessionmaker, run_id: int, settings: Settings) -> None:
    with factory() as database:
        row = database.get(OperationRun, run_id)
        if row is not None:
            _finish(database, row, settings)


def _finish(database: Session, row: OperationRun, settings: Settings) -> None:
    data = dict(row.artifact_references[0]["data"])
    try:
        metrics, passed, dataset, report = _evaluate(data["evaluation"], data["configuration"], settings)
        data.update(metrics=metrics, passed=passed, report=report)
        data["conditions"] = {**data["conditions"], "dataset": dataset}
        row.status = "succeeded"
    except Exception as error:  # noqa: BLE001 - the run records its failure
        row.status = "failed"
        row.error_code = type(error).__name__
        row.error_detail = str(error)[:2000]
    row.artifact_references = [{"kind": "experiment", "data": data}]
    row.finished_at = datetime.now(UTC)
    database.commit()


def _evaluate(name: str, configuration: dict, settings: Settings) -> tuple[dict, bool | None, dict, dict]:
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
        report = _case_report(
            result,
            result["scenarios"],
            system=result["system"],
            planner=PLANNERS[result["system"]],
            thresholds=result["thresholds"],
        )
        return result["metrics"], result["passed"], result["dataset"], report
    from app.evaluation.agent_benchmark import evaluate_agent  # noqa: PLC0415

    provider = configuration["agent_parser_provider"]
    key = settings.openai_api_key.get_secret_value() if provider == "openai" and settings.openai_api_key else None
    # The run's own requests to the model API, taken here so they are in its report, not the process-wide count.
    with model_client.counting():
        result = evaluate_agent(
            dataset_path=dataset,
            provider=provider,
            allow_live_api=provider == "openai",
            api_key=key,
            model=settings.openai_model,
        )
        calls = model_client.take().requests
    report = _case_report(
        result, result["cases"], provider=result["provider"], model=result["model"], model_calls=calls
    )
    return result["metrics"], result["metrics"]["failure_case_count"] == 0, result["dataset"], report


def _case_report(result: dict, rows: list[dict], **context: Any) -> dict:
    """Every case a runner scored, in the row shape the drawer and the A/B case diff read (as the worker's)."""
    return {
        **context,
        "category_metrics": result["category_metrics"],
        "runs": [
            {
                "case_id": row["id"],
                "status": "failed" if row["failure_reasons"] else "passed",
                "failures": [{"code": reason} for reason in row["failure_reasons"]],
                **{key: value for key, value in row.items() if key != "id"},
            }
            for row in rows
        ],
    }


def experiment_view(row: OperationRun) -> ExperimentRun:
    data = row.artifact_references[0]["data"]
    conditions = _recorded_conditions(row)
    duration_seconds = _duration(row.started_at, row.finished_at)
    return ExperimentRun(
        id=row.id,
        evaluation=data["evaluation"],
        label=data.get("label"),
        status=row.status,
        configuration=data["configuration"],
        metrics=data.get("metrics") or {},
        passed=data.get("passed"),
        # The server's one verdict, so the list says what the drawer says. The worker's own flag (its fields
        # are written, code_commit aside) stays in storage, where it marks a stored result.
        conditions={
            **conditions,
            "conditions_complete": _reproducibility(row, conditions, duration_seconds)["complete"],
        },
        error=row.error_detail,
        created_at=row.created_at,
        duration_seconds=duration_seconds,
    )


def _recorded_conditions(row: OperationRun) -> dict[str, Any]:
    conditions = row.artifact_references[0]["data"].get("conditions", {})
    return {
        **conditions,
        "code_commit": row.code_commit,
        "parameter_digest": conditions.get("parameter_digest") or row.input_digest,
    }


def experiment_detail(row: OperationRun) -> ExperimentDetail:
    summary = experiment_view(row)
    data = row.artifact_references[0]["data"]
    return ExperimentDetail(
        **summary.model_dump(),
        reproducibility=_reproducibility(row, _recorded_conditions(row), summary.duration_seconds),
        report=data.get("report") if isinstance(data.get("report"), dict) else None,
    )


def _reproducibility(row: OperationRun, conditions: dict[str, Any], duration_seconds: float | None) -> dict:
    dataset = conditions.get("dataset") if isinstance(conditions.get("dataset"), dict) else {}
    paid_model = conditions.get("paid_model") if isinstance(conditions.get("paid_model"), dict) else {}
    required = {
        "code_commit": conditions.get("code_commit"),
        "parameter_digest": conditions.get("parameter_digest"),
        "dataset.path": dataset.get("path"),
        "dataset.file_sha256": _dataset_file_sha(conditions),
        "dataset.semantic_sha256": dataset.get("semantic_sha256"),
        "runner": conditions.get("runner"),
        "code_source": conditions.get("code_source"),
        "product_snapshot_sha256": conditions.get("product_snapshot_sha256"),
        "repeats": conditions.get("repeats"),
        "duration_seconds": conditions.get("duration_seconds") or duration_seconds,
        "paid_model.used": paid_model.get("used") if "used" in paid_model else None,
        "paid_model.budget_usd": paid_model.get("budget_usd"),
        "paid_model.usage_usd": paid_model.get("usage_usd"),
    }
    missing = [name for name, value in required.items() if value is None]
    if conditions.get("conditions_complete") is not True:
        missing.append("conditions_complete")
    if "seed" not in conditions:
        missing.append("seed")
    claim_scope = str(conditions.get("citation_scope") or "not_declared")
    if claim_scope == "not_declared":
        missing.append("citation_scope")
    complete = row.status == "succeeded" and not missing
    warnings = ["Developer diagnostics do not support held-out or production-performance claims."]
    if row.run_type == EXPERIMENT_RUN_TYPE:
        warnings.append("Legacy inline run: reproducibility fields may be incomplete.")
    if row.status != "succeeded":
        warnings.append("Only a succeeded run can be cited.")
    return {
        "complete": complete,
        "citation_allowed": complete and claim_scope == "developer_diagnostic_only",
        "claim_scope": claim_scope,
        "missing": sorted(set(missing)),
        "warnings": warnings,
    }


def experiment_comparison(a: ExperimentDetail, b: ExperimentDetail) -> ExperimentComparison:
    reasons: list[str] = []
    if a.status != "succeeded" or b.status != "succeeded":
        reasons.append("Both runs must have succeeded.")
    if a.evaluation != b.evaluation:
        reasons.append("The runs use different evaluation registries.")
    if not a.reproducibility.complete or not b.reproducibility.complete:
        reasons.append("Both runs need complete recorded conditions.")
    evidence_fields = [
        ("runner", ("runner",), "Runner protocol differs or is missing."),
        ("code_commit", ("code_commit",), "Code revision differs or is missing."),
        ("code_source", ("code_source",), "Implementation fingerprint differs or is missing."),
        ("product_snapshot", ("product_snapshot_sha256",), "Product snapshot differs or is missing."),
        ("seed", ("seed",), "Seed differs or is missing."),
        ("repeats", ("repeats",), "Repeat count differs or is missing."),
        ("claim_scope", ("citation_scope",), "Claim scope differs or is missing."),
    ]
    # The semantic digest when both runs recorded one, else the dataset file's hash; a "file" key says which.
    semantic = [_condition_value(run.conditions, ("dataset", "semantic_sha256")) for run in (a, b)]
    digest_key, digests = (
        ("dataset_digest", semantic)
        if None not in semantic
        else ("dataset_file_digest", [_dataset_file_sha(run.conditions) for run in (a, b)])
    )
    rows = [(digest_key, *digests, "Dataset digest differs or is missing.")] + [
        (key, _condition_value(a.conditions, path), _condition_value(b.conditions, path), message)
        for key, path, message in evidence_fields
    ]
    evidence = []
    for key, left, right, message in rows:
        present = (left is not None and right is not None) or (key == "seed" and left is None and right is None)
        matches = present and left == right
        evidence.append({"key": key, "a": left, "b": right, "matches": matches})
        if not matches:
            reasons.append(message)
    if (
        a.reproducibility.claim_scope != "developer_diagnostic_only"
        or b.reproducibility.claim_scope != "developer_diagnostic_only"
    ):
        reasons.append("Only developer-diagnostic comparison is supported here.")
    compatible = not reasons
    return ExperimentComparison(
        runs=[ExperimentRun.model_validate(a.model_dump()), ExperimentRun.model_validate(b.model_dump())],
        compatible=compatible,
        reasons=list(dict.fromkeys(reasons)),
        evidence=evidence,
        configurations=_comparison_rows(a.configuration, b.configuration),
        metrics=_comparison_rows(a.metrics, b.metrics, deltas=compatible),
        failure_mechanisms=_comparison_rows(
            _mapping(a.conditions.get("failure_mechanisms")),
            _mapping(b.conditions.get("failure_mechanisms")),
        ),
        # None, not "no change", when a run stored no case-level report to compare.
        case_differences=_case_differences(a.report, b.report) if a.report and b.report else None,
        claim_scope="developer_diagnostic_only" if compatible else "not_comparable",
    )


def _dataset_file_sha(conditions: dict[str, Any]) -> Any:
    dataset = conditions.get("dataset") if isinstance(conditions.get("dataset"), dict) else {}
    # The inline runners record the file hash as "sha256".
    return dataset.get("file_sha256") or dataset.get("sha256")


def _condition_value(conditions: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = conditions
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _comparison_rows(a: dict[str, Any], b: dict[str, Any], *, deltas: bool = False) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(set(a) | set(b)):
        left = a.get(key)
        right = b.get(key)
        delta = None
        if (
            deltas
            and isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
        ):
            delta = round(float(right) - float(left), 4)
        rows.append({"key": key, "a": left, "b": right, "delta": delta, "matches": left == right})
    return rows


def _case_differences(a: dict[str, Any] | None, b: dict[str, Any] | None) -> list[dict[str, Any]]:
    left = _indexed_case_rows(a)
    right = _indexed_case_rows(b)
    differences = []
    for key in sorted(set(left) | set(right)):
        a_row = left.get(key, {})
        b_row = right.get(key, {})
        a_failures = _failure_codes(a_row)
        b_failures = _failure_codes(b_row)
        a_status = _case_status(a_row)
        b_status = _case_status(b_row)
        gained = sorted(b_failures - a_failures)
        lost = sorted(a_failures - b_failures)
        if gained or lost or a_status != b_status:
            differences.append(
                {
                    "case_id": key[0],
                    "condition": key[1],
                    "a_status": a_status,
                    "b_status": b_status,
                    "failures_gained": gained,
                    "failures_lost": lost,
                }
            )
    return differences


def _indexed_case_rows(report: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    rows = report.get("runs", []) if isinstance(report, dict) else []
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("case_id"):
            continue
        # A component row names its preset and a gate row pairs gate on and off; an inline run's row is the case.
        condition = str(row.get("preset") or ("paired_gate" if isinstance(row.get("conditions"), dict) else ""))
        if row.get("repeat") is not None:
            condition = f"{condition} repeat {row['repeat']}"
        indexed[(str(row["case_id"]), condition)] = row
    return indexed


def _failure_codes(value: Any) -> set[str]:
    codes: set[str] = set()
    if isinstance(value, dict):
        if value.get("code") and value.get("status") != "passed":
            codes.add(str(value["code"]))
        for nested in value.values():
            codes.update(_failure_codes(nested))
    elif isinstance(value, list):
        for nested in value:
            codes.update(_failure_codes(nested))
    return codes


def _case_status(row: dict[str, Any]) -> str | None:
    if row.get("status") is not None:
        return str(row["status"])
    conditions = row.get("conditions")
    if isinstance(conditions, dict):
        selected = conditions.get("final_gate_on")
        if isinstance(selected, dict):
            audit = selected.get("audit")
            if isinstance(audit, dict) and audit.get("status") is not None:
                return str(audit["status"])
            return "no_selection" if selected.get("candidate_index") is None else "selected"
    return None
