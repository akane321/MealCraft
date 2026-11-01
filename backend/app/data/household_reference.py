"""The household reference tables: HPB energy and sodium by age band and sex, and the basics assumed at home.

Both are small committed data files: `data/nutrition/hpb-reference-v1.json` (values transcribed from HealthHub,
with a check per value) and `data/ingredients/basic-seasonings-v2.json` (ADR-0068, ADR-0072 section 2, widened on
2026-10-29).
"""

import json
from fractions import Fraction
from functools import lru_cache
from typing import get_args

from app.core.paths import data_root

HPB_FILE = "nutrition/hpb-reference-v1.json"
BASICS_FILE = "ingredients/basic-seasonings-v2.json"
AGE_BANDS = ("toddler", "child", "teen", "adult", "senior")
ACTIVITIES = ("low", "moderate", "high")
SERVINGS_RANGE = (Fraction(1, 4), Fraction(3))


@lru_cache
def hpb() -> dict:
    return json.loads((data_root() / HPB_FILE).read_text(encoding="utf-8"))


@lru_cache
def _basics_file() -> dict:
    return json.loads((data_root() / BASICS_FILE).read_text(encoding="utf-8"))


@lru_cache
def basic_seasonings() -> dict[str, dict]:
    """normalized_name -> {normalized_name, display_name, category, allergens}: everything assumed at home."""
    return {item["normalized_name"]: item for item in _basics_file()["items"]}


@lru_cache
def basic_categories() -> dict[str, str]:
    """category id -> label, in the order the profile page groups them."""
    return {category["id"]: category["label"] for category in _basics_file()["categories"]}


@lru_cache
def basic_short_labels() -> dict[str, str]:
    """category id -> the plural noun the grocery note counts in, in the same order."""
    return {category["id"]: category["short"] for category in _basics_file()["categories"]}


def _rows(age_band: str | None, sex: str | None) -> list[dict]:
    band = age_band or "adult"  # null reads as adult (docs/design/sprint2-schema-foundation.md)
    return [row for row in hpb()["rows"] if row["age_band"] == band and (sex is None or row["sex"] == sex)]


def _row_energy(row: dict, activity: str | None) -> float | None:
    # A null activity reads as moderate (`energy_kcal`); toddler rows are not split by activity.
    return row.get("energy_kcal_by_activity", {}).get(activity or "moderate", row["energy_kcal"])


def energy(age_band: str | None, sex: str | None, activity: str | None = None) -> float | None:
    """The HPB energy need in kcal for the activity column; a null sex is the mean of both rows."""
    values = [_row_energy(row, activity) for row in _rows(age_band, sex)]
    if not values or any(value is None for value in values):
        return None
    return sum(values) / len(values)


def default_servings(
    age_band: str | None, sex: str | None, goal: str | None, activity: str | None = None
) -> tuple[float, str]:
    """Portions a meal from energy need over the adult reference (ADR-0071 section 3), and where it came from.

    Fat loss takes 10% off (the table's `goal_factors`). A band with no researched energy is 1.0, flagged.
    """
    need = energy(age_band, sex, activity)
    if need is None:
        return 1.0, "fallback_todo"
    table = hpb()
    servings = Fraction(str(need)) / table["adult_reference"]["energy_kcal"]
    if goal in table["goal_factors"]:
        servings *= Fraction(str(table["goal_factors"][goal]))
    low, high = SERVINGS_RANGE
    return round(float(min(high, max(low, servings))), 2), "hpb_default"


def daily_energy_kcal(
    age_band: str | None, sex: str | None, goal: str | None, activity: str | None = None
) -> float | None:
    """One member's daily energy target in kcal: the HPB need for the band, sex and activity, less 10% for a
    fat-loss goal (the table's `goal_factors`, ADR-0071 section 3). None where HPB has no researched energy.

    A meal's own floor is this times that meal's `energy_floor_share` (data/planning/meal-structure-v1.json:
    lunch and dinner 25%), the energy floor of ADR-0070 section 3 read per member instead of once for the table.
    `meal_shares` (25/35/35) only pro-rates sodium and the other per-day limits.
    """
    need = energy(age_band, sex, activity)
    if need is None:
        return None
    factor = hpb()["goal_factors"].get(goal) if goal else None
    return round(float(Fraction(str(need)) * Fraction(str(factor))) if factor else float(need), 1)


def sodium_limit(age_band: str | None) -> float | None:
    """The HPB daily sodium limit in mg for the band, or None where HPB gives none (children)."""
    values = [row["sodium_mg_max"] for row in _rows(age_band, None) if row["sodium_mg_max"] is not None]
    return min(values) if values else None


def meal_shares() -> dict[str, float]:
    return {meal: share for meal, share in hpb()["meal_shares"].items() if meal != "basis"}


def reference_table() -> dict:
    """What the profile page shows: default portions for every band, sex, activity and goal, sodium limits, the
    basics."""
    table = hpb()
    goals = {"none": None, "fat_loss": "fat_loss", "muscle_gain": "muscle_gain"}
    return {
        "default_servings": {
            band: {
                sex_key: {
                    activity: {
                        goal_key: default_servings(band, sex, goal, activity)[0] for goal_key, goal in goals.items()
                    }
                    for activity in ACTIVITIES
                }
                for sex_key, sex in (("female", "female"), ("male", "male"), ("any", None))
            }
            for band in AGE_BANDS
        },
        "sodium_limit_mg": {band: sodium_limit(band) for band in AGE_BANDS},
        "basics": list(basic_seasonings().values()),
        "basic_categories": [{"id": key, "label": label} for key, label in basic_categories().items()],
        "meal_shares": meal_shares(),
        "sources": [
            {key: table[part][key] for key in ("title", "url", "retrieved_on")} for part in ("source", "sodium_source")
        ],
        "meal_structure": structure_reference(),
    }


def structure_reference() -> dict:
    """The full meal structure the profile editor offers (ADR-0070): presets, the dinner table, energy floors,
    the equipment a kitchen may lack, and the shelf-life and shopping-trip days."""
    from app.data import meal_structure
    from app.schemas.catalog_tags import Equipment
    from app.schemas.meal_plan import STRUCTURED_PRESETS

    floors = meal_structure.meal_structure()["energy_floor_share"]
    return {
        "presets": STRUCTURED_PRESETS,
        "dinner_counts": meal_structure.dinner_counts(),
        "energy_floor_share": {meal: share for meal, share in floors.items() if meal != "note"},
        "equipment": list(get_args(Equipment)),
        "perishable_days": meal_structure.perishable_days(),
        "trip_days": meal_structure.trip_days(),
    }
