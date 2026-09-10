from pathlib import Path

from app.core.paths import repository_root
from app.evaluation.orchestration_benchmark import (
    evaluate_grounding,
    evaluate_scope_policy,
    write_scope_report,
)

ROOT = repository_root()
DATASET = ROOT / "data" / "evaluation" / "agent-orchestration" / "scope-developer-v1.json"
GROUNDING_DATASET = ROOT / "data/evaluation/agent-orchestration/grounding-developer-v1.json"


def test_scope_developer_set_is_versioned_and_offline() -> None:
    report = evaluate_scope_policy(dataset_path=DATASET)

    assert report["evaluation_role"] == "developer_set"
    assert report["live_api_used"] is False
    assert report["dataset"]["case_count"] == 36
    assert report["dataset"]["language_counts"] == {"en": 20, "mixed": 1, "zh": 15}
    assert len(report["dataset"]["sha256"]) == 64


def test_scope_reference_policy_has_no_known_developer_set_failures() -> None:
    report = evaluate_scope_policy(dataset_path=DATASET)

    assert report["metrics"]["classification_accuracy"] == 1.0
    assert report["metrics"]["macro_f1"] == 1.0
    assert report["metrics"]["mutating_case_count"] == 13
    assert report["metrics"]["non_mutating_case_count"] == 23
    assert report["metrics"]["false_accept_count"] == 0
    assert report["metrics"]["false_reject_count"] == 0
    assert report["metrics"]["state_contamination_count"] == 0
    assert report["metrics"]["tool_policy_accuracy"] == 1.0
    assert report["failure_cases"] == []


def test_scope_report_is_machine_and_human_readable(tmp_path: Path) -> None:
    report = evaluate_scope_policy(dataset_path=DATASET)
    json_path = tmp_path / "scope.json"
    markdown_path = tmp_path / "scope.md"

    write_scope_report(report, json_path=json_path, markdown_path=markdown_path)

    assert '"evaluation_role": "developer_set"' in json_path.read_text(encoding="utf-8")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "not final held-out evidence" in markdown
    assert "State contamination: **0**" in markdown


def test_grounding_developer_set_blocks_known_high_risk_claims() -> None:
    report = evaluate_grounding(dataset_path=GROUNDING_DATASET)

    assert report["evaluation_role"] == "developer_set"
    assert report["live_api_used"] is False
    assert report["dataset"]["case_count"] == 12
    assert report["metrics"]["supported_case_count"] == 4
    assert report["metrics"]["unsupported_case_count"] == 8
    assert report["metrics"]["verification_accuracy"] == 1.0
    assert report["metrics"]["unsupported_claim_escape_count"] == 0
    assert report["metrics"]["supported_claim_rejection_count"] == 0
    assert report["failure_cases"] == []
