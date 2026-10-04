from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.models.platform import OperationRun
from app.orchestration.run_lifecycle import stable_digest
from app.planning.developer_experiments import MealExperimentDataset, digest, run_experiments
from app.planning.validation_gate_experiments import GateDataset, run_gate_experiments
from app.schemas.operations import PlanningExperimentName
from app.services.ops_planning_experiments import PLANNING_EXPERIMENT_RUN_TYPE, PLANNING_EXPERIMENTS


class PlanningExperimentJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation: PlanningExperimentName
    label: str | None = None
    parameters: dict[str, int]


def run_planning_experiment_handler(payload: dict, database_url: str, context: Any) -> None:
    request = PlanningExperimentJobPayload.model_validate(payload)
    registry = PLANNING_EXPERIMENTS[request.evaluation]
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            current = session.get(OperationRun, context.run_id)
            if current is None or not _owns_attempt(current, context.attempt_count):
                return
            if _has_complete_result(current):
                return

        dataset_path = repository_root() / registry["dataset"]
        raw = dataset_path.read_bytes()
        started = perf_counter()
        if request.evaluation == "planning-components":
            dataset = MealExperimentDataset.model_validate_json(raw)
            report = run_experiments(dataset, **request.parameters)
            metrics, mechanisms = _component_summary(report, len(dataset.cases))
        else:
            dataset = GateDataset.model_validate_json(raw)
            report = run_gate_experiments(
                dataset,
                width=request.parameters["width"],
                max_expansions=request.parameters["max_expansions"],
            )
            metrics, mechanisms = _gate_summary(report, len(dataset.cases))
        duration_seconds = perf_counter() - started
        file_sha256 = hashlib.sha256(raw).hexdigest()
        snapshot_sha256 = _product_snapshot_digest(dataset)

        artifact = {
            "kind": "planning_experiment",
            "data": {
                "evaluation": request.evaluation,
                "label": request.label,
                "configuration": request.parameters,
                "metrics": metrics,
                "passed": None,
                "conditions": {
                    "dataset": {
                        "registry_key": request.evaluation,
                        "path": registry["dataset"],
                        "file_sha256": file_sha256,
                        "semantic_sha256": report["dataset_sha256"],
                    },
                    "runner": report["protocol"],
                    "code_source": report["implementation"],
                    "parameter_digest": stable_digest(request.parameters),
                    "seed": None,
                    "repeats": request.parameters["repeats"],
                    "product_snapshot_sha256": snapshot_sha256,
                    "duration_seconds": duration_seconds,
                    "failure_mechanisms": mechanisms,
                    "paid_model": {"used": False, "budget_usd": 0, "usage_usd": 0},
                    "conditions_complete": True,
                    "citation_scope": "developer_diagnostic_only",
                },
                "report": report,
            },
        }

        with Session(engine) as session:
            run = session.scalars(
                select(OperationRun).where(OperationRun.id == context.run_id).with_for_update()
            ).one_or_none()
            if run is None or not _owns_attempt(run, context.attempt_count):
                return
            if _has_complete_result(run):
                return
            run.artifact_references = [artifact]
            run.product_snapshot_version = f"sha256:{snapshot_sha256}"
            run.algorithm_version = report["protocol"]
            session.commit()
    finally:
        engine.dispose()


def _owns_attempt(run: OperationRun, attempt_count: int) -> bool:
    lease_now = datetime.now(UTC)
    if run.lease_expires_at is not None and run.lease_expires_at.tzinfo is None:
        lease_now = lease_now.replace(tzinfo=None)
    return (
        run.run_type == PLANNING_EXPERIMENT_RUN_TYPE
        and run.status == "running"
        and run.attempt_count == attempt_count
        and run.lease_expires_at is not None
        and run.lease_expires_at > lease_now
    )


def _has_complete_result(run: OperationRun) -> bool:
    return bool(
        run.artifact_references
        and run.artifact_references[0].get("kind") == "planning_experiment"
        and run.artifact_references[0].get("data", {}).get("conditions", {}).get("conditions_complete") is True
    )


def _product_snapshot_digest(dataset: Any) -> str:
    snapshots = [
        {
            "case_id": case.case_id,
            "version": case.problem.product_snapshot_version,
            "products": [product.model_dump(mode="json") for product in case.problem.products],
            "repair_snapshots": case.snapshots,
        }
        for case in dataset.cases
    ]
    return digest(snapshots)


def _component_summary(report: dict, case_count: int) -> tuple[dict[str, int], dict[str, int]]:
    applicable = [row for row in report["runs"] if row["status"] != "not_applicable"]
    mechanisms = Counter(failure["code"] for row in applicable for failure in row.get("failures", []))
    return (
        {
            "case_count": case_count,
            "condition_run_count": len(applicable),
            "not_applicable_count": len(report["runs"]) - len(applicable),
            "passed_audit_count": sum(row["audit"]["status"] == "passed" for row in applicable),
        },
        dict(sorted(mechanisms.items())),
    )


def _gate_summary(report: dict, case_count: int) -> tuple[dict[str, int], dict[str, int]]:
    mechanisms = Counter(
        failure["code"]
        for row in report["runs"]
        for candidate in row["candidate_checks"]
        for failure in candidate["failures"]
    )
    return (
        {
            "case_count": case_count,
            "gate_selected_count": sum(
                row["conditions"]["final_gate_on"]["candidate_index"] is not None for row in report["runs"]
            ),
            "unchecked_invalid_count": sum(
                (row["conditions"]["final_gate_off"].get("audit") or {}).get("status") != "passed"
                for row in report["runs"]
            ),
        },
        dict(sorted(mechanisms.items())),
    )
