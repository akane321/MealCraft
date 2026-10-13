"""The console's experiments (ADR-0047): what each evaluation runs, records and keeps for the evidence drawer."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.agent import model_client
from app.core.config import Settings
from app.core.paths import repository_root
from app.core.runtime_config import REGISTRY
from app.evaluation import runner
from app.evaluation.agent_benchmark import evaluate_agent
from app.models.platform import OperationRun
from app.planning import product_path
from app.planning.product_path import ProductPlanningEngine, ProductPlanningError
from app.services.ops_settings import (
    _case_differences,
    _case_report,
    _evaluate,
    experiment_comparison,
    experiment_detail,
    experiment_view,
)
from app.worker.planning_experiments import _gate_summary
from tests.test_operations_console_api import console  # noqa: F401 - the console API fixture

ROOT = repository_root()
CATALOG = {
    "ingredient_path": ROOT / "data/ingredients/ingredients.json",
    "recipe_path": ROOT / "data/recipes/recipes.json",
    "scenario_path": ROOT / "data/evaluation/dev/planning-v1.json",
    "fixture_path": ROOT / "data/fixtures/fairprice-products.json",
}


def _run(client, body: dict, key: str):
    return client.post("/api/ops/experiments", json=body, headers={"Idempotency-Key": key})


def test_the_product_planner_option_scores_the_planner_the_product_runs(monkeypatch) -> None:
    strategies = []

    class Watched(ProductPlanningEngine):
        def plan(self, constraints, *args, **kwargs):
            strategies.append(constraints.planner_strategy)
            return super().plan(constraints, *args, **kwargs)

    monkeypatch.setattr(runner, "ProductPlanningEngine", Watched)
    report = runner.evaluate(**CATALOG, system="product-planner")

    planned = [row for row in report["scenarios"] if row["actual_feasible"]]
    assert report["system"] == "product-planner"
    # Twice a week with candidates (the determinism check), each with the product's beam search.
    assert len(strategies) == 2 * len(planned) == 36
    assert set(strategies) == {"beam"}
    assert report["metrics"]["hard_constraint_violation_count"] == 0


def test_a_week_the_product_planner_refuses_is_scored_as_answered_infeasible(monkeypatch) -> None:
    def refuse(self, constraints, *args, **kwargs):
        raise ProductPlanningError("infeasible", "No week fits.", {})

    monkeypatch.setattr(ProductPlanningEngine, "plan", refuse)
    rows = {row["id"]: row for row in runner.evaluate(**CATALOG, system="product-planner")["scenarios"]}

    assert all(not row["actual_feasible"] and row["selected_slugs"] == [] for row in rows.values())
    assert rows["dev-001"]["failure_reasons"] == ["feasibility_mismatch"]
    assert rows["dev-019"]["failure_reasons"] == []  # expected infeasible, answered so


def test_developer_planning_records_only_what_it_reads_and_keeps_every_scenario(console) -> None:  # noqa: F811
    client, factory = console
    # A switch this evaluation never reads is refused, not recorded as a difference with no effect.
    assert _run(client, {"evaluation": "developer-planning", "overrides": {"beam_width": 1}}, "beam").status_code == 422
    # The v1 weekly selector the recorded reports name is not the product's planner, so it is not offered.
    old = {"evaluation": "developer-planning", "overrides": {"planner": "mealcraft-planner"}}
    assert _run(client, old, "v1").status_code == 422

    product = _run(client, {"evaluation": "developer-planning", "label": "product"}, "product").json()
    greedy = _run(
        client, {"evaluation": "developer-planning", "overrides": {"planner": "greedy-baseline"}}, "greedy"
    ).json()
    assert product["configuration"] == {"planner": "product-planner"}
    assert (product["metrics"]["failure_case_count"], greedy["metrics"]["failure_case_count"]) == (0, 18)

    detail = client.get(f"/api/ops/experiments/{product['id']}").json()
    assert detail["report"]["system"] == "product-planner"
    # The run says which planner the option ran, as the runner's names alone do not.
    assert detail["report"]["planner"].startswith("ProductPlanningEngine, beam search")
    assert len(detail["report"]["runs"]) == 20
    assert sum(item["scenario_count"] for item in detail["report"]["category_metrics"].values()) == 20
    # The inline runner records the file hash as "sha256"; it counts. A semantic digest it never made does not.
    assert "dataset.file_sha256" not in detail["reproducibility"]["missing"]
    assert "dataset.semantic_sha256" in detail["reproducibility"]["missing"]

    comparison = client.get(f"/api/ops/experiments/compare?ids={product['id']},{greedy['id']}").json()
    changes = comparison["case_differences"]
    assert len(changes) == 18
    assert changes[0] == {
        "case_id": "dev-001",
        "condition": "",
        "a_status": "passed",
        "b_status": "failed",
        "failures_gained": ["consecutive_recipe_repetition"],
        "failures_lost": [],
    }

    # A run stored before reports were kept has nothing to compare: not "no case changed".
    with factory() as database:
        row = database.get(OperationRun, greedy["id"])
        data = {key: value for key, value in row.artifact_references[0]["data"].items() if key != "report"}
        row.artifact_references = [{"kind": "experiment", "data": data}]
        database.commit()
    comparison = client.get(f"/api/ops/experiments/compare?ids={product['id']},{greedy['id']}").json()
    assert comparison["case_differences"] is None


def test_the_assistant_benchmark_keeps_each_message_and_category(console) -> None:  # noqa: F811
    client, _ = console
    agent = _run(client, {"evaluation": "agent-benchmark"}, "agent").json()
    assert agent["configuration"] == {"agent_parser_provider": "fixture"}

    report = client.get(f"/api/ops/experiments/{agent['id']}").json()["report"]
    assert report["provider"] == "fixture"
    assert len(report["runs"]) == 24
    case = report["runs"][0]
    assert case["message"] and case["status"] == "passed" and case["failures"] == []
    assert {"expected_extraction", "actual_extraction", "expected_missing_fields", "category"} <= set(case)
    assert sum(item["case_count"] for item in report["category_metrics"].values()) == 24


def test_the_assistant_benchmark_records_its_own_model_calls_not_the_process_count(monkeypatch) -> None:
    def sends_three_requests(**kwargs):
        for _ in range(3):
            model_client._count(None)
        return evaluate_agent(**kwargs)

    monkeypatch.setattr("app.evaluation.agent_benchmark.evaluate_agent", sends_three_requests)
    before = model_client.unrecorded_requests()

    report = _evaluate("agent-benchmark", {"agent_parser_provider": "fixture"}, Settings())[3]

    assert report["model_calls"] == 3
    assert model_client.unrecorded_requests() == before


def test_a_failing_message_is_listed_and_compared_by_its_failure_codes() -> None:
    passing = evaluate_agent(dataset_path=ROOT / "data/evaluation/agent/fixture-v1.json")
    failing = {**passing, "cases": [{**passing["cases"][0], "failure_reasons": ["extraction_mismatch"]}]}

    row = _case_report(failing, failing["cases"])["runs"][0]
    assert (row["status"], row["failures"], row["message"]) == (
        "failed",
        [{"code": "extraction_mismatch"}],
        passing["cases"][0]["message"],
    )
    assert _case_differences(_case_report(passing, passing["cases"][:1]), _case_report(failing, failing["cases"])) == [
        {
            "case_id": passing["cases"][0]["id"],
            "condition": "",
            "a_status": "passed",
            "b_status": "failed",
            "failures_gained": ["extraction_mismatch"],
            "failures_lost": [],
        }
    ]


def test_the_list_and_the_drawer_give_one_reproducibility_verdict() -> None:
    now = datetime.now(UTC)
    conditions = {
        "dataset": {"path": "data/fixtures/x.json", "file_sha256": "f" * 64, "semantic_sha256": "s" * 64},
        "runner": "planning-component-ablation-dev-v1",
        "code_source": {"sha256": "c" * 64},
        "parameter_digest": "p" * 64,
        "seed": None,
        "repeats": 1,
        "product_snapshot_sha256": "n" * 64,
        "duration_seconds": 1.0,
        "paid_model": {"used": False, "budget_usd": 0, "usage_usd": 0},
        "conditions_complete": True,  # the worker's own flag: its fields are written
        "citation_scope": "developer_diagnostic_only",
    }
    data = {"evaluation": "planning-components", "configuration": {}, "metrics": {}, "passed": None}
    row = OperationRun(
        id=1,
        run_type="planning_experiment",
        status="succeeded",
        code_commit=None,
        created_at=now,
        started_at=now,
        finished_at=now,
        artifact_references=[{"kind": "planning_experiment", "data": {**data, "conditions": conditions}}],
    )

    assert experiment_view(row).conditions["conditions_complete"] is False
    detail = experiment_detail(row)
    assert (detail.reproducibility.complete, detail.reproducibility.missing) == (False, ["code_commit"])
    assert detail.conditions["conditions_complete"] is False

    row.code_commit = "a" * 40
    assert experiment_view(row).conditions["conditions_complete"] is True
    assert experiment_detail(row).reproducibility.complete is True


def test_the_dataset_digest_row_compares_the_file_hash_when_a_run_has_no_semantic_digest() -> None:
    def detail(row_id: int, dataset: dict):
        now = datetime.now(UTC)
        data = {"evaluation": "agent-benchmark", "configuration": {}, "metrics": {}, "conditions": {"dataset": dataset}}
        return experiment_detail(
            OperationRun(
                id=row_id,
                run_type="experiment",
                status="succeeded",
                created_at=now,
                started_at=now,
                finished_at=now,
                artifact_references=[{"kind": "experiment", "data": data}],
            )
        )

    def digest_row(a: dict, b: dict):
        comparison = experiment_comparison(detail(1, a), detail(2, b))
        rows = [row.model_dump(exclude={"delta"}) for row in comparison.evidence]
        return next(row for row in rows if row["key"].startswith("dataset_")), comparison

    both = {"sha256": "f" * 64}
    row, comparison = digest_row(both, both)
    assert row == {"key": "dataset_file_digest", "a": "f" * 64, "b": "f" * 64, "matches": True}
    assert comparison.compatible is False  # the runs still lack the rest of the recorded conditions
    row, _ = digest_row(both, {"file_sha256": "0" * 64})
    assert (row["key"], row["matches"]) == ("dataset_file_digest", False)
    # One run's semantic digest is no use against a run that recorded none.
    row, _ = digest_row({**both, "semantic_sha256": "s" * 64}, both)
    assert (row["key"], row["matches"]) == ("dataset_file_digest", True)
    row, _ = digest_row({**both, "semantic_sha256": "s" * 64}, {**both, "semantic_sha256": "s" * 64})
    assert row == {"key": "dataset_digest", "a": "s" * 64, "b": "s" * 64, "matches": True}
    row, _ = digest_row({}, {})
    assert (row["a"], row["b"], row["matches"]) == (None, None, False)


def test_a_gate_case_with_no_draft_is_not_an_unchecked_invalid_draft() -> None:
    def case(audit):
        return {
            "candidate_checks": [],
            "conditions": {"final_gate_on": {"candidate_index": None}, "final_gate_off": {"audit": audit}},
        }

    report = {
        "runs": [case({"status": "passed"}), case({"status": "failed"}), case({"status": "indeterminate"}), case(None)]
    }
    metrics, _ = _gate_summary(report, 4)

    assert (metrics["unchecked_invalid_count"], metrics["unchecked_no_candidate_count"]) == (2, 1)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_a_number_switch_refuses_a_value_that_is_not_finite(value: float) -> None:
    with pytest.raises(ValueError, match="Beam width must be between 1 and 512"):
        REGISTRY["beam_width"].check(value)


def test_an_overflowing_number_is_a_422_not_a_500(console) -> None:  # noqa: F811
    client, _ = console
    for raw in ('{"value": 1e999}', '{"value": -1e999}', '{"value": NaN}', '{"value": 1' + "0" * 400 + "}"):
        response = client.put("/api/ops/config/beam_width", content=raw, headers={"Content-Type": "application/json"})
        assert response.status_code == 422, raw


def test_the_meal_options_default_is_what_the_product_planner_keeps() -> None:
    # The module's own file, so the test reads it in a checkout and in the backend container alike.
    source = Path(product_path.__file__).read_text(encoding="utf-8")
    default = REGISTRY["meal_options_per_slot"].default(Settings(environment="test", database_url="sqlite://"))

    # The planner's literal and the console's default are kept in step until the planner reads the key.
    assert re.findall(r"meal_options_per_slot=(\d+)", source) == [str(default)]
