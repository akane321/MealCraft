"""Developer examples, independent of held-out recipes or labels."""

from types import SimpleNamespace

import pytest

from app.planning import recipe_similarity
from app.planning.recipe_pair_similarity import RecipePairIndex


def recipe(slug, title, ingredients):
    return SimpleNamespace(
        slug=slug,
        external_id=None,
        title=title,
        recipe_ingredients=[SimpleNamespace(ingredient=SimpleNamespace(normalized_name=i)) for i in ingredients],
    )


def test_name_variants_share_core_words_and_duplicate_lines_do_not_inflate_overlap(monkeypatch):
    monkeypatch.setattr(recipe_similarity, "_catalog", lambda: None)
    index = RecipePairIndex(
        [
            recipe("a", "Easy Chinese-Style Fried Rice", ["rice", "egg", "egg"]),
            recipe("b", "Basic Fried Rice", ["egg", "rice"]),
            recipe("c", "Chicken Soup", ["chicken", "carrot"]),
        ]
    )
    variants = index.compare("slug:a", "slug:b")
    different = index.compare("slug:a", "slug:c")
    assert variants.title_overlap == variants.ingredient_overlap == 1
    assert different.title_overlap == different.ingredient_overlap == 0
    assert variants.vector_cosine is None
    assert variants.vector_status == "catalog_missing"


def test_same_ingredients_do_not_erase_different_preparation_and_missing_is_not_zero(monkeypatch):
    monkeypatch.setattr(recipe_similarity, "_catalog", lambda: None)
    index = RecipePairIndex(
        [
            recipe("a", "Tomato Soup", ["tomato", "onion"]),
            recipe("b", "Tomato Salad", ["onion", "tomato"]),
            recipe("c", "", []),
        ]
    )
    signals = index.compare("slug:a", "slug:b")
    assert signals.ingredient_overlap == 1
    assert signals.title_overlap < 1
    empty = index.compare("slug:c", "slug:c")
    assert empty.title_overlap is None
    assert empty.ingredient_overlap is None


@pytest.mark.parametrize(
    "rows, expected, status",
    [
        (bytes([127, 0, 129, 0]), -1, "available"),
        (bytes([60, 80, 30, 40]), 1, "available"),
        (bytes([127, 0, 0, 0]), None, "recipe_vector_missing_or_zero"),
        (bytes([127, 0, 127]), None, "catalog_invalid"),
    ],
)
def test_signed_quantized_vectors_are_normalized_and_incomplete_rows_are_not_compared(
    monkeypatch, rows, expected, status
):
    keys = ["slug:a", "slug:b"]
    meta = {"dimensions": 2, "keys": keys, "model": "synthetic", "texts_sha256": "synthetic"}
    monkeypatch.setattr(recipe_similarity, "_catalog", lambda: (meta, dict(zip(keys, range(2), strict=True)), rows))
    index = RecipePairIndex([recipe("a", "Rice", ["rice"]), recipe("b", "Rice", ["rice"])])
    signals = index.compare(*keys)
    assert signals.vector_status == status
    assert signals.vector_cosine == (pytest.approx(expected) if expected is not None else None)
    assert signals == index.compare(*reversed(keys))


def test_catalog_row_absence_is_unknown_and_stable_keys_must_be_unique(monkeypatch):
    monkeypatch.setattr(recipe_similarity, "_catalog", lambda: ({"dimensions": 2, "keys": []}, {}, b""))
    item = recipe("a", "Rice", ["rice"])
    assert RecipePairIndex([item]).compare("slug:a", "slug:a").vector_cosine is None
    with pytest.raises(ValueError, match="Duplicate recipe key"):
        RecipePairIndex([item, item])


def test_committed_vectors_can_be_compared_without_an_api_call():
    index = RecipePairIndex(
        [
            recipe("tofu-vegetable-soba", "Tofu Soba", ["firm_tofu", "soba_noodle"]),
            recipe("lemon-herb-chicken-rice-bowl", "Lemon Chicken Rice", ["chicken_breast", "rice"]),
        ]
    )
    same = index.compare("slug:tofu-vegetable-soba", "slug:tofu-vegetable-soba")
    other = index.compare("slug:tofu-vegetable-soba", "slug:lemon-herb-chicken-rice-bowl")
    assert same.vector_cosine == pytest.approx(1)
    assert other.vector_cosine < same.vector_cosine
    assert index.vector_source["model"] == "text-embedding-3-small"
    assert len(index.vector_source["texts_sha256"]) == 64
