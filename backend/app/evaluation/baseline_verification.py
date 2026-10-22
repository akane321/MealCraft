from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.baseline_mapping import CoverageResult

DEFAULT_COVERAGE_THRESHOLD = 0.90


@dataclass(frozen=True)
class VerificationResult:
    coverage: float
    threshold: float
    verifiable: bool
    unmatched_grams: float
    needs_review_count: int
    unmatched_count: int


def verify_coverage(
    result: CoverageResult,
    *,
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> VerificationResult:
    needs_review_count = sum(item.status == "needs_review" for item in result.mappings)

    unmatched_count = sum(item.status == "unmatched" for item in result.mappings)

    unmatched_grams = result.total_grams - result.matched_grams

    return VerificationResult(
        coverage=result.coverage,
        threshold=threshold,
        verifiable=result.coverage >= threshold,
        unmatched_grams=unmatched_grams,
        needs_review_count=needs_review_count,
        unmatched_count=unmatched_count,
    )
