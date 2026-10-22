from app.evaluation.baseline_mapping import (
    CoverageResult,
    IngredientMapping,
)
from app.evaluation.baseline_verification import verify_coverage


def test_coverage_at_threshold_is_verifiable():
    result = CoverageResult(
        total_grams=1000,
        matched_grams=900,
        coverage=0.9,
        mappings=(),
    )

    verified = verify_coverage(result)

    assert verified.verifiable is True
    assert verified.coverage == 0.9


def test_coverage_below_threshold_is_not_verifiable():
    result = CoverageResult(
        total_grams=1000,
        matched_grams=899,
        coverage=0.899,
        mappings=(),
    )

    verified = verify_coverage(result)

    assert verified.verifiable is False


def test_reports_mapping_failures():
    result = CoverageResult(
        total_grams=550,
        matched_grams=500,
        coverage=500 / 550,
        mappings=(
            IngredientMapping(
                original_name="chicken breast",
                quantity_g=300,
                ingredient_id="chicken_breast",
                status="matched",
            ),
            IngredientMapping(
                original_name="mystery leaf",
                quantity_g=30,
                ingredient_id=None,
                status="needs_review",
                suggestions=("coriander",),
            ),
            IngredientMapping(
                original_name="unknown powder",
                quantity_g=20,
                ingredient_id=None,
                status="unmatched",
            ),
        ),
    )

    verified = verify_coverage(result)

    assert verified.verifiable is True
    assert verified.unmatched_grams == 50
    assert verified.needs_review_count == 1
    assert verified.unmatched_count == 1
