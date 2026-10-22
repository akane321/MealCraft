"""The full meal structure's tunable values (ADR-0070) and the cuisine groups (ADR-0068 idealization).

Both are small committed data files read by the planner, never by the importer:
`data/planning/meal-structure-v1.json` (presets, portion shares, energy floors, soft weights, staple kinds, shelf
life and shopping trips) and `data/recipes/cuisine-groups.json` (recipe cuisine -> one of six groups).
"""

import json
from functools import lru_cache

from app.core.paths import data_root

STRUCTURE_FILE = "planning/meal-structure-v1.json"
GROUPS_FILE = "recipes/cuisine-groups.json"


@lru_cache
def meal_structure() -> dict:
    return json.loads((data_root() / STRUCTURE_FILE).read_text(encoding="utf-8"))


@lru_cache
def cuisine_groups() -> dict[str, str]:
    """cuisine -> group; a cuisine not listed has no group."""
    groups = json.loads((data_root() / GROUPS_FILE).read_text(encoding="utf-8"))["groups"]
    return {cuisine: group for group, cuisines in groups.items() for cuisine in cuisines}


def cuisine_group(cuisine: str | None) -> str | None:
    return cuisine_groups().get(cuisine) if cuisine else None


def presets() -> dict[str, list[dict]]:
    """The full default's roles of each meal, as JSON role dicts (`PlanningMealRole`)."""
    return {meal: roles for meal, roles in meal_structure()["presets"].items() if meal != "note"}


def portion_shares() -> dict:
    return {key: value for key, value in meal_structure()["portion_shares"].items() if key != "note"}


def energy_floor_share(meal: str) -> float | None:
    return meal_structure()["energy_floor_share"].get(meal)


def soft_weights() -> dict:
    return meal_structure()["soft"]


@lru_cache
def _plain_staples() -> dict[str, str]:
    defaults = meal_structure()["staple_defaults"]
    return {recipe_id: kind for kind, ids in defaults.items() if kind != "note" for recipe_id in ids}


def plain_staple_kind(recipe_id: str) -> str | None:
    """The kind of a plain staple (`staple_defaults`), by release id or by a release slug, which ends with the id's
    hex; None for any other recipe."""
    plain = _plain_staples()
    if recipe_id in plain:
        return plain[recipe_id]
    return plain.get(f"RCP2_{recipe_id.rsplit('-', 1)[-1].upper()}")


def usual_staple_kinds(group: str | None) -> list[str]:
    table = meal_structure()["staple_kind_by_group"]
    return table.get(group or "none") or table["none"]


def perishable_days() -> int:
    return meal_structure()["perishable_days"]


MAX_PLAN_DAYS = 14  # the longest plan a request may ask for (day_count le=14)
MIN_TRIP_DAYS = -(-MAX_PLAN_DAYS // 2)  # ceil(14 / 2): pricing and budgeting assume at most two shopping trips


def trip_days() -> int:
    """Days of a plan bought in the first trip; below MIN_TRIP_DAYS a long plan would need a third trip."""
    days = meal_structure()["trip_days"]
    if days < MIN_TRIP_DAYS:
        raise ValueError(f"trip_days {days} would plan a third shopping trip; it must be at least {MIN_TRIP_DAYS}")
    return days


def roles_for(roles: list[dict], people: int) -> list[dict]:
    """The roles a meal has with `people` at it: a role with min_people only from that many on."""
    return [role for role in roles if (role.get("min_people") or 0) <= people]


def dinner_counts() -> list[dict]:
    """The full default's dinner by people at it (ADR-0070 table): one row per run of equal counts, up to 12."""
    rows: list[dict] = []
    for people in range(1, 13):
        kinds = [role["role_id"].split("-")[0] for role in roles_for(presets()["dinner"], people)]
        counts = {
            "protein_mains": kinds.count("main"),
            "vegetables": kinds.count("vegetable"),
            "soup": kinds.count("soup"),
            "staple": kinds.count("staple"),
        }
        if rows and {key: rows[-1][key] for key in counts} == counts:
            rows[-1]["max_people"] = None if people == 12 else people
        else:
            if rows and rows[-1]["max_people"] is None:
                rows[-1]["max_people"] = people - 1
            rows.append({"min_people": people, "max_people": None if people == 12 else people, **counts})
    return rows
