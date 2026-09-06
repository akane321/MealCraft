"""Deterministic evaluation for the bounded Agent scope gate.

This module evaluates the reference policy on a versioned developer set. It is
deliberately separate from the held-out Agent benchmark: these cases may be used
while developing the policy and therefore must not be reported as final
generalisation evidence.
"""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.parser import RuleBasedConstraintParser
from app.orchestration.contracts import ActionReceipt, EvidenceFact, ResponseClaim, ScopeClass
from app.orchestration.grounding import verify_structured_claims
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.schemas.agent import AgentConstraintState


class ScopeBenchmarkCase(BaseModel):
    id: str
    language: str
    category: str
    message: str
    expected_class: ScopeClass
    expected_state_mutation: bool
    expected_tool_call: bool


class GroundingBenchmarkCase(BaseModel):
    id: str
    category: str
    claim: ResponseClaim
    evidence: list[EvidenceFact] = Field(default_factory=list)
    action_receipts: list[ActionReceipt] = Field(default_factory=list)
    expected_supported: bool


@dataclass
class ScopeCaseResult:
    id: str
    language: str
    category: str
    expected_class: str
    actual_class: str
    classification_correct: bool
    expected_state_mutation: bool
    actual_state_mutation: bool
    expected_tool_call: bool
    actual_tool_call: bool
    state_contaminated: bool
    reason_code: str
    failure_reasons: list[str]


@dataclass
class GroundingCaseResult:
    id: str
    category: str
    expected_supported: bool
    actual_supported: bool
    reason_code: str | None
    failure_reasons: list[str]


def _load_cases(path: Path) -> list[ScopeBenchmarkCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ScopeBenchmarkCase.model_validate(item) for item in raw]


def _load_grounding_cases(path: Path) -> list[GroundingBenchmarkCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GroundingBenchmarkCase.model_validate(item) for item in raw]


def _class_metrics(results: list[ScopeCaseResult]) -> tuple[dict[str, dict[str, float | int]], float]:
    labels = sorted({item.expected_class for item in results} | {item.actual_class for item in results})
    metrics: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    for label in labels:
        true_positive = sum(item.expected_class == label and item.actual_class == label for item in results)
        false_positive = sum(item.expected_class != label and item.actual_class == label for item in results)
        false_negative = sum(item.expected_class == label and item.actual_class != label for item in results)
        support = sum(item.expected_class == label for item in results)
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        f1_values.append(f1)
        metrics[label] = {
            "support": support,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return metrics, round(sum(f1_values) / max(len(f1_values), 1), 4)


def evaluate_scope_policy(*, dataset_path: Path) -> dict[str, Any]:
    """Evaluate classification and state isolation without external services."""
    cases = _load_cases(dataset_path)
    policy = ReferenceScopePolicy()
    orchestrator = BoundedAgentOrchestrator(RuleBasedConstraintParser(), scope_policy=policy)
    results: list[ScopeCaseResult] = []

    for case in cases:
        initial = AgentConstraintState(
            household_size=5,
            max_cooking_time_minutes=45,
            weekly_budget_sgd=125,
            allergens=["sesame"],
        )
        decision = policy.classify(case.message)
        outcome = orchestrator.process(
            case.message,
            current=initial,
            acknowledged_unknowns=[],
            history=[],
            current_status="ready",
            current_missing_fields=[],
            current_questions=[],
            context_version=7,
        )
        state_contaminated = False
        if not case.expected_state_mutation:
            state_contaminated = (
                outcome.state_mutated
                or outcome.context_version != 7
                or outcome.constraints.model_dump(mode="json") != initial.model_dump(mode="json")
            )

        failure_reasons: list[str] = []
        if decision.scope_class is not case.expected_class:
            failure_reasons.append("scope_class_mismatch")
        if decision.should_mutate_state != case.expected_state_mutation:
            failure_reasons.append("state_mutation_policy_mismatch")
        if decision.should_call_tools != case.expected_tool_call:
            failure_reasons.append("tool_policy_mismatch")
        if state_contaminated:
            failure_reasons.append("state_contamination")

        results.append(
            ScopeCaseResult(
                id=case.id,
                language=case.language,
                category=case.category,
                expected_class=case.expected_class.value,
                actual_class=decision.scope_class.value,
                classification_correct=decision.scope_class is case.expected_class,
                expected_state_mutation=case.expected_state_mutation,
                actual_state_mutation=decision.should_mutate_state,
                expected_tool_call=case.expected_tool_call,
                actual_tool_call=decision.should_call_tools,
                state_contaminated=state_contaminated,
                reason_code=decision.reason_code,
                failure_reasons=failure_reasons,
            )
        )

    class_metrics, macro_f1 = _class_metrics(results)
    false_accepts = sum(not item.expected_state_mutation and item.actual_state_mutation for item in results)
    false_rejects = sum(item.expected_state_mutation and not item.actual_state_mutation for item in results)
    mutating_cases = sum(item.expected_state_mutation for item in results)
    non_mutating_cases = len(results) - mutating_cases
    contamination_cases = sum(item.state_contaminated for item in results)
    classification_correct = sum(item.classification_correct for item in results)
    tool_policy_correct = sum(item.expected_tool_call == item.actual_tool_call for item in results)
    language_counts = Counter(item.language for item in results)
    return {
        "schema_version": "1.0",
        "evaluation_role": "developer_set",
        "policy": "reference-lexical-v1",
        "live_api_used": False,
        "dataset": {
            "path": dataset_path.as_posix(),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "case_count": len(results),
            "language_counts": dict(sorted(language_counts.items())),
        },
        "metrics": {
            "classification_accuracy": round(classification_correct / max(len(results), 1), 4),
            "macro_f1": macro_f1,
            "mutating_case_count": mutating_cases,
            "non_mutating_case_count": non_mutating_cases,
            "false_accept_count": false_accepts,
            "false_accept_rate": round(false_accepts / max(non_mutating_cases, 1), 4),
            "false_reject_count": false_rejects,
            "false_reject_rate": round(false_rejects / max(mutating_cases, 1), 4),
            "state_contamination_count": contamination_cases,
            "state_contamination_rate": round(contamination_cases / max(non_mutating_cases, 1), 4),
            "tool_policy_accuracy": round(tool_policy_correct / max(len(results), 1), 4),
            "failure_case_count": sum(bool(item.failure_reasons) for item in results),
        },
        "class_metrics": class_metrics,
        "failure_cases": [asdict(item) for item in results if item.failure_reasons],
        "cases": [asdict(item) for item in results],
    }


def write_scope_report(report: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Agent Scope Developer-set Evaluation",
        "",
        "> This is a developer set used to build the reference policy. It is not final held-out evidence.",
        "",
        f"- Dataset SHA-256: `{report['dataset']['sha256']}`",
        f"- Cases: **{report['dataset']['case_count']}**",
        f"- Classification accuracy: **{report['metrics']['classification_accuracy']}**",
        f"- Macro-F1: **{report['metrics']['macro_f1']}**",
        f"- False accepts: **{report['metrics']['false_accept_count']}**",
        f"- False rejects: **{report['metrics']['false_reject_count']}**",
        f"- State contamination: **{report['metrics']['state_contamination_count']}**",
        "",
        "## Per-class metrics",
        "",
        "| Class | N | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, values in report["class_metrics"].items():
        lines.append(
            f"| `{label}` | {values['support']} | {values['precision']} | {values['recall']} | {values['f1']} |"
        )
    lines.extend(["", "## Failure cases", "", "| ID | Expected | Actual | Reasons |", "|---|---|---|---|"])
    for item in report["failure_cases"]:
        lines.append(
            f"| {item['id']} | {item['expected_class']} | {item['actual_class']} | "
            f"{', '.join(item['failure_reasons'])} |"
        )
    if not report["failure_cases"]:
        lines.append("| - | - | - | No failures recorded |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_grounding(*, dataset_path: Path) -> dict[str, Any]:
    """Evaluate typed evidence/receipt verification on a visible developer set."""
    cases = _load_grounding_cases(dataset_path)
    results: list[GroundingCaseResult] = []
    for case in cases:
        report = verify_structured_claims([case.claim], case.evidence, case.action_receipts)
        actual_supported = case.claim.claim_id in report.supported_claim_ids
        failure_reasons: list[str] = []
        if actual_supported != case.expected_supported:
            failure_reasons.append("unsupported_claim_escaped" if actual_supported else "supported_claim_rejected")
        results.append(
            GroundingCaseResult(
                id=case.id,
                category=case.category,
                expected_supported=case.expected_supported,
                actual_supported=actual_supported,
                reason_code=report.unsupported_reason_codes.get(case.claim.claim_id),
                failure_reasons=failure_reasons,
            )
        )

    positive_cases = sum(item.expected_supported for item in results)
    negative_cases = len(results) - positive_cases
    false_supports = sum(not item.expected_supported and item.actual_supported for item in results)
    false_rejections = sum(item.expected_supported and not item.actual_supported for item in results)
    correct = sum(item.expected_supported == item.actual_supported for item in results)
    category_metrics: dict[str, dict[str, float | int]] = {}
    for category in sorted({item.category for item in results}):
        category_results = [item for item in results if item.category == category]
        category_metrics[category] = {
            "case_count": len(category_results),
            "accuracy": round(
                sum(item.expected_supported == item.actual_supported for item in category_results)
                / max(len(category_results), 1),
                4,
            ),
        }
    return {
        "schema_version": "1.0",
        "evaluation_role": "developer_set",
        "verifier": "typed-evidence-and-receipt-v1",
        "live_api_used": False,
        "dataset": {
            "path": dataset_path.as_posix(),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "case_count": len(results),
        },
        "metrics": {
            "verification_accuracy": round(correct / max(len(results), 1), 4),
            "supported_case_count": positive_cases,
            "unsupported_case_count": negative_cases,
            "unsupported_claim_escape_count": false_supports,
            "unsupported_claim_escape_rate": round(false_supports / max(negative_cases, 1), 4),
            "supported_claim_rejection_count": false_rejections,
            "supported_claim_rejection_rate": round(false_rejections / max(positive_cases, 1), 4),
            "failure_case_count": sum(bool(item.failure_reasons) for item in results),
        },
        "category_metrics": category_metrics,
        "failure_cases": [asdict(item) for item in results if item.failure_reasons],
        "cases": [asdict(item) for item in results],
    }
