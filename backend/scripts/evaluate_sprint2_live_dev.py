"""Bounded live measurement on the visible developer set; never reads held-out evaluation data."""

import json
import statistics
import time
from datetime import UTC, datetime

from app.agent import model_client
from app.agent.parser import OpenAIConstraintParser
from app.core.config import get_settings
from app.core.paths import repository_root
from app.orchestration.model_pricing import CHAT_RATES
from app.orchestration.scope_classifier import OpenAIScopeClassifier
from app.orchestration.tool_scheduler import ModelToolScheduler
from app.schemas.agent import AgentConstraintState

MAX_BUDGET_USD = 5.0


class EvaluationBudget:
    """Track measured spend and prevent starting another paid request at the budget ceiling."""

    def __init__(self, limit_usd: float = MAX_BUDGET_USD) -> None:
        if limit_usd <= 0:
            raise ValueError("budget limit must be positive")
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    @property
    def can_start_request(self) -> bool:
        return self.spent_usd < self.limit_usd

    def record(self, cost: float | None) -> None:
        if cost is None:
            raise ValueError("cannot continue a paid evaluation with unknown model pricing")
        self.spent_usd += cost


def cost_usd(tally, model: str) -> float | None:
    rates = CHAT_RATES.get(model)
    if rates is None:
        return None
    input_rate, cached_rate, output_rate = rates
    cached = min(tally.cached_input_tokens, tally.input_tokens)
    value = (
        (tally.input_tokens - cached) * input_rate + cached * cached_rate + tally.output_tokens * output_rate
    ) / 1_000_000
    return float(value)


def measured(classifier, text: str, model: str):
    with model_client.counting():
        started = time.perf_counter()
        decision = classifier.classify(text)
        elapsed = time.perf_counter() - started
        tally = model_client.take()
    return decision, tally, elapsed, cost_usd(tally, model)


def main() -> None:
    settings = get_settings()
    if settings.openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY is not configured")
    if settings.openai_model not in CHAT_RATES:
        raise SystemExit(f"No published cost rate is configured for model {settings.openai_model!r}")
    root = repository_root()
    dataset_path = root / "data/evaluation/agent-orchestration/scope-developer-v2.json"
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    api_key = settings.openai_api_key.get_secret_value()
    classifier = OpenAIScopeClassifier(
        api_key=api_key,
        model=settings.openai_model,
        tool_scheduler=ModelToolScheduler(api_key=api_key, model=settings.openai_model, max_steps=2),
    )
    results = []
    errors = 0
    partial_reason = None
    budget = EvaluationBudget()
    for case in cases:
        if not budget.can_start_request:
            partial_reason = "budget_limit_reached"
            break
        decision, tally, elapsed, cost = measured(classifier, case["message"], settings.openai_model)
        budget.record(cost)
        fallback = tally.fell_back
        errors += int(fallback)
        results.append(
            {
                "id": case["id"],
                "language": case["language"],
                "category": case["category"],
                "expected": case["expected_class"],
                "actual": decision.scope_class.value,
                "correct": decision.scope_class.value == case["expected_class"],
                "mutation_expected": case["expected_state_mutation"],
                "mutation_actual": decision.should_mutate_state,
                "tool_expected": case["expected_tool_call"],
                "tool_actual": decision.should_call_tools,
                "latency_seconds": round(elapsed, 4),
                "requests": tally.requests,
                "input_tokens": tally.input_tokens,
                "cached_input_tokens": tally.cached_input_tokens,
                "output_tokens": tally.output_tokens,
                "estimated_cost_usd": cost,
                "fallback": fallback,
            }
        )
        if fallback:
            partial_reason = "model_fallback_or_api_unavailable"
            break

    per_language = {}
    for language in sorted({item["language"] for item in results}):
        group = [item for item in results if item["language"] == language]
        per_language[language] = {
            "cases": len(group),
            "accuracy": sum(item["correct"] for item in group) / len(group),
            "false_accepts": sum(not x["mutation_expected"] and x["mutation_actual"] for x in group),
            "false_rejects": sum(x["mutation_expected"] and not x["mutation_actual"] for x in group),
        }
    stability_cases = []
    selected = [
        next(item for item in cases if item["category"] == "planning_constraints" and item["language"] == "en"),
        next(item for item in cases if item["category"] == "planning_constraints" and item["language"] == "zh"),
        next(item for item in cases if item["category"] == "food_questions" and item["language"] == "zh"),
        next(item for item in cases if item["category"] == "food_questions" and item["language"] == "mixed"),
        next(
            item
            for item in cases
            if item["category"] == "mixed_supported_and_unsupported" and item["language"] == "mixed"
        ),
    ]
    for case in selected if partial_reason is None else []:
        repeated = []
        for _ in range(5):
            if not budget.can_start_request:
                partial_reason = "budget_limit_reached"
                break
            sample = measured(classifier, case["message"], settings.openai_model)
            repeated.append(sample)
            budget.record(sample[3])
            if sample[1].fell_back:
                errors += 1
                partial_reason = "model_fallback_or_api_unavailable_during_stability"
                break
        labels = [item[0].scope_class.value for item in repeated]
        stability_cases.append(
            {
                "id": case["id"],
                "runs": len(labels),
                "labels": labels,
                "consistent": len(set(labels)) == 1 and not any(item[1].fell_back for item in repeated),
                "latency_seconds": [round(item[2], 4) for item in repeated],
                "estimated_cost_usd": [item[3] for item in repeated],
            }
        )
        if partial_reason is not None:
            break

    planning_cases = [item for item in cases if item["category"] == "planning_constraints"][:10]
    parser = OpenAIConstraintParser(api_key=settings.openai_api_key.get_secret_value(), model=settings.openai_model)
    plan_turns = []
    for case in planning_cases if partial_reason is None else []:
        if not budget.can_start_request:
            partial_reason = "budget_limit_reached"
            break
        decision, scope_tally, scope_latency, scope_cost = measured(classifier, case["message"], settings.openai_model)
        budget.record(scope_cost)
        if scope_tally.fell_back:
            errors += 1
            partial_reason = "model_fallback_or_api_unavailable_during_plan_sample"
            break
        if not budget.can_start_request:
            partial_reason = "budget_limit_reached"
            break
        try:
            with model_client.counting():
                parser_started = time.perf_counter()
                parser.parse(
                    case["message"],
                    current=AgentConstraintState(),
                    acknowledged_unknowns=[],
                    history=[],
                )
                parser_latency = time.perf_counter() - parser_started
                parser_tally = model_client.take()
        except Exception as error:  # report the partial developer sample without retrying after quota/network errors
            partial_reason = f"parser_api_unavailable:{type(error).__name__}"
            break
        parser_cost = cost_usd(parser_tally, settings.openai_model)
        budget.record(parser_cost)
        plan_turns.append(
            {
                "id": case["id"],
                "scope_requests": scope_tally.requests,
                "parser_requests": parser_tally.requests,
                "input_tokens": scope_tally.input_tokens + parser_tally.input_tokens,
                "output_tokens": scope_tally.output_tokens + parser_tally.output_tokens,
                "latency_seconds": round(scope_latency + parser_latency, 4),
                "estimated_cost_usd": (
                    scope_cost + parser_cost if scope_cost is not None and parser_cost is not None else None
                ),
                "scope": decision.scope_class.value,
            }
        )

    known_costs = [item["estimated_cost_usd"] for item in results if item["estimated_cost_usd"] is not None]
    plan_costs = [item["estimated_cost_usd"] for item in plan_turns if item["estimated_cost_usd"] is not None]
    report = {
        "report_version": "sprint2-live-dev-v1",
        "evaluation_role": "developer_set_only",
        "partial": partial_reason is not None,
        "partial_reason": partial_reason,
        "budget_limit_usd": budget.limit_usd,
        "estimated_total_cost_usd": round(budget.spent_usd, 6),
        "created_at": datetime.now(UTC).isoformat(),
        "model": settings.openai_model,
        "pricing_checked_at": "2026-10-21",
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        "dataset": {"path": "data/evaluation/agent-orchestration/scope-developer-v2.json", "count": len(cases)},
        "metrics": {
            "cases_completed": len(results),
            "accuracy": sum(item["correct"] for item in results) / len(results) if results else None,
            "false_accepts": sum(not x["mutation_expected"] and x["mutation_actual"] for x in results),
            "false_rejects": sum(x["mutation_expected"] and not x["mutation_actual"] for x in results),
            "tool_policy_accuracy": (
                sum(x["tool_expected"] == x["tool_actual"] for x in results) / len(results) if results else None
            ),
            "fallback_cases": errors,
            "mean_latency_seconds": statistics.mean(item["latency_seconds"] for item in results) if results else None,
            "per_language": per_language,
            "stability_consistent_fraction": (
                sum(item["consistent"] for item in stability_cases) / len(stability_cases) if stability_cases else None
            ),
            "stability_runs": sum(item["runs"] for item in stability_cases),
            "stability_cases_consistent": sum(item["consistent"] for item in stability_cases),
            "mean_scope_call_cost_usd": statistics.mean(known_costs) if known_costs else None,
            "estimated_cost_10_plan_understanding_turns_usd": sum(plan_costs) if plan_costs else None,
            "mean_estimated_cost_per_plan_understanding_turn_usd": statistics.mean(plan_costs) if plan_costs else None,
        },
        "stability_cases": stability_cases,
        "plan_turn_samples": plan_turns,
        "cases": results,
    }
    output = root / "reports/sprint2-llm/scope-live-developer-2026-10-21.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": output.as_posix(), "metrics": report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
