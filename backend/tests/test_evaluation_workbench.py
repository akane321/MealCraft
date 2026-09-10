import pytest

from app.agent.parser import AgentConfigurationError
from app.core.paths import repository_root
from app.evaluation.agent_benchmark import evaluate_agent
from app.evaluation.orchestration_benchmark import evaluate_grounding, evaluate_scope_policy
from app.evaluation.runner import evaluate

ROOT = repository_root()
INGREDIENTS = ROOT / "data/ingredients/ingredients.json"
RECIPES = ROOT / "data/recipes/recipes.json"
HELDOUT = ROOT / "data/evaluation/heldout/planning-v1.json"
AGENT_CASES = ROOT / "data/evaluation/agent/fixture-v1.json"
FIXTURES = ROOT / "data/fixtures/fairprice-products.json"
SCOPE_CASES = ROOT / "data/evaluation/agent-orchestration/scope-developer-v1.json"
GROUNDING_CASES = ROOT / "data/evaluation/agent-orchestration/grounding-developer-v1.json"


def test_heldout_comparison_keeps_baseline_and_planner_on_same_dataset() -> None:
    baseline = evaluate(
        ingredient_path=INGREDIENTS,
        recipe_path=RECIPES,
        scenario_path=HELDOUT,
        fixture_path=FIXTURES,
        system="greedy-baseline",
        enforce_gates=False,
    )
    planner = evaluate(
        ingredient_path=INGREDIENTS,
        recipe_path=RECIPES,
        scenario_path=HELDOUT,
        fixture_path=FIXTURES,
        system="mealcraft-planner",
        enforce_gates=False,
    )

    assert baseline["dataset"]["sha256"] == planner["dataset"]["sha256"]
    assert baseline["metrics"]["scenario_count"] == 40
    assert baseline["metrics"]["consecutive_repetition_count"] > 0
    assert planner["metrics"]["consecutive_repetition_count"] < baseline["metrics"]["consecutive_repetition_count"]
    assert planner["metrics"]["hard_constraint_violation_count"] == 0


def test_strong_rule_only_baseline_is_deterministic_and_not_a_repeat_strawman() -> None:
    report = evaluate(
        ingredient_path=INGREDIENTS,
        recipe_path=RECIPES,
        scenario_path=HELDOUT,
        fixture_path=FIXTURES,
        system="rule-only-baseline",
        enforce_gates=False,
    )

    assert report["metrics"]["scenario_count"] == 40
    assert report["metrics"]["determinism_rate"] == 1.0
    assert report["metrics"]["hard_constraint_violation_count"] == 0
    assert report["metrics"]["consecutive_repetition_count"] == 0
    assert report["metrics"]["mean_distinct_recipes"] > 1.0


def test_fixture_agent_benchmark_is_offline_and_keeps_failures_visible() -> None:
    report = evaluate_agent(dataset_path=AGENT_CASES)

    assert report["provider"] == "fixture"
    assert report["live_api_used"] is False
    assert report["metrics"]["case_count"] == 24
    assert report["metrics"]["failure_case_count"] >= 8


def test_openai_benchmark_requires_explicit_live_api_opt_in() -> None:
    with pytest.raises(AgentConfigurationError, match="disabled by default"):
        evaluate_agent(dataset_path=AGENT_CASES, provider="openai")


def test_scope_benchmark_is_a_separate_developer_set() -> None:
    report = evaluate_scope_policy(dataset_path=SCOPE_CASES)

    assert report["evaluation_role"] == "developer_set"
    assert report["live_api_used"] is False
    assert report["metrics"]["state_contamination_count"] == 0


def test_grounding_benchmark_is_offline_and_keeps_denominators() -> None:
    report = evaluate_grounding(dataset_path=GROUNDING_CASES)

    assert report["live_api_used"] is False
    assert report["metrics"]["supported_case_count"] == 4
    assert report["metrics"]["unsupported_case_count"] == 8
    assert report["metrics"]["unsupported_claim_escape_rate"] == 0.0
