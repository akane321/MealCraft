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


def test_nothing_described_leaves_the_swap_to_its_usual_order():
    recipe = _recipe(1, "slug:tofu-vegetable-soba", "Tofu Soba", [])

    assert RecipeSimilarity(lambda texts: [_row("slug:tofu-vegetable-soba")]).scores("Day 3.", [recipe]) == {}
    assert RecipeSimilarity(None).scores("fish please", [recipe]) == {}  # no recipe shares a word


def test_without_the_model_or_after_a_failed_call_shared_words_still_follow_the_request():
    tofu = _recipe(1, "slug:tofu-vegetable-soba", "Tofu Soba", [])
    other = _recipe(2, "slug:lemon-chicken", "Lemon Chicken", [])

    def broken(texts):
        raise RuntimeError("no network")

    assert RecipeSimilarity(broken).scores("tofu please", [tofu, other]) == {1: 2.0, 2: 0.0}
    assert RecipeSimilarity(None).scores("tofu please", [tofu, other]) == {1: 2.0, 2: 0.0}


def test_a_condiment_does_not_make_a_dish_what_was_asked_for():
    omelet = _recipe(1, "slug:omelet", "Thai Omelet", ["egg", "fish sauce"])
    salmon = _recipe(2, "slug:salmon-rice", "Rice Bowl", ["salmon fish fillet", "rice"])
    scores = RecipeSimilarity(None).scores("Can Wednesday be fish instead?", [omelet, salmon])
    assert scores == {1: 0.0, 2: 1.0}


def test_a_chinese_request_is_scored_in_english_too():
    from app.planning.recipe_similarity import in_english

    assert in_english("牛肉").endswith("beef")
    assert "korean" in in_english("韩国菜")
    assert "noodles" in in_english("面条") and "pasta" in in_english("意大利面")
    assert in_english("fish") == "fish"  # nothing to translate


def test_without_the_model_a_chinese_request_still_finds_its_dish():
    beef = _recipe(1, "slug:beef-stew", "Beef Stew", ["beef", "carrot"])
    tofu = _recipe(2, "slug:tofu-soba", "Tofu Soba", ["tofu"])
    assert RecipeSimilarity(None).scores("换成牛肉的", [beef, tofu]) == {1: 3.0, 2: 0.0}
