"""Developer regressions from reviewed pairs; not independent accuracy evidence."""

import pytest

from app.planning.near_duplicate_groups import NearDuplicatePolicy, classify
from app.planning.recipe_pair_similarity import RecipePairIndex, RecipePairSignals
from tests.test_recipe_pair_similarity import recipe

POLICY = NearDuplicatePolicy("peer-review-dev-v2", 0.2, 0.05, 0.75, fried_rice_cosine_min=0.64)


@pytest.mark.parametrize(
    "signals,expected",
    [
        (RecipePairSignals(1 / 3, 3 / 7, 0.7099332645536424, "available"), "distinct"),
        (RecipePairSignals(0.5, 2 / 11, 0.6475723966776182, "available", "fried_rice"), "near"),
        (RecipePairSignals(2 / 7, 2 / 7, 0.6474687627771077, "available", "fried_rice"), "near"),
        (RecipePairSignals(0.5, 0.3, 0.65, "available"), "distinct"),
        (RecipePairSignals(0.5, 0.3, None, "catalog_missing", "fried_rice"), "unknown"),
        (RecipePairSignals(0.5, 0.01, 0.9, "available", "fried_rice"), "distinct"),
        (RecipePairSignals(0.5, 0.3, 0.63, "available", "fried_rice"), "distinct"),
    ],
)
def test_opt_in_preparation_rule_preserves_other_evidence_gates(signals, expected):
    assert classify(signals, POLICY) == expected


def test_shared_preparation_requires_both_titles_and_rejects_other_forms():
    titles = ["Chicken Fried Rice", "Chinese Fried-Rice With Bacon", "Fried Rice Cakes", "Rice With Fried Chicken"]
    index = RecipePairIndex([recipe(str(i), title, ["rice"]) for i, title in enumerate(titles)])
    assert index.compare("slug:0", "slug:1").shared_preparation == "fried_rice"
    for other in ("slug:2", "slug:3"):
        assert index.compare("slug:0", other).shared_preparation is None


def test_original_policy_does_not_implicitly_use_preparation_threshold():
    signals = RecipePairSignals(0.5, 0.3, 0.65, "available", "fried_rice")
    assert classify(signals, NearDuplicatePolicy("old", 0.2, 0.05, 0.7)) == "distinct"
