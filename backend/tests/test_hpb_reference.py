"""The HPB reference table and the basic seasonings (layer 08): values pinned to the researched sources."""

import json

import pytest

from app.core.paths import data_root
from app.data import household_reference
from app.data.household_reference import (
    basic_seasonings,
    default_servings,
    energy,
    hpb,
    reference_table,
    sodium_limit,
)

# Transcribed from HealthHub on 2026-10-18 (moderate activity; toddlers are not split by activity).
ENERGY = {
    ("toddler", "female"): 1000,
    ("toddler", "male"): 1080,
    ("child", "female"): 1620,
    ("child", "male"): 1740,
    ("teen", "female"): 2400,
    ("teen", "male"): 3120,
    ("adult", "female"): 2035,
    ("adult", "male"): 2590,
    ("senior", "female"): 1865,
    ("senior", "male"): 2235,
}
# The same page's Light / Vigorous (children, teens) and Low / Very active (adults) columns, low-moderate-high.
ACTIVITY = {
    ("child", "female"): (1380, 1620, 1860),
    ("child", "male"): (1480, 1740, 2000),
    ("teen", "female"): (2040, 2400, 2760),
    ("teen", "male"): (2650, 3120, 3590),
    ("adult", "female"): (1720, 2035, 2800),
    ("adult", "male"): (2185, 2590, 3560),
    ("senior", "female"): (1570, 1865, 2560),
    ("senior", "male"): (1885, 2235, 3070),
}
SERVINGS = {
    "toddler": (0.43, 0.47, 0.45),
    "child": (0.70, 0.75, 0.73),
    "teen": (1.04, 1.35, 1.19),
    "adult": (0.88, 1.12, 1.00),
    "senior": (0.81, 0.97, 0.89),
}


def test_the_table_holds_only_researched_values_each_with_a_check():
    table = hpb()
    rows = {(row["age_band"], row["sex"]): row for row in table["rows"]}
    assert {key: row["energy_kcal"] for key, row in rows.items()} == ENERGY
    assert all(row["protein_g"] is None for row in rows.values())
    assert {key for key, row in rows.items() if row["sodium_mg_max"] is not None} == {
        (band, sex) for band in ("adult", "senior") for sex in ("female", "male")
    }
    assert {row["sodium_mg_max"] for row in rows.values()} == {None, 2000}
    checked = {check["field"]: check["value"] for check in table["checks"]}
    for (band, sex), row in rows.items():
        for field in ("energy_kcal", "sodium_mg_max"):
            if row[field] is not None:
                assert checked[f"{band}.{sex}.{field}"] == row[field]
    for (band, sex), levels in ACTIVITY.items():
        assert rows[band, sex]["energy_kcal_by_activity"] == dict(zip(("low", "moderate", "high"), levels, strict=True))
        assert levels[1] == ENERGY[band, sex]
        for level, value in zip(("low", "high"), (levels[0], levels[2]), strict=True):
            assert checked[f"{band}.{sex}.energy_kcal_by_activity.{level}"] == value
    assert "energy_kcal_by_activity" not in rows["toddler", "male"]
    assert len(checked) == 14 + 16
    assert not [item for item in table["todo"] if item["field"].startswith("activity")]
    assert table["adult_reference"]["energy_kcal"] == 2313
    for part in ("source", "sodium_source"):
        assert table[part]["url"].startswith("https://www.healthhub.sg/")


@pytest.mark.parametrize("band", list(SERVINGS))
def test_default_portions_are_energy_over_the_adult_reference(band):
    female, male, either = SERVINGS[band]
    assert default_servings(band, "female", None) == (female, "hpb_default")
    assert default_servings(band, "male", None) == (male, "hpb_default")
    assert default_servings(band, None, None) == (either, "hpb_default")
    # Fat loss takes 10% off; muscle gain changes ranking, not portions.
    assert default_servings(band, "male", "fat_loss")[0] == round(ENERGY[band, "male"] / 2313 * 0.9, 2)
    assert default_servings(band, "male", "muscle_gain")[0] == male
    assert reference_table()["default_servings"][band]["any"]["moderate"]["none"] == either


def test_activity_picks_the_hpb_column_and_unset_reads_as_moderate():
    assert default_servings("adult", "male", None, "high") == (round(3560 / 2313, 2), "hpb_default")
    assert default_servings("adult", "female", None, "low") == (round(1720 / 2313, 2), "hpb_default")
    assert default_servings("teen", "male", None, None) == default_servings("teen", "male", None, "moderate")
    # Toddlers are one value at every level; fat loss still takes 10% off the active column.
    assert default_servings("toddler", "male", None, "high") == default_servings("toddler", "male", None, "low")
    assert default_servings("adult", "male", "fat_loss", "high")[0] == round(3560 / 2313 * 0.9, 2)
    assert energy("adult", None, "low") == (2185 + 1720) / 2
    assert reference_table()["default_servings"]["adult"]["male"]["high"]["none"] == 1.54


def test_an_unset_age_band_reads_as_adult_and_sodium_is_known_for_adults_only():
    assert energy(None, None) == energy("adult", None) == 2312.5
    assert sodium_limit(None) == sodium_limit("adult") == sodium_limit("senior") == 2000
    assert sodium_limit("child") is None and sodium_limit("teen") is None and sodium_limit("toddler") is None


def test_a_band_with_no_researched_energy_falls_back_to_one_portion(monkeypatch):
    table = json.loads(json.dumps(hpb()))
    for row in table["rows"]:
        if row["age_band"] == "teen":
            row["energy_kcal"] = None
            row.pop("energy_kcal_by_activity")
    monkeypatch.setattr(household_reference, "hpb", lambda: table)
    assert default_servings("teen", "female", None) == (1.0, "fallback_todo")
    assert default_servings("adult", "female", None) == (0.88, "hpb_default")


def test_basics_are_exact_catalog_names_with_their_allergens():
    snapshot = json.loads((data_root() / "products/fairprice-v2-snapshot.json").read_text(encoding="utf-8"))
    basics = basic_seasonings()
    assert set(basics) <= set(snapshot["ingredients"])
    assert {"salt", "sugar", "soy_sauce", "garlic", "ginger", "green_onion"} <= set(basics)
    assert "water" not in basics  # never bought anyway
    assert basics["soy_sauce"]["allergens"] == ["gluten", "soy"]
    assert basics["oyster_sauce"]["allergens"] == ["shellfish"]
    assert reference_table()["meal_shares"] == {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.35}
