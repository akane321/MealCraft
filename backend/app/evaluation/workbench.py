"""Generate the versioned MealCraft evaluation evidence bundle."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.evaluation.agent_benchmark import evaluate_agent
from app.evaluation.runner import evaluate


def _delta(full: dict[str, Any], baseline: dict[str, Any], metric: str) -> float:
    return round(full["metrics"][metric] - baseline["metrics"][metric], 4)


def build_workbench(
    *,
    ingredient_path: Path,
    recipe_path: Path,
    developer_path: Path,
    heldout_path: Path,
    agent_path: Path,
    fixture_path: Path,
    agent_provider: str = "fixture",
    allow_live_api: bool = False,
    api_key: str | None = None,
    model: str = "gpt-5.4-mini",
) -> dict[str, Any]:
    developer = evaluate(
        ingredient_path=ingredient_path,
        recipe_path=recipe_path,
        scenario_path=developer_path,
        fixture_path=fixture_path,
    )
    baseline = evaluate(
        ingredient_path=ingredient_path,
        recipe_path=recipe_path,
        scenario_path=heldout_path,
        fixture_path=fixture_path,
        system="greedy-baseline",
        enforce_gates=False,
    )
    planner = evaluate(
        ingredient_path=ingredient_path,
        recipe_path=recipe_path,
        scenario_path=heldout_path,
        fixture_path=fixture_path,
        system="mealcraft-planner",
        enforce_gates=False,
    )
    agent = evaluate_agent(
        dataset_path=agent_path,
        provider=agent_provider,
        allow_live_api=allow_live_api,
        api_key=api_key,
        model=model,
    )
    return {
        "schema_version": "1.0",
        "protocol": "docs/evaluation/protocol-v1.md",
        "developer_gate_passed": developer["passed"],
        "api_evaluation": {
            "provider": agent_provider,
            "live_api_used": agent["live_api_used"],
            "status": "enabled explicitly" if agent["live_api_used"] else "reserved; not used",
        },
        "comparison": {
            "expectation_rate_delta": _delta(planner, baseline, "scenario_expectation_rate"),
            "mean_distinct_recipes_delta": _delta(planner, baseline, "mean_distinct_recipes"),
            "consecutive_repetition_reduction": (
                baseline["metrics"]["consecutive_repetition_count"] - planner["metrics"]["consecutive_repetition_count"]
            ),
            "failure_case_reduction": (
                baseline["metrics"]["failure_case_count"] - planner["metrics"]["failure_case_count"]
            ),
        },
        "developer_planning": developer,
        "heldout_greedy_baseline": baseline,
        "heldout_mealcraft_planner": planner,
        "agent_benchmark": agent,
        "failure_registry": [
            *[{"source": "heldout-greedy-baseline", **item} for item in baseline["failure_cases"]],
            *[{"source": "heldout-mealcraft-planner", **item} for item in planner["failure_cases"]],
            *[{"source": "agent-benchmark", **item} for item in agent["failure_cases"]],
        ],
    }


def write_workbench(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    comparison = report["comparison"]
    developer = report["developer_planning"]
    baseline = report["heldout_greedy_baseline"]
    planner = report["heldout_mealcraft_planner"]
    agent = report["agent_benchmark"]
    lines = [
        "# MealCraft Evaluation Workbench",
        "",
        "> Generated evidence. Method, split rules and metric definitions are fixed in "
        "[`protocol-v1.md`](../protocol-v1.md).",
        "",
        "## Run status",
        "",
        f"- Developer gate: **{'PASS' if developer['passed'] else 'FAIL'}**",
        f"- Agent provider: **{agent['provider']}**",
        f"- Live API used: **{'yes' if agent['live_api_used'] else 'no'}**",
        f"- Recorded failure cases: **{len(report['failure_registry'])}**",
        "",
        "## Held-out comparison",
        "",
        "| Metric | Greedy baseline | MealCraft planner | Delta |",
        "|---|---:|---:|---:|",
        (
            "| Scenario expectation rate | "
            f"{baseline['metrics']['scenario_expectation_rate']} | "
            f"{planner['metrics']['scenario_expectation_rate']} | "
            f"{comparison['expectation_rate_delta']} |"
        ),
        (
            "| Mean distinct recipes | "
            f"{baseline['metrics']['mean_distinct_recipes']} | "
            f"{planner['metrics']['mean_distinct_recipes']} | "
            f"{comparison['mean_distinct_recipes_delta']} |"
        ),
        (
            "| Consecutive repetitions | "
            f"{baseline['metrics']['consecutive_repetition_count']} | "
            f"{planner['metrics']['consecutive_repetition_count']} | "
            f"-{comparison['consecutive_repetition_reduction']} |"
        ),
        (
            "| Failure cases | "
            f"{baseline['metrics']['failure_case_count']} | "
            f"{planner['metrics']['failure_case_count']} | "
            f"-{comparison['failure_case_reduction']} |"
        ),
        "",
        "## Offline Agent benchmark",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in agent["metrics"].items())
    lines.extend(
        [
            "",
            "## Failure registry",
            "",
            "| # | Source | Case | Reasons |",
            "|---:|---|---|---|",
        ]
    )
    for index, item in enumerate(report["failure_registry"], start=1):
        lines.append(f"| {index} | {item['source']} | {item['id']} | {', '.join(item['failure_reasons'])} |")
    if not report["failure_registry"]:
        lines.append("| - | - | No failures recorded | - |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the offline-first MealCraft evaluation workbench.")
    parser.add_argument("--ingredients", type=Path, default=Path("data/ingredients/ingredients.json"))
    parser.add_argument("--recipes", type=Path, default=Path("data/recipes/recipes.json"))
    parser.add_argument("--developer", type=Path, default=Path("data/evaluation/dev/planning-v1.json"))
    parser.add_argument("--heldout", type=Path, default=Path("data/evaluation/heldout/planning-v1.json"))
    parser.add_argument("--agent-dataset", type=Path, default=Path("data/evaluation/agent/fixture-v1.json"))
    parser.add_argument("--fixtures", type=Path, default=Path("data/fixtures/fairprice-products.json"))
    parser.add_argument("--agent-provider", choices=("fixture", "openai"), default="fixture")
    parser.add_argument("--allow-live-api", action="store_true")
    parser.add_argument("--openai-model", default="gpt-5.4-mini")
    parser.add_argument("--json-report", type=Path, default=Path("docs/evaluation/workbench/latest.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("docs/evaluation/workbench/latest.md"))
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY") if args.agent_provider == "openai" and args.allow_live_api else None
    report = build_workbench(
        ingredient_path=args.ingredients,
        recipe_path=args.recipes,
        developer_path=args.developer,
        heldout_path=args.heldout,
        agent_path=args.agent_dataset,
        fixture_path=args.fixtures,
        agent_provider=args.agent_provider,
        allow_live_api=args.allow_live_api,
        api_key=api_key,
        model=args.openai_model,
    )
    write_workbench(report, args.json_report, args.markdown_report)
    print("MealCraft evaluation workbench complete")
    print(f"  developer gate: {'PASS' if report['developer_gate_passed'] else 'FAIL'}")
    print(f"  live API used: {report['api_evaluation']['live_api_used']}")
    print(f"  failure cases: {len(report['failure_registry'])}")


if __name__ == "__main__":
    main()
