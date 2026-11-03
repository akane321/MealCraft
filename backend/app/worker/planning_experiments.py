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
from app.evaluation.ablation_conditions import ABLATION_CONDITIONS
from app.evaluation.unified_run import run_unified_evaluation
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

        root = repository_root()
        dataset_path = root / registry["dataset"]
        raw = dataset_path.read_bytes()
        started = perf_counter()
        if request.evaluation == "planning-unified":
            product, baselines, ablations = _unified_condition_runners(root, request.parameters)
            report = run_unified_evaluation(product=product, baselines=baselines, ablations=ablations)
            report["protocol"] = report["schema_version"]
            report["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
            report["implementation"] = {"orchestrator": "app.worker.planning_experiments"}
            metrics = {
                "condition_count": len(report["manifest"]),
                "completed_condition_count": sum(row["status"] == "completed" for row in report["results"]),
                "failed_condition_count": sum(row["status"] == "failed" for row in report["results"]),
            }
            mechanisms = Counter(row["label"] for row in report["results"] if row["status"] == "failed")
            dataset = None
        elif request.evaluation == "planning-components":
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
        snapshot_sha256 = _product_snapshot_digest(dataset) if dataset is not None else hashlib.sha256(raw).hexdigest()

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


def _unified_condition_runners(root: Any, parameters: dict[str, int]):
    """Load registered developer inputs, then expose existing runners as one matrix."""
    from app.evaluation.agent_benchmark import evaluate_agent
    from app.evaluation.runner import evaluate
    from app.services.ops_settings import PLANNERS

    component_raw = (root / PLANNING_EXPERIMENTS["planning-components"]["dataset"]).read_bytes()
    gate_raw = (root / PLANNING_EXPERIMENTS["planning-final-gate"]["dataset"]).read_bytes()
    component_dataset = MealExperimentDataset.model_validate_json(component_raw)
    gate_dataset = GateDataset.model_validate_json(gate_raw)
    planning_dataset = root / PLANNING_EXPERIMENTS["planning-unified"]["dataset"]
    agent_dataset = root / "data/evaluation/agent/fixture-v1.json"
    common = {
        "ingredient_path": root / "data/ingredients/ingredients.json",
        "recipe_path": root / "data/recipes/recipes.json",
        "scenario_path": planning_dataset,
        "fixture_path": root / "data/fixtures/fairprice-products.json",
    }
    component_cache: dict[str, dict] = {}

    def planning(system: str, **options: Any):
        return lambda: evaluate(**common, system=system, **options)

    def component(condition: str):
        def run() -> dict:
            if "report" not in component_cache:
                component_cache["report"] = run_experiments(component_dataset, **parameters)
            report = component_cache["report"]
            return {**report, "runs": [row for row in report["runs"] if row["preset"] == condition]}

        return run

    def final_gate_off() -> dict:
        report = run_gate_experiments(
            gate_dataset,
            width=parameters["width"],
            max_expansions=parameters["max_expansions"],
        )
        return report

    ablations = {
        "retrieval_off": component("retrieval_off"),
        "rule_only_parser": lambda: evaluate_agent(dataset_path=agent_dataset, provider="fixture"),
        "independent_validator_off": final_gate_off,
        "repair_off": component("repair_off"),
        "diversity_off": component("diversity_off"),
        "local_improvement_off": planning("product-planner", local_improvement=False),
    }
    assert set(ablations) == set(ABLATION_CONDITIONS)
    return (
        planning("product-planner"),
        tuple((system, planning(system)) for system in PLANNERS if system != "product-planner"),
        ablations,
    )


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
    # Without the gate the first draft ships; a case with no draft at all has no audit and ships nothing.
    unchecked = [row["conditions"]["final_gate_off"].get("audit") for row in report["runs"]]
    return (
        {
            "case_count": case_count,
            "gate_selected_count": sum(
                row["conditions"]["final_gate_on"]["candidate_index"] is not None for row in report["runs"]
            ),
            "unchecked_invalid_count": sum(
                audit is not None and audit.get("status") != "passed" for audit in unchecked
            ),
            "unchecked_no_candidate_count": sum(audit is None for audit in unchecked),
        },
        dict(sorted(mechanisms.items())),
    )
