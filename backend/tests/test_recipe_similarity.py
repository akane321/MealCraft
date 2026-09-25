"""A swap follows what the household asked for, among candidates that already hold every hard constraint."""

from types import SimpleNamespace

import pytest

from app.planning import recipe_similarity
from app.planning.recipe_similarity import RecipeSimilarity, wanted


@pytest.mark.parametrize(
    "reason, expected",
    [
        ("Can Wednesday be fish instead?", "fish"),
        ("swap Tuesday for a pasta dish", "pasta"),
        ("换成牛肉的", "牛肉"),
        ("想吃面", "面"),
        ("Replace a meal.", None),
        ("Day 3.", None),
        ("换掉周三", None),
        (None, None),
    ],
)
def test_only_what_was_described_is_matched(reason, expected):
    assert wanted(reason) == expected


def _recipe(i: int, key: str, title: str, ingredients: list[str]) -> SimpleNamespace:
    external_id, slug = (None, key.removeprefix("slug:")) if key.startswith("slug:") else (key, "")
    return SimpleNamespace(
        id=i,
        external_id=external_id,
        slug=slug,
        title=title,
        cuisine="",
        recipe_ingredients=[SimpleNamespace(ingredient=SimpleNamespace(display_name=n)) for n in ingredients],
    )


def _row(key: str) -> list[float]:
    meta, index, rows = recipe_similarity._catalog()
    size = meta["dimensions"]
    return [b - 256 if b > 127 else b for b in rows[index[key] * size : (index[key] + 1) * size]]


def test_the_committed_vectors_rank_the_described_dish_first_and_shared_words_add_a_little():
    tofu, chicken = (
        _recipe(1, "slug:tofu-vegetable-soba", "Tofu Soba", ["firm tofu"]),
        _recipe(2, "slug:lemon-herb-chicken-rice-bowl", "", []),
    )
    similarity = RecipeSimilarity(lambda texts: [_row("slug:tofu-vegetable-soba")])  # a request that "means" tofu soba

    scores = similarity.scores("tofu please", [tofu, chicken])

    assert scores[1] > scores[2]
    assert scores[1] == pytest.approx(1.0 + recipe_similarity.KEYWORD_WEIGHT)  # itself, plus the word "tofu"


def test_nothing_described_or_a_failed_call_leaves_the_swap_to_its_usual_order():
    recipe = _recipe(1, "slug:tofu-vegetable-soba", "Tofu Soba", [])

    def broken(texts):
        raise RuntimeError("no network")

    assert RecipeSimilarity(lambda texts: [_row("slug:tofu-vegetable-soba")]).scores("Day 3.", [recipe]) == {}
    assert RecipeSimilarity(broken).scores("tofu please", [recipe]) == {}
    assert RecipeSimilarity(None).scores("tofu please", [recipe]) == {}
