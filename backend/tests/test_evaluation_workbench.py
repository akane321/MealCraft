from pathlib import Path

import pytest

from app.agent.parser import AgentConfigurationError
from app.evaluation.agent_benchmark import evaluate_agent
from app.evaluation.runner import evaluate

ROOT = Path("/app") if Path("/app/data").exists() else Path(__file__).resolve().parents[2]
INGREDIENTS = ROOT / "data/ingredients/ingredients.json"
RECIPES = ROOT / "data/recipes/recipes.json"
HELDOUT = ROOT / "data/evaluation/heldout/planning-v1.json"
AGENT_CASES = ROOT / "data/evaluation/agent/fixture-v1.json"
FIXTURES = ROOT / "data/fixtures/fairprice-products.json"


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


def test_fixture_agent_benchmark_is_offline_and_keeps_failures_visible() -> None:
    report = evaluate_agent(dataset_path=AGENT_CASES)

    assert report["provider"] == "fixture"
    assert report["live_api_used"] is False
    assert report["metrics"]["case_count"] == 24
    assert report["metrics"]["failure_case_count"] >= 8


def test_openai_benchmark_requires_explicit_live_api_opt_in() -> None:
    with pytest.raises(AgentConfigurationError, match="disabled by default"):
        evaluate_agent(dataset_path=AGENT_CASES, provider="openai")
