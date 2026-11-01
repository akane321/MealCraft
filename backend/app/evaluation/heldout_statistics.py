"""Deterministic paired statistics over sealed held-out outcome records.

This module analyses already-scored ``CaseOutcome`` records.  It does not load
episodes, gold labels, system outputs, or alter scoring.  Opaque case references
are used for pairing and are never emitted.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from statistics import fmean, median, pstdev
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.evaluation.heldout_report import CaseOutcome, ExpectedManifest, _check_manifest, _validate

DEFAULT_BOOTSTRAP_SAMPLES = 10_000
DEFAULT_SEED = 365
_Z_95 = 1.959963984540054


class MetricSpec(BaseModel):
    """A predeclared metric already present in every applicable outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    kind: Literal["binary", "continuous"]
    higher_is_better: bool = True

    @field_validator("name")
    @classmethod
    def _reserved_success(cls, value: str) -> str:
        if value == "success":
            raise ValueError("success is built in; do not redeclare it")
        return value


def _round(value: float) -> float:
    value = round(value, 6)
    return 0.0 if value == 0 else value


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _derived_seed(seed: int, *parts: str) -> int:
    digest = hashlib.sha256("\x1f".join((str(seed), *parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    samples: int,
    seed: int,
) -> list[float] | None:
    if not values:
        return None
    generator = random.Random(seed)
    size = len(values)
    estimates = [statistic([values[generator.randrange(size)] for _ in range(size)]) for _ in range(samples)]
    return [_round(_quantile(estimates, 0.025)), _round(_quantile(estimates, 0.975))]


def wilson_interval(successes: int, total: int) -> list[float] | None:
    """Return a two-sided 95% Wilson score interval for one binary rate."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("Wilson counts require 0 <= successes <= total")
    if total == 0:
        return None
    rate = successes / total
    denominator = 1 + _Z_95**2 / total
    centre = (rate + _Z_95**2 / (2 * total)) / denominator
    radius = _Z_95 * math.sqrt(rate * (1 - rate) / total + _Z_95**2 / (4 * total**2)) / denominator
    return [_round(centre - radius), _round(centre + radius)]


def mcnemar_exact(product_only: int, baseline_only: int) -> dict:
    """Two-sided exact McNemar test, conditioning on discordant pairs."""
    if product_only < 0 or baseline_only < 0:
        raise ValueError("McNemar counts cannot be negative")
    discordant = product_only + baseline_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(min(product_only, baseline_only) + 1)) / 2**discordant
        p_value = min(1.0, 2 * tail)
    return {
        "product_only_success_n": product_only,
        "baseline_only_success_n": baseline_only,
        "discordant_n": discordant,
        "exact_two_sided_p_value": _round(p_value),
    }


def _metric_value(row: CaseOutcome, metric: MetricSpec | None) -> float | None:
    if metric is None:
        return float(row.status == "success")
    values = row.binary_metrics if metric.kind == "binary" else row.continuous_metrics
    value = values.get(metric.name)
    if value is None:
        if metric.kind == "binary" and row.status in {"timeout", "error", "missing"}:
            # No output cannot pass a declared binary endpoint, irrespective of
            # whether that endpoint is expressed as positive or negative.
            return 0.0 if metric.higher_is_better else 1.0
        return None
    return float(value)


def _episode_values(rows: Sequence[CaseOutcome], metric: MetricSpec | None) -> dict[str, float]:
    by_case: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.voided:
            continue
        value = _metric_value(row, metric)
        if value is not None:
            by_case[row.case_ref].append(value)
    return {case_ref: fmean(values) for case_ref, values in by_case.items()}


def _run_summary(rows: Sequence[CaseOutcome], metric: MetricSpec | None) -> dict:
    by_run: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        if row.voided:
            continue
        value = _metric_value(row, metric)
        if value is not None:
            by_run[row.run].append(value)
    per_run = [_round(fmean(by_run[run])) if by_run[run] else None for run in sorted({r.run for r in rows})]
    known = [value for value in per_run if value is not None]
    return {
        "per_run": per_run,
        "mean": _round(fmean(known)) if known else None,
        "standard_deviation": _round(pstdev(known)) if known else None,
    }


def _binary_comparison(
    product: dict[str, float],
    baseline: dict[str, float],
    *,
    higher_is_better: bool,
    samples: int,
    seed: int,
) -> dict:
    case_refs = sorted(product.keys() & baseline.keys())
    product_binary = [product[case_ref] >= 0.5 for case_ref in case_refs]
    baseline_binary = [baseline[case_ref] >= 0.5 for case_ref in case_refs]
    if not higher_is_better:
        product_binary = [not value for value in product_binary]
        baseline_binary = [not value for value in baseline_binary]
    differences = [float(p) - float(b) for p, b in zip(product_binary, baseline_binary, strict=True)]
    product_successes = sum(product_binary)
    baseline_successes = sum(baseline_binary)
    return {
        "paired_n": len(case_refs),
        "product_unpaired_n": len(product) - len(case_refs),
        "baseline_unpaired_n": len(baseline) - len(case_refs),
        "episode_aggregation": "mean across runs, then success when the mean is at least 0.5",
        "product_rate": _round(product_successes / len(case_refs)) if case_refs else None,
        "product_wilson_95_ci": wilson_interval(product_successes, len(case_refs)),
        "baseline_rate": _round(baseline_successes / len(case_refs)) if case_refs else None,
        "baseline_wilson_95_ci": wilson_interval(baseline_successes, len(case_refs)),
        "paired_rate_difference": _round(fmean(differences)) if differences else None,
        "paired_bootstrap_95_ci": _bootstrap_ci(differences, fmean, samples=samples, seed=seed),
        "mcnemar": mcnemar_exact(
            sum(p and not b for p, b in zip(product_binary, baseline_binary, strict=True)),
            sum(b and not p for p, b in zip(product_binary, baseline_binary, strict=True)),
        ),
    }


def _continuous_comparison(
    product: dict[str, float],
    baseline: dict[str, float],
    *,
    higher_is_better: bool,
    samples: int,
    seed: int,
) -> dict:
    case_refs = sorted(product.keys() & baseline.keys())
    direction = 1 if higher_is_better else -1
    differences = [direction * (product[case_ref] - baseline[case_ref]) for case_ref in case_refs]
    return {
        "paired_n": len(case_refs),
        "product_unpaired_n": len(product) - len(case_refs),
        "baseline_unpaired_n": len(baseline) - len(case_refs),
        "episode_aggregation": "mean across runs before pairing",
        "mean_difference": _round(fmean(differences)) if differences else None,
        "mean_paired_bootstrap_95_ci": _bootstrap_ci(differences, fmean, samples=samples, seed=seed),
        "median_difference": _round(median(differences)) if differences else None,
        "median_paired_bootstrap_95_ci": _bootstrap_ci(differences, median, samples=samples, seed=seed + 1),
        "difference_iqr": (
            [_round(_quantile(differences, 0.25)), _round(_quantile(differences, 0.75))] if differences else None
        ),
    }


def _minimum_detectable_difference(episodes: int) -> float | None:
    # Issue #365's preregistered planning approximation: about 10 points needs 60 episodes.
    return _round(math.sqrt(0.6 / episodes)) if episodes else None


def _comparison(
    rows: Sequence[CaseOutcome],
    product_id: str,
    baseline_id: str,
    metrics: Sequence[MetricSpec],
    *,
    samples: int,
    seed: int,
) -> dict:
    product_rows = [row for row in rows if row.system_id == product_id]
    baseline_rows = [row for row in rows if row.system_id == baseline_id]
    definitions: list[tuple[str, MetricSpec | None]] = [("success", None), *[(m.name, m) for m in metrics]]
    output = {}
    for name, metric in definitions:
        product = _episode_values(product_rows, metric)
        baseline = _episode_values(baseline_rows, metric)
        metric_seed = _derived_seed(seed, baseline_id, name)
        kind = "binary" if metric is None else metric.kind
        result = (
            _binary_comparison(
                product,
                baseline,
                higher_is_better=True if metric is None else metric.higher_is_better,
                samples=samples,
                seed=metric_seed,
            )
            if kind == "binary"
            else _continuous_comparison(
                product,
                baseline,
                higher_is_better=metric.higher_is_better,
                samples=samples,
                seed=metric_seed,
            )
        )
        result["product_run_summary"] = _run_summary(product_rows, metric)
        result["baseline_run_summary"] = _run_summary(baseline_rows, metric)
        result["higher_is_better"] = True if metric is None else metric.higher_is_better
        output[name] = result
    paired_n = output["success"]["paired_n"]
    return {
        "baseline_system_id": baseline_id,
        "power_note": {
            "paired_episodes": paired_n,
            "approximate_minimum_detectable_absolute_difference": _minimum_detectable_difference(paired_n),
            "method": "planning approximation sqrt(0.6 / n); about 0.10 requires at least 60 paired episodes",
            "limitation": "descriptive planning guidance, not a post-hoc power calculation from observed effects",
        },
        "metrics": output,
    }


def compare(
    records: Iterable[CaseOutcome],
    *,
    product_system_id: str,
    metrics: Sequence[MetricSpec] = (),
    seed: int = DEFAULT_SEED,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    include_groups: bool = False,
    expected: ExpectedManifest | None = None,
) -> dict:
    """Compare one product with every other system using episode-level pairs."""
    rows = list(records)
    if not rows:
        raise ValueError("no outcomes")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    _validate(rows)
    if expected is not None:
        _check_manifest(rows, expected)
    systems = sorted({row.system_id for row in rows})
    if product_system_id not in systems:
        raise ValueError("product system is absent")
    baselines = [system for system in systems if system != product_system_id]
    if not baselines:
        raise ValueError("at least one baseline is required")

    comparisons = {
        baseline: _comparison(rows, product_system_id, baseline, metrics, samples=bootstrap_samples, seed=seed)
        for baseline in baselines
    }
    grouped = None
    if include_groups:
        selectors = {
            "by_category": lambda row: row.category,
            "by_language": lambda row: row.language,
            "by_source": lambda row: row.source,
            "cells": lambda row: f"{row.category}|{row.language}|{row.source}",
        }
        grouped = {}
        for dimension, selector in selectors.items():
            grouped[dimension] = {}
            for label in sorted({selector(row) for row in rows}):
                subset = [row for row in rows if selector(row) == label]
                grouped[dimension][label] = {
                    baseline: _comparison(
                        subset,
                        product_system_id,
                        baseline,
                        metrics,
                        samples=bootstrap_samples,
                        seed=_derived_seed(seed, dimension, label),
                    )
                    for baseline in baselines
                }

    return {
        "method": "paired episode-level comparison",
        "product_system_id": product_system_id,
        "seed": seed,
        "bootstrap_samples": bootstrap_samples,
        "grouped_reporting_enabled": include_groups,
        "note": (
            "Voided episodes are excluded. Timeout, error, failure and missing statuses are failures. "
            "Metric values are consumed after scoring; this analysis does not rescore outputs."
        ),
        "comparisons": comparisons,
        **({"groups": grouped} if grouped is not None else {}),
    }
