from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.code_version import code_commit
from app.models.platform import AuditEvent, OperationRun
from app.orchestration.run_lifecycle import stable_digest
from app.repositories.operation_jobs import OperationJobRepository
from app.schemas.operations import ExperimentRequest, PlanningExperimentName, PlanningExperimentParameters

PLANNING_EXPERIMENT_RUN_TYPE = "planning_experiment"

PLANNING_EXPERIMENTS: dict[PlanningExperimentName, dict[str, Any]] = {
    "planning-components": {
        "label": "Planning component ablations",
        "description": "Beam, greedy, diversity, overlap and repair conditions on developer fixtures.",
        "dataset": "data/fixtures/planning-v2/ablation-developer-v1.json",
        "runner": "planning-component-ablation-dev-v1",
    },
    "planning-final-gate": {
        "label": "Final validation gate (single dish)",
        "description": "Paired final-gate diagnostic on fixed single-dish developer fixtures.",
        "dataset": "data/fixtures/planning-v2/final-gate-developer-v1.json",
        "runner": "planning-final-gate-dev-v2",
    },
    "planning-final-gate-composed": {
        "label": "Final validation gate (composed meals)",
        "description": "Paired final-gate diagnostic on composed-meal developer fixtures.",
        "dataset": "data/fixtures/planning-v2/final-gate-composed-developer-v1.json",
        "runner": "planning-final-gate-dev-v2",
    },
}


@dataclass(frozen=True)
class EnqueuedPlanningExperiment:
    run: OperationRun
    created: bool


def normalized_parameters(request: ExperimentRequest) -> dict[str, int]:
    parameters = request.parameters or PlanningExperimentParameters()
    result = {
        "repeats": parameters.repeats,
        "width": parameters.width,
        "max_expansions": parameters.max_expansions,
    }
    if request.evaluation == "planning-components":
        result["repair_rounds"] = 1 if parameters.repair_rounds is None else parameters.repair_rounds
    return result


def planning_experiment_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "label": item["label"],
            "description": item["description"],
            "dataset": item["dataset"],
            "options": {},
            "execution_mode": "durable_worker",
        }
        for name, item in PLANNING_EXPERIMENTS.items()
    ]


class PlanningExperimentService:
    def __init__(self, database: Session, *, actor_user_id: int) -> None:
        self.database = database
        self.actor_user_id = actor_user_id
        self.repository = OperationJobRepository(database)

    def enqueue(self, request: ExperimentRequest, *, idempotency_key: str) -> EnqueuedPlanningExperiment:
        if request.evaluation not in PLANNING_EXPERIMENTS:
            raise ValueError("only registered planning experiments can use the worker")
        parameters = normalized_parameters(request)
        payload = {
            "evaluation": request.evaluation,
            "label": request.label,
            "parameters": parameters,
        }
        digest = stable_digest(payload)
        parameter_digest = stable_digest(parameters)
        run, created = self.repository.enqueue(
            trace_id=f"planning-experiment-{uuid4().hex}",
            run_type=PLANNING_EXPERIMENT_RUN_TYPE,
            triggered_by_user_id=self.actor_user_id,
            input_digest=digest,
            job_payload=payload,
            idempotency_key=idempotency_key,
            code_commit=code_commit(),
        )
        if created:
            registry = PLANNING_EXPERIMENTS[request.evaluation]
            run.algorithm_version = registry["runner"]
            run.provider_mode = "fixture"
            run.artifact_references = [
                {
                    "kind": "planning_experiment",
                    "data": {
                        "evaluation": request.evaluation,
                        "label": request.label,
                        "configuration": parameters,
                        "metrics": {},
                        "passed": None,
                        "conditions": {
                            "dataset": {"registry_key": request.evaluation, "path": registry["dataset"]},
                            "runner": registry["runner"],
                            "parameter_digest": parameter_digest,
                            "seed": None,
                            "repeats": parameters["repeats"],
                            "paid_model": {"used": False, "budget_usd": 0, "usage_usd": 0},
                            "conditions_complete": False,
                            "citation_scope": "developer_diagnostic_only",
                        },
                    },
                }
            ]
            evidence = {
                "operation_run_id": run.id,
                "evaluation": request.evaluation,
                "parameter_digest": parameter_digest,
                "dataset_registry_key": request.evaluation,
            }
            self.database.add(
                AuditEvent(
                    actor_user_id=self.actor_user_id,
                    action="planning_experiment.queued",
                    target_type="operation_run",
                    target_id=str(run.id),
                    after_digest=stable_digest(evidence),
                    details=evidence,
                )
            )
        self.database.commit()
        return EnqueuedPlanningExperiment(run=run, created=created)
