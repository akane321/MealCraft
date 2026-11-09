from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.planning.acceptance_evidence import (
    NearDuplicateReviewBatch,
    NearDuplicateThresholdFreeze,
    PriceReferenceDomain,
    assess_price_gap,
    assess_real_minimum_readiness,
    compare_package_policies,
    verify_near_duplicate_freeze,
)
from app.planning.swap_diversity import FROZEN_SWAP_ACCEPTANCE_POLICY


def test_fixed_generated_options_cannot_be_called_a_real_minimum():
    evidence = assess_price_gap(
        10.50,
        10,
        PriceReferenceDomain(
            candidate_scope="generated_options",
            packaging_scope="fixed_product",
            price_source="fixture",
            exact=True,
        ),
    )
    assert evidence.within_five_percent
    assert evidence.claim_scope == "generated-domain-reference"
    assert evidence.ratio == Decimal("1.05")


def test_real_minimum_claim_requires_every_domain_condition():
    complete = {
        "candidate_scope": "full_supported_catalog",
        "packaging_scope": "mixed_packages",
        "price_source": "observed_snapshot",
        "exact": True,
    }
    assert assess_price_gap(10, 10, PriceReferenceDomain(**complete)).claim_scope == "real-minimum"
    for field, value in {
        "candidate_scope": "generated_options",
        "packaging_scope": "fixed_product",
        "price_source": "fixture",
        "exact": False,
    }.items():
        domain = PriceReferenceDomain(**dict(complete, **{field: value}))
        assert assess_price_gap(10, 10, domain).claim_scope == "generated-domain-reference"


def test_price_gap_rejects_an_invalid_reference_and_a_quote_below_the_reference():
    domain = PriceReferenceDomain(
        candidate_scope="generated_options",
        packaging_scope="fixed_product",
        price_source="fixture",
        exact=True,
    )
    with pytest.raises(ValueError, match="positive"):
        assess_price_gap(1, 0, domain)
    assert not assess_price_gap(9, 10, domain).within_five_percent


def test_real_minimum_readiness_reports_the_actual_missing_domain_layers():
    ingredients = {
        "rice": {"status": "mapped", "products": [{"id": "small"}, {"id": "large"}]},
        "tofu": {"status": "mapped", "products": [{"id": "one"}]},
        "water": {"status": "not_purchased", "products": []},
    }
    result = assess_real_minimum_readiness(
        ingredients,
        observed_snapshot=True,
        full_supported_catalog=False,
        mixed_packages_in_product=False,
        exact_joint_plan_and_purchase_solver=False,
    )
    assert (result.mapped_ingredients, result.product_observations, result.multi_product_ingredients) == (2, 3, 1)
    assert not result.ready
    assert result.blockers == (
        "candidate_domain_is_not_the_full_supported_catalog",
        "product_path_does_not_support_mixed_packages",
        "no_exact_joint_plan_and_purchase_solve",
    )


def test_real_minimum_readiness_requires_every_layer_even_with_one_product_each():
    result = assess_real_minimum_readiness(
        {"rice": {"status": "mapped", "products": [{}]}},
        observed_snapshot=True,
        full_supported_catalog=True,
        mixed_packages_in_product=True,
        exact_joint_plan_and_purchase_solver=True,
    )
    assert result.ready and result.blockers == ()


def test_matched_package_comparison_can_measure_a_mixed_package_saving():
    products = [
        {"external_id": "large", "package_grams": 10, "price_sgd": 9, "in_stock": True},
        {"external_id": "small", "package_grams": 6, "price_sgd": 5, "in_stock": True},
    ]
    result = compare_package_policies("rice", products, 16)
    assert result is not None
    assert result.fixed_product_cost_sgd == Decimal("15")
    assert result.mixed_package_cost_sgd == Decimal("14")
    assert result.savings_sgd == Decimal("1")
    assert result.mixed_allocations == (("large", 1), ("small", 1))


def test_matched_package_comparison_uses_only_valid_in_stock_whole_cent_rows():
    products = [
        {"external_id": "valid", "package_grams": 10, "price_sgd": 2, "in_stock": True},
        {"external_id": "gone", "package_grams": 100, "price_sgd": 0.5, "in_stock": False},
        {"external_id": "fractional", "package_grams": 100, "price_sgd": 0.001, "in_stock": True},
    ]
    result = compare_package_policies("rice", products, 11)
    assert result is not None
    assert result.fixed_product_cost_sgd == result.mixed_package_cost_sgd == Decimal("4")
    assert compare_package_policies("rice", [], 11) is None


def review(**changes):
    data = {
        "schema_version": "near-duplicate-review-v1",
        "producer_id": "producer-a",
        "reviewer_id": "reviewer-b",
        "source_sha256": "a" * 64,
        "rows": [{"pair_id": "PAIR-001", "verdict": "near", "rationale": "Same preparation."}],
    }
    return NearDuplicateReviewBatch.model_validate(dict(data, **changes))


def test_review_requires_an_independent_identified_reviewer():
    with pytest.raises(ValidationError, match="independent"):
        review(reviewer_id="producer-a")
    with pytest.raises(ValidationError):
        review(reviewer_id="")


def test_unsure_is_preserved_but_blocks_threshold_freeze():
    batch = review(rows=[{"pair_id": "PAIR-030", "verdict": "unsure", "rationale": "Evidence is ambiguous."}])
    assert not batch.freeze_ready
    assert review().freeze_ready


def test_review_pair_ids_are_unique():
    row = {"pair_id": "PAIR-001", "verdict": "distinct", "rationale": "Different preparation."}
    with pytest.raises(ValidationError, match="unique"):
        review(rows=[row, row])


def freeze(batch, **changes):
    data = {
        "schema_version": "near-duplicate-threshold-freeze-v1",
        "policy_version": "product-swap-acceptance-v1",
        "review_batch_sha256": batch.content_sha256,
        "title_min": 0.2,
        "ingredients_min": 0.05,
        "cosine_min": 0.75,
        "fried_rice_cosine_min": 0.64,
    }
    return NearDuplicateThresholdFreeze.model_validate(dict(data, **changes))


def test_formal_freeze_binds_reviewed_bytes_and_runtime_thresholds():
    batch = review()
    assert verify_near_duplicate_freeze(batch, freeze(batch), FROZEN_SWAP_ACCEPTANCE_POLICY) == ()
    changed = review(rows=[{"pair_id": "PAIR-001", "verdict": "distinct", "rationale": "Changed."}])
    assert verify_near_duplicate_freeze(changed, freeze(batch), FROZEN_SWAP_ACCEPTANCE_POLICY) == (
        "review_batch_digest_mismatch",
    )


def test_formal_freeze_rejects_unsure_rows_and_threshold_drift():
    batch = review(rows=[{"pair_id": "PAIR-030", "verdict": "unsure", "rationale": "Ambiguous."}])
    candidate = freeze(batch, cosine_min=0.7)
    assert verify_near_duplicate_freeze(batch, candidate, FROZEN_SWAP_ACCEPTANCE_POLICY) == (
        "review_batch_has_unsure_verdicts",
        "runtime_policy_mismatch",
    )
