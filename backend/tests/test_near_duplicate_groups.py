"""Synthetic developer checks, not a calibrated production threshold or accuracy claim."""

from itertools import permutations

import pytest

from app.planning.near_duplicate_groups import NearDuplicatePolicy, classify, group_candidates
from app.planning.recipe_pair_similarity import RecipePairSignals

POLICY = NearDuplicatePolicy("synthetic-test-v1", 0.5, 0.6, 0.85)


@pytest.mark.parametrize(
    "signals, expected",
    [
        # Same dish with small name/ingredient changes; all evidence agrees.
        (RecipePairSignals(0.8, 0.8, 0.95, "available"), "near"),
        # Soup and salad sharing ingredients must not merge on those ingredients alone.
        (RecipePairSignals(1 / 3, 1, 0.9, "available"), "distinct"),
        # Similar names and vectors cannot hide a different ingredient set.
        (RecipePairSignals(1, 0.1, 0.95, "available"), "distinct"),
        (RecipePairSignals(1, 1, None, "catalog_missing"), "unknown"),
        (RecipePairSignals(None, 1, 1, "available"), "unknown"),
        (RecipePairSignals(1, None, 1, "available"), "unknown"),
        (RecipePairSignals(1, 1, float("nan"), "available"), "unknown"),
        (RecipePairSignals(1, 1, 1, "catalog_invalid"), "unknown"),
    ],
)
def test_three_signals_must_agree_and_missing_evidence_cannot_prove_variety(signals, expected):
    assert classify(signals, POLICY) == expected


class ChainIndex:
    def compare(self, left, right):
        if {left, right} == {"a", "c"}:
            return RecipePairSignals(0.1, 0.2, 0.3, "available")
        return RecipePairSignals(1, 1, 1, "available")


def test_a_similarity_bridge_never_merges_different_endpoints_and_input_order_does_not_matter():
    results = [group_candidates(list(order), ChainIndex(), POLICY) for order in permutations("abc")]
    assert all(result == results[0] for result in results)
    assert results[0].groups == (("a", "b"), ("c",))
    # b and c are still near: the later objective must not count them as distinct
    # solely because complete-link grouping put them in different groups.
    assert results[0].near_pairs == (("a", "b"), ("b", "c"))


def test_unknown_pairs_remain_visible_even_when_placed_in_separate_groups():
    class MissingIndex:
        def compare(self, left, right):
            return RecipePairSignals(1, 1, None, "catalog_missing")

    result = group_candidates(["b", "a"], MissingIndex(), POLICY)
    assert result.groups == (("a",), ("b",))
    assert result.unknown_pairs == (("a", "b"),)
    assert not result.near_pairs
    assert group_candidates([], MissingIndex(), POLICY).groups == ()
    with pytest.raises(ValueError, match="unique"):
        group_candidates(["a", "a"], MissingIndex(), POLICY)


@pytest.mark.parametrize("value", [0, -1, 1.01, float("nan"), float("inf")])
def test_invalid_thresholds_are_rejected(value):
    with pytest.raises(ValueError, match="Thresholds"):
        NearDuplicatePolicy("dev", value, 0.5, 0.8)
