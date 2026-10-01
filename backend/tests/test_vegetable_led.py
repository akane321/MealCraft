"""The vegetable dish of a meal is a side or salad of vegetables without meat (owner, 2026-10-02)."""

import pytest

from app.planning.vegetable_led import (
    SEASONING_FROM_FLESH,
    food_groups,
    meat_or_fish,
    vegetable_led,
    vegetable_role,
    vegetable_share,
    whole_grams,
)


def test_the_walkthrough_vegetables_are_not_led_by_vegetables():
    # The release lines of "Fettuccine Noodles" and "Refried Beans", which filled the vegetable role.
    fettuccine = [("egg_noodles", 340), ("margarine", 57), ("yogurt", 368), ("parmesan", 14), ("salt", 2)]
    refried = [("pinto_beans", 425), ("salsa", 125)]
    assert vegetable_share(fettuccine) == 0 and vegetable_share(refried) == 0
    assert not vegetable_led(fettuccine) and not vegetable_led(refried)


def test_a_vegetable_dish_is_weighed_without_its_dressing_fat_and_liquid():
    slaw = [("cabbage", 400), ("carrot", 60), ("mayo", 200), ("sugar", 50), ("vinegar", 30)]
    assert vegetable_share(slaw) == 1.0
    braised = [("bok_choy", 300), ("chicken_broth", 400), ("oyster_sauce", 30), ("garlic", 6), ("olive_oil", 15)]
    assert vegetable_led(braised)


def test_dry_rice_counts_at_its_cooked_weight():
    spanish_rice = [("rice", 185), ("tomato", 180), ("onion", 110), ("bell_pepper", 74), ("water", 296)]
    # 364 g of vegetables outweigh 185 g of raw rice, but not the 462.5 g it cooks to.
    assert vegetable_share(spanish_rice) == pytest.approx(364 / (364 + 462.5))
    assert not vegetable_led(spanish_rice)


def test_potatoes_and_ungrouped_ingredients_never_lead_and_a_curated_id_takes_its_release_group():
    assert not vegetable_led([("potato", 500), ("onion", 50)])
    assert not vegetable_led([("no_such_ingredient", 300)])
    assert vegetable_share([("water", 500), ("salt", 5)]) is None
    assert vegetable_led([("baby_spinach", 200), ("olive_oil", 15)])  # a variety of spinach in the hierarchy
    assert vegetable_share([("chickpea", 100), ("spinach", 100)]) == 0.5  # one half is enough


def test_the_vegetable_role_is_vegetable_and_its_numbered_copies():
    assert vegetable_role("vegetable") and vegetable_role("vegetable-2")
    assert not any(vegetable_role(role) for role in ("main", "main-2", "soup", "side", "vegetables", "veg"))


def test_a_dish_with_any_meat_or_fish_is_not_a_vegetable_dish():
    # "Saigon Chicken Cole Slaw" (release lines): 62% cabbage, onion and carrot, and 344 g of chicken. The
    # product planned it as the vegetable of mdw-dev-002 and mdw-dev-007 (review of #210).
    slaw = [
        ("cabbage", 453.6),
        ("onion", 55.0),
        ("carrot", 122.0),
        ("chicken_breast", 344.0),
        ("black_pepper", 3.4),
        ("rice_vinegar", 64.2),
        ("lemon", 50.0),
        ("fish_sauce", 72.0),
        ("sugar", 37.5),
    ]
    assert vegetable_share(slaw) > 0.6 and not vegetable_led(slaw)
    # However little of it: three anchovy fillets in a kimchi, or a line of bacon the release did not weigh.
    assert not vegetable_led([("daikon", 453.6), ("cabbage", 113.4), ("anchovy", 12.0)])
    assert not vegetable_led([("green_beans", 450.0), ("bacon", None)])


def test_seasonings_stocks_and_fats_made_from_meat_or_fish_and_eggs_and_dairy_are_not_meat():
    # Owner, 2026-10-02: anchovy-based condiments such as fish sauce and Worcestershire are seasoning, not fish.
    for seasoning in ("fish_sauce", "worcestershire", "oyster_sauce", "shrimp_paste", "nuoc_cham", "steak_sauce"):
        assert seasoning in SEASONING_FROM_FLESH and not meat_or_fish(seasoning), seasoning
        assert vegetable_led([("spinach", 300.0), (seasoning, 10.0)]), seasoning
    for other in ("bonito_flakes", "chicken_broth", "dashi", "lard", "bacon_grease", "gelatin"):
        assert not meat_or_fish(other), other
    for flesh in ("anchovy", "bacon", "ham", "chicken_breast", "beef_steak", "shrimp", "crab", "tuna", "pork_fatback"):
        assert meat_or_fish(flesh), flesh
    for food in ("egg", "parmesan", "yogurt", "milk", "tofu", "chickpea"):
        assert not meat_or_fish(food), food
    # Every name on the list is of animal flesh in release v2.1, so a misspelt one cannot hide.
    assert all(food_groups()[name][2] == "flesh" for name in SEASONING_FROM_FLESH)


def test_a_whole_head_the_release_weighed_as_one_leaf_counts_at_a_heads_weight():
    # "Fried Cabbage" (release lines): "1 medium cabbage" weighed at 100 g, one leaf, under 281 g of flour.
    fried = [
        ("cabbage", 100.0, "1 medium cabbage"),
        ("butter", 14.2, "1 Tbsp. butter"),
        ("egg", 200.0, "4 eggs"),
        ("flour", 281.2, "2 1/4 c. flour"),
    ]
    assert vegetable_share(fried) == pytest.approx(908 / (908 + 200 + 281.2))
    assert vegetable_led(fried) and not vegetable_led([line[:2] for line in fried])
    assert whole_grams("cabbage", 50.0, "1/2 large head cabbage") == 454
    assert whole_grams("cabbage", 33.3, "1/3 small head cabbage") == pytest.approx(908 / 3)  # the release rounds
    assert whole_grams("cabbage", 150.0, "1 1/2 small cabbages") == pytest.approx(1362)
    assert whole_grams("cauliflower", 25.0, "1 medium head cauliflower (about 1 1/2 lb.), trimmed") == 588
    assert whole_grams("lettuce", 2.5, "1/4 iceberg lettuce") == pytest.approx(539 / 4)
    assert whole_grams("broccoli", 20.0, "1 Broccoli") == 300
    # Leaves, florets and pieces are parts; a weight the release took from the wording, a cup, a head the
    # release already weighs, a line with no wording and another vegetable all stay as weighed.
    assert whole_grams("cabbage", 1400.0, "14 leaves green cabbage") == 1400
    assert whole_grams("broccoli", 400.0, "20 broccoli florets") == 400
    assert whole_grams("lettuce", 160.0, "16 piece(s) lettuce") == 160
    assert whole_grams("cabbage", 1814.4, "1 (4 lb) cabbage") == 1814.4
    assert whole_grams("cabbage", 534.0, "6 c. cabbage (1 small head), cut into 1-inch squares") == 534
    assert whole_grams("cabbage", 908.0, "1 head cabbage, cored and shredded") == 908
    assert whole_grams("cabbage", 100.0, None) == 100
    assert whole_grams("bok_choy", 85.0, "1 small head bok choy") == 85
