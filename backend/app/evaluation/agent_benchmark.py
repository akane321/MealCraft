"""Offline-first benchmark for the constraint-extraction agent boundary."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.parser import AgentConfigurationError, OpenAIConstraintParser, RuleBasedConstraintParser
from app.agent.workflow import AgentConstraintWorkflow
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState

AgentEvaluationProvider = Literal["fixture", "openai"]


class AgentBenchmarkCase(BaseModel):
    id: str
    category: str
    language: Literal["en", "zh", "mixed"]
    message: str
    current_constraints: dict[str, Any] = Field(default_factory=dict)
    acknowledged_unknowns: list[str] = Field(default_factory=list)
    expected_extraction: dict[str, Any] = Field(default_factory=dict)
    expected_missing_fields: list[str] = Field(default_factory=list)
    expect_medical_boundary: bool = False


@dataclass
class AgentCaseResult:
    id: str
    category: str
    language: str
    exact_match: bool
    matched_fields: int
    expected_fields: int
    predicted_fields: int
    hallucinated_fields: list[str]
    mismatched_fields: list[str]
    missing_fields_match: bool
    medical_boundary_match: bool
    actual_extraction: dict[str, Any]
    actual_missing_fields: list[str]
    failure_reasons: list[str]


def _meaningful_fields(payload: dict[str, Any]) -> dict[str, Any]:
    ignored = {"assistant_summary", "acknowledged_unknown_quantities"}
    meaningful: dict[str, Any] = {}
    for key, value in payload.items():
        if key in ignored or value is None or value is False or value == [] or value == {}:
            continue
        if key == "nutrition_targets" and isinstance(value, dict):
            targets = {name: number for name, number in value.items() if number is not None}
            if targets:
                meaningful[key] = targets
            continue
        meaningful[key] = value
    return meaningful


def _load_cases(path: Path) -> list[AgentBenchmarkCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [AgentBenchmarkCase.model_validate(item) for item in raw]


def _build_parser(
    provider: AgentEvaluationProvider,
    *,
    allow_live_api: bool,
    api_key: str | None,
    model: str,
):
    if provider == "fixture":
        return RuleBasedConstraintParser()
    if not allow_live_api:
        raise AgentConfigurationError(
            "OpenAI evaluation is disabled by default. Pass --allow-live-api explicitly to enable it."
        )
    if not api_key:
        raise AgentConfigurationError("OpenAI evaluation requires an API key supplied at runtime.")
    return OpenAIConstraintParser(api_key=api_key, model=model)


def evaluate_agent(
    *,
    dataset_path: Path,
    provider: AgentEvaluationProvider = "fixture",
    allow_live_api: bool = False,
    api_key: str | None = None,
    model: str = "gpt-5.4-mini",
) -> dict[str, Any]:
    """Evaluate extraction and clarification without using a live API by default."""
    parser = _build_parser(provider, allow_live_api=allow_live_api, api_key=api_key, model=model)
    workflow = AgentConstraintWorkflow(parser)
    cases = _load_cases(dataset_path)
    results: list[AgentCaseResult] = []

    for case in cases:
        current = AgentConstraintState.model_validate(case.current_constraints)
        extraction = parser.parse(
            case.message,
            current=current,
            acknowledged_unknowns=case.acknowledged_unknowns,
            history=[],
        )
        actual = _meaningful_fields(extraction.model_dump(mode="json"))
        expected = _meaningful_fields(
            AgentConstraintExtraction.model_validate(case.expected_extraction).model_dump(mode="json")
        )
        mismatched = sorted(key for key, value in expected.items() if actual.get(key) != value)
        hallucinated = sorted(key for key in actual if key not in expected)
        matched = len(expected) - len(mismatched)

        state = workflow.run(
            case.message,
            current=current,
            acknowledged_unknowns=case.acknowledged_unknowns,
            history=[],
        )
        actual_missing = sorted(state["missing_fields"])
        missing_match = actual_missing == sorted(case.expected_missing_fields)
        boundary_text = state["assistant_message"].lower()
        boundary_match = not case.expect_medical_boundary or "does not provide disease-specific" in boundary_text
        failure_reasons: list[str] = []
        if mismatched:
            failure_reasons.append("extraction_mismatch")
        if hallucinated:
            failure_reasons.append("hallucinated_field")
        if not missing_match:
            failure_reasons.append("clarification_mismatch")
        if not boundary_match:
            failure_reasons.append("medical_boundary_missing")

        results.append(
            AgentCaseResult(
                id=case.id,
                category=case.category,
                language=case.language,
                exact_match=not failure_reasons,
                matched_fields=matched,
                expected_fields=len(expected),
                predicted_fields=len(actual),
                hallucinated_fields=hallucinated,
                mismatched_fields=mismatched,
                missing_fields_match=missing_match,
                medical_boundary_match=boundary_match,
                actual_extraction=actual,
                actual_missing_fields=actual_missing,
                failure_reasons=failure_reasons,
            )
        )

    matched_fields = sum(item.matched_fields for item in results)
    expected_fields = sum(item.expected_fields for item in results)
    predicted_fields = sum(item.predicted_fields for item in results)
    precision = matched_fields / max(predicted_fields, 1)
    recall = matched_fields / max(expected_fields, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    metrics = {
        "case_count": len(results),
        "exact_case_rate": round(sum(item.exact_match for item in results) / max(len(results), 1), 4),
        "field_precision": round(precision, 4),
        "field_recall": round(recall, 4),
        "field_f1": round(f1, 4),
        "hallucinated_field_count": sum(len(item.hallucinated_fields) for item in results),
        "clarification_accuracy": round(sum(item.missing_fields_match for item in results) / max(len(results), 1), 4),
        "medical_boundary_accuracy": round(
            sum(item.medical_boundary_match for item in results) / max(len(results), 1), 4
        ),
        "failure_case_count": sum(bool(item.failure_reasons) for item in results),
    }
    return {
        "schema_version": "1.0",
        "provider": provider,
        "model": model if provider == "openai" else None,
        "live_api_used": provider == "openai",
        "dataset": {
            "path": dataset_path.as_posix(),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        },
        "metrics": metrics,
        "failure_cases": [asdict(item) for item in results if item.failure_reasons],
        "cases": [asdict(item) for item in results],
    }
