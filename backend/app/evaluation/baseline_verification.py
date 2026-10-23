"""Which dishes of a baseline plan can be verified, and the coverage figures to report (ADR-0074 section 2).

A dish is verifiable when at least 90% of its grams map to catalog ingredients. Two bases follow from that:

- strict: a plan with any unverifiable dish fails (`all_dishes_verifiable` is False);
- coverage-adjusted: only the verifiable dishes are scored (`baseline_validation`).

Coverage itself is a reported metric: the plan's gram coverage, each dish's coverage and the verifiable-dish
share. Every flagged or unmatched line goes to the review list.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping, PlanCoverage

DEFAULT_COVERAGE_THRESHOLD = 0.90


@dataclass(frozen=True)
class DishVerification:
    slot_id: str
    name: str
    coverage: float
    verifiable: bool


@dataclass(frozen=True)
class VerificationResult:
    threshold: float
    gram_coverage: float
    dishes: tuple[DishVerification, ...]
    unmatched_grams: float
    needs_review_count: int
    unmatched_count: int
    review_list: tuple[IngredientMapping, ...]

    @property
    def dish_count(self) -> int:
        return len(self.dishes)

    @property
    def verifiable_dish_count(self) -> int:
        return sum(dish.verifiable for dish in self.dishes)

    @property
    def verifiable_dish_share(self) -> float | None:
        return self.verifiable_dish_count / self.dish_count if self.dishes else None

    @property
    def all_dishes_verifiable(self) -> bool:
        """The strict basis: every dish verifiable. A plan with no dishes is not."""
        return bool(self.dishes) and self.verifiable_dish_count == self.dish_count


def dish_verifiable(dish: DishCoverage, threshold: float = DEFAULT_COVERAGE_THRESHOLD) -> bool:
    return dish.total_grams > 0 and dish.coverage >= threshold


def verify_coverage(
    result: PlanCoverage,
    *,
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> VerificationResult:
    mappings = result.mappings
    return VerificationResult(
        threshold=threshold,
        gram_coverage=result.coverage,
        dishes=tuple(
            DishVerification(dish.slot_id, dish.name, dish.coverage, dish_verifiable(dish, threshold))
            for dish in result.dishes
        ),
        unmatched_grams=result.total_grams - result.mapped_grams,
        needs_review_count=sum(item.status == "needs_review" for item in mappings),
        unmatched_count=sum(item.status == "unmatched" for item in mappings),
        review_list=tuple(item for item in mappings if item.status != "matched"),
    )
