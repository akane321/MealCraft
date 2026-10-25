from app.evaluation.baseline_comparison import Arm, run_comparison, select_episodes
from app.evaluation.baseline_mapping import CoverageResult, IngredientMapping
from app.evaluation.baseline_output import BaselineResponse
from app.evaluation.baseline_recomputation import BaselineRecomputation
from app.evaluation.baseline_verification import VerificationResult
from app.evaluation.pure_llm_baseline import EpisodeResult, GenerationResult, ModelUsage
from app.schemas.planning_v2 import PlanningNutrients


def episode(identifier="episode-1"):
    return {
        "episode_id": identifier,
        "scenario": {"household_profile": {"allergens": ["peanut"]}},
        "gold": {"class": "feasible", "applicable_hard_constraints": {"budget_sgd": 10}},
    }


def result(identifier="episode-1", *, coverage=1.0, system_id="test-arm"):
    response = BaselineResponse(episode_id=identifier, system_id=system_id, status="plan")
    mapping = IngredientMapping("rice", 100, "rice", "matched")
    recomputation = BaselineRecomputation(
        nutrition=PlanningNutrients(
            calories_kcal=100,
            protein_g=2,
            carbohydrate_g=20,
            fat_g=1,
            sodium_mg=1,
            sugar_g=0,
        ),
        nutrition_complete=True,
        nutrition_unknown_ingredients=(),
        allergens=(),
        allergens_complete=True,
        allergen_unknown_ingredients=(),
        pricing_status="complete",
        purchase_total_sgd=5,
        price_results=(),
    )
    return EpisodeResult(
        episode_id=identifier,
        system_id=system_id,
        valid_output=True,
        generation=GenerationResult(
            response=response,
            attempts=1,
            elapsed_seconds=2.5,
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost_usd=0.02),
            parse_errors=(),
        ),
        coverage=CoverageResult(100, 100 * coverage, coverage, (mapping,)),
        verification=VerificationResult(coverage, 0.9, coverage >= 0.9, 100 * (1 - coverage), 0, 0),
        recomputation=recomputation,
    )


def test_stochastic_arm_repeats_and_reports_shared_metrics(tmp_path):
    calls = []
    arm = Arm("test-arm", "stochastic", lambda item: calls.append(item) or result())

    report = run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path, repeats=3)

    assert len(calls) == 3
    assert len(report["runs"]) == 3
    summary = report["arms"]["test-arm"]
    assert summary["mapping_coverage_mean"] == 1
    assert summary["verifiable"] == 3
    assert summary["hard_constraint_success"] == 3
    assert summary["strict_success"] == 3
    assert summary["coverage_adjusted_success"] == 3
    assert summary["runtime_seconds_total"] == 7.5
    assert summary["token_usage"]["total_tokens"] == 45
    assert summary["api_model_cost_usd"] == 0.06
    assert len(list((tmp_path / "raw" / "test-arm").rglob("*.json"))) == 3


def test_deterministic_arm_runs_once_and_reuses_matching_raw_result(tmp_path):
    calls = []
    arm = Arm("test-arm", "deterministic", lambda item: calls.append(item) or result())

    first = run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path, repeats=5)
    second = run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path, repeats=5)

    assert len(first["runs"]) == 1
    assert len(calls) == 1
    assert second["runs"][0]["reused"] is True


def test_strict_fails_below_coverage_gate_but_adjusted_retains_hard_result(tmp_path):
    arm = Arm("test-arm", "stochastic", lambda item: result(coverage=0.8))

    report = run_comparison(episodes=[episode()], arms=[arm], output_dir=tmp_path)

    comparison = report["runs"][0]["comparison"]
    assert comparison["hard_constraint_success"] is True
    assert comparison["strict_success"] is False
    assert comparison["coverage_adjusted_success"] is True


def test_episode_selection_rejects_unknown_ids():
    import pytest

    with pytest.raises(ValueError, match="unknown evaluation episodes"):
        select_episodes([episode()], {"missing"})


def test_arm_failure_is_recorded_without_aborting_other_arms(tmp_path):
    def fail(_item):
        raise RuntimeError("deliberate test failure")

    report = run_comparison(
        episodes=[episode()],
        arms=[
            Arm("broken-arm", "deterministic", fail),
            Arm("healthy-arm", "deterministic", lambda _: result(system_id="healthy-arm")),
        ],
        output_dir=tmp_path,
    )

    assert (tmp_path / "comparison.json").is_file()
    assert len(report["runs"]) == 2
    failed, completed = report["runs"]
    assert failed["status"] == "failed"
    assert failed["error"]["type"] == "RuntimeError"
    assert failed["error"]["message"] == "deliberate test failure"
    assert completed["status"] == "completed"
    assert completed["comparison"]["strict_success"] is True
    assert completed["comparison"]["coverage_adjusted_success"] is True
    assert report["arms"]["broken-arm"]["failed_runs"] == 1
    assert report["arms"]["broken-arm"]["token_usage"]["total_tokens"] is None
    assert report["arms"]["broken-arm"]["api_model_cost_usd"] is None
    assert report["arms"]["healthy-arm"]["completed_runs"] == 1
    raw = tmp_path / failed["raw_result"]
    assert raw.is_file()
    assert '"status": "failed"' in raw.read_text(encoding="utf-8")
