"""The vegetable dish of a meal is a side or salad led by vegetables (owner, 2026-10-02)."""

import pytest

from app.planning.vegetable_led import vegetable_led, vegetable_role, vegetable_share


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
