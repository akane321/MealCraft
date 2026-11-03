import pytest

from app.evaluation.ablation_conditions import ABLATION_CONDITIONS
from app.evaluation.unified_run import run_unified_evaluation


def runners(calls):
    def runner(label):
        def run():
            calls.append(label)
            return {"runner": label}

        return run

    return runner


def test_one_run_executes_product_baselines_and_all_six_canonical_ablations():
    calls = []
    runner = runners(calls)
    report = run_unified_evaluation(
        product=runner("product"),
        baselines=(("strong-rule", runner("strong-rule")), ("llm-only", runner("llm-only"))),
        ablations={condition: runner(condition) for condition in reversed(ABLATION_CONDITIONS)},
    )

    expected_labels = [
        "product/default",
        "baseline/strong-rule",
        "baseline/llm-only",
        *(f"ablation/{condition}" for condition in ABLATION_CONDITIONS),
    ]
    assert calls == ["product", "strong-rule", "llm-only", *ABLATION_CONDITIONS]
    assert [item["label"] for item in report["manifest"]] == expected_labels
    assert [item["label"] for item in report["results"]] == expected_labels
    assert all(item["status"] == "completed" for item in report["results"])


def test_a_failed_condition_is_labelled_and_does_not_skip_later_ablations():
    calls = []
    runner = runners(calls)

    def fail():
        calls.append("repair_off")
        raise RuntimeError("synthetic failure")

    ablations = {condition: runner(condition) for condition in ABLATION_CONDITIONS}
    ablations["repair_off"] = fail
    report = run_unified_evaluation(product=runner("product"), baselines=(), ablations=ablations)

    failed = next(item for item in report["results"] if item["label"] == "ablation/repair_off")
    assert failed["status"] == "failed"
    assert failed["error"] == {"type": "RuntimeError", "message": "synthetic failure"}
    assert calls[-1] == "local_improvement_off"


def test_partial_ablation_registry_cannot_start_a_unified_run():
    ablations = {condition: (lambda: {}) for condition in ABLATION_CONDITIONS[:-1]}
    with pytest.raises(ValueError, match="missing: local_improvement_off"):
        run_unified_evaluation(product=lambda: {}, baselines=(), ablations=ablations)


def test_condition_labels_must_be_unique():
    ablations = {condition: (lambda: {}) for condition in ABLATION_CONDITIONS}
    with pytest.raises(ValueError, match="nonempty and unique"):
        run_unified_evaluation(
            product=lambda: {}, baselines=(("same", lambda: {}), ("same", lambda: {})), ablations=ablations
        )
