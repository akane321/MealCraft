"""One execution matrix for the product, baselines, and canonical ablations.

The sealed-side caller owns episode loading and supplies the already-registered
condition runners.  This layer deliberately knows nothing about sealed packet
formats: it only enumerates every arm, executes it once, and preserves stable
condition labels in the returned manifest and report.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.evaluation.ablation_conditions import ABLATION_CONDITIONS, AblationCondition

ConditionKind = Literal["product", "baseline", "ablation"]
ConditionRunner = Callable[[], dict[str, Any]]

PRODUCT_CONDITION = "product/default"


@dataclass(frozen=True)
class EvaluationCondition:
    """One existing runner under its reproducible matrix identity."""

    label: str
    kind: ConditionKind
    run: ConditionRunner


def evaluation_conditions(
    *,
    product: ConditionRunner,
    baselines: Sequence[tuple[str, ConditionRunner]],
    ablations: Mapping[AblationCondition, ConditionRunner],
) -> tuple[EvaluationCondition, ...]:
    """Build the canonical matrix and reject partial or ambiguous runs."""

    missing = set(ABLATION_CONDITIONS) - ablations.keys()
    extra = ablations.keys() - set(ABLATION_CONDITIONS)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unknown: {', '.join(sorted(extra))}")
        raise ValueError(f"A unified run requires exactly the canonical ablations ({'; '.join(details)})")

    baseline_conditions = tuple(
        EvaluationCondition(label=f"baseline/{label}", kind="baseline", run=runner) for label, runner in baselines
    )
    conditions = (
        EvaluationCondition(PRODUCT_CONDITION, "product", product),
        *baseline_conditions,
        *(
            EvaluationCondition(label=f"ablation/{condition}", kind="ablation", run=ablations[condition])
            for condition in ABLATION_CONDITIONS
        ),
    )
    labels = [condition.label for condition in conditions]
    if any(not label.removeprefix("baseline/") for label in labels) or len(labels) != len(set(labels)):
        raise ValueError("Product, baseline, and ablation condition labels must be nonempty and unique")
    return conditions


def run_unified_evaluation(
    *,
    product: ConditionRunner,
    baselines: Sequence[tuple[str, ConditionRunner]],
    ablations: Mapping[AblationCondition, ConditionRunner],
) -> dict[str, Any]:
    """Execute every condition once, retaining later arms after a runner error."""

    conditions = evaluation_conditions(product=product, baselines=baselines, ablations=ablations)
    manifest = [{"label": item.label, "kind": item.kind} for item in conditions]
    results = []
    for condition in conditions:
        try:
            report = condition.run()
            if not isinstance(report, dict):
                raise TypeError("condition runner must return a report mapping")
            results.append({"label": condition.label, "kind": condition.kind, "status": "completed", "report": report})
        except Exception as error:
            results.append(
                {
                    "label": condition.label,
                    "kind": condition.kind,
                    "status": "failed",
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
            )
    return {
        "schema_version": "unified-evaluation-run-v1",
        "manifest": manifest,
        "results": results,
    }
