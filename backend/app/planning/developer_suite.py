"""Fixed developer-only Planning suite for CLI and future console consumers."""

import argparse
import json
from pathlib import Path

from app.core.paths import repository_root
from app.planning.developer_experiments import MealExperimentDataset, run_experiments, source_fingerprint
from app.planning.feedback_plan_experiments import FeedbackPlanDataset, plan_with_feedback
from app.planning.feedback_ranking import FeedbackReplay, replay_feedback
from app.planning.validation_gate_experiments import GateDataset, run_gate_experiments

DATASETS = {
    "single_components": "ablation-developer-v1.json",
    "composed_components": "composed-ablation-developer-v1.json",
    "single_gate": "final-gate-developer-v1.json",
    "composed_gate": "final-gate-composed-developer-v1.json",
    "feedback": "feedback-ranking-developer-v1.json",
    "feedback_plans": "feedback-plan-developer-v1.json",
}


def run_planning_suite(*, repeats=3):
    """No user data, live provider, arbitrary dataset path, or persistence side effect.

    Consumers store the returned JSON intact, including conditions and caveats.
    A completed diagnostic is not an assertion that every draft passed validation.
    """
    if type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer in [1, 20]")
    root = repository_root() / "data/fixtures/planning-v2"
    reports = {}
    for key, name in DATASETS.items():
        raw = (root / name).read_bytes()
        if key.endswith("components"):
            report = run_experiments(MealExperimentDataset.model_validate_json(raw), repeats=repeats)
        elif key.endswith("gate"):
            report = run_gate_experiments(GateDataset.model_validate_json(raw))
        elif key == "feedback_plans":
            data = FeedbackPlanDataset.model_validate_json(raw)
            report = {
                "dataset_version": data.version,
                "conditions": {
                    name: plan_with_feedback(
                        data.problem, data.events, scope_id=data.scope_id, decision_at=data.decision_at, enabled=enabled
                    )
                    for name, enabled in (("off", False), ("on", True))
                },
            }
        else:
            report = replay_feedback(FeedbackReplay.model_validate_json(raw))
        reports[key] = report
    return {
        "schema_version": "planning-developer-suite-v1",
        "evidence": "developer_diagnostic",
        "conditions": {
            "provider": "fixture",
            "component_repeats": repeats,
            "gate_repeats": 1,
            "feedback_repeats": 1,
            "capability": "offline-components",
            "datasets": dict(DATASETS),
        },
        "implementation": source_fingerprint(),
        "reports": reports,
        "limitations": [
            "No held-out or end-to-end product claim.",
            "Final gate off retains search-side constraint checks.",
            "Composed greedy preset is width-one meal beam, not evaluation B1.",
            "Feedback replay measures agreement with logged choices, not causal benefit.",
            "No trained personalization model, console route, product activation or data export.",
        ],
    }


def analysis_markdown(report):
    """Generate counts and failure mechanisms, without per-category rates or winners."""
    lines = [
        "# Planning developer diagnostics",
        "",
        "Synthetic component checks only. These counts are not task-success rates.",
        "",
    ]
    for key in ("single_components", "composed_components"):
        data = report["reports"][key]
        lines += [f"## {key}", "", f"Dataset: `{data['dataset_version']}`; digest: `{data['dataset_sha256']}`.", ""]
        for category, count in data["category_counts"].items():
            lines.append(f"- Category `{category}`: {count} input cases.")
        lines += ["", "Individual failed or indeterminate checks (first repeat; repeated runs remain in JSON):", ""]
        for row in data["runs"]:
            if row["status"] == "not_applicable":
                lines.append(f"- `{row['case_id']}` / `{row['preset']}`: not applicable; {row['reason']}.")
            elif row["repeat"] == 0 and row["audit"]["status"] != "passed":
                codes = ", ".join(sorted({f["code"] for f in row["failures"]}))
                lines.append(
                    f"- `{row['case_id']}` / `{row['preset']}`: {row['audit']['status']}; "
                    f"{codes}; stop `{row['stop_reason']}`."
                )
    lines += ["", "## Final gate observations", ""]
    for key in ("single_gate", "composed_gate"):
        for row in report["reports"][key]["runs"]:
            values = []
            for name, condition in row["conditions"].items():
                audit = condition["audit"]
                values.append(f"{name}: {audit['status'] if audit else 'no selection'}")
            lines.append(f"- `{row['case_id']}`: {'; '.join(values)}.")
    replay = report["reports"]["feedback"]
    lines += [
        "",
        "## Feedback replay",
        "",
        f"{replay['decision_count']} recorded decisions; {replay['cooked_choice_count']} cooked-choice labels.",
    ]
    for policy, matches in replay["cooked_choice_top1_matches"].items():
        lines.append(f"- `{policy}`: {matches} top-choice agreements.")
    lines += ["", replay["claim_scope"] + ".", "", "## Feedback plan audit", ""]
    for name, condition in report["reports"]["feedback_plans"]["conditions"].items():
        lines.append(
            f"- `{name}`: {condition['audit']['status']}; selected "
            f"{[a['recipe_id'] for a in condition['assignments']]}. "
            "Synthetic component outcome, not personalization evidence."
        )
    lines += ["", "## Limits", ""]
    lines += ["- " + text for text in report["limitations"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()
    if args.json_report.resolve() == args.markdown_report.resolve():
        parser.error("Report paths must be different")
    report = run_planning_suite(repeats=args.repeats)
    args.json_report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.markdown_report.write_text(analysis_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
