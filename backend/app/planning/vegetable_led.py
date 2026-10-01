"""The vegetable dish of a meal (素菜) is a side dish or salad led by vegetables (owner, 2026-10-02).

The `vegetable` role admitted any side or salad, so the walkthrough's dinners got "Fettuccine Noodles"
and "Refried Beans" as their vegetable. A dish may fill the role only when vegetables are at least half
of what it is made of, by the grams of its ingredient lines and each ingredient's release food group:

- vegetables: the release's `vegetable` and `herb` groups and edamame, less the starchy tubers
  (potatoes, cassava, taro);
- not counted at all: water and the other liquids (broths, milk, cream, juices, drinks), fats and oils,
  seasonings, sauces and condiments (tomato sauce and paste too), sugars and syrups, leavening. They
  cook or flavour a dish; with them counted, a cabbage slaw in a sweet dressing was not led by its cabbage;
- everything else is food that is not a vegetable: grains, pasta, bread, potatoes, beans and pulses,
  meat, fish, eggs, cheese, fruit, nuts.

Dry rice, pasta, noodles and grains count at 2.5 times their weight, about what they weigh cooked: by
raw weight, Spanish rice and Mexican rice were more tomato than rice. A curated ingredient takes the
group of the release ingredient it is a kind of (`baby_spinach` is `spinach`); one with no group at all is
counted as not a vegetable, so it never makes a dish vegetable-led.

The threshold of one half is where release v2.1's sides and salads turn from mostly other dishes into
mostly vegetable dishes. Their shares are bimodal, most under 0.1 or over 0.9; of the few in between,
those under one half are mostly rice, couscous, potato, bean and meat dishes, those over it mostly
vegetable dishes. Some meat salads, yogurt raitas and tomato-heavy rice dishes still reach it.

The role is the one the profile editor and the shape change call `vegetable` (a second one is
`vegetable-2`), as the main dish is the role called `main`; a household's other roles are unchanged.
"""

import json
import re
from collections.abc import Iterable
from functools import cache

from app.core.paths import repository_root
from app.data.ingredient_hierarchy import runtime

VEGETABLE_ROLE = "vegetable"
VEGETABLE_LED_SHARE = 0.5
COOKED_YIELD = 2.5

VEGETABLE_GROUPS = frozenset({"vegetable", "herb"})
UNCOUNTED_GROUPS = frozenset(
    {"liquid", "beverage", "plant_milk", "fat", "seasoning", "flavoring", "leavening", "condiment", "sweetener"}
)
# Where an ingredient's release group misleads.
VEGETABLES = frozenset({"edamame"})
NOT_VEGETABLES = frozenset(
    {
        "potato",
        "sweet_potato",
        "mashed_potatoes",
        "instant_mashed_potato",
        "hash_brown",
        "tater_tots",
        "cassava",
        "taro",
        "ube",
        "french_fried_onions",
    }
)
UNCOUNTED = frozenset(
    {
        # sauces, broths, soups and their mixes
        "tomato_sauce",
        "tomato_paste",
        "tomato_puree",
        "broth",
        "chicken_broth",
        "beef_broth",
        "vegetable_broth",
        "chicken_or_veg_broth",
        "fish_broth",
        "squid_broth",
        "bouillon",
        "dashi",
        "clam_juice",
        "soup",
        "chicken_soup",
        "mushroom_soup",
        "tomato_soup",
        "celery_soup",
        "cheese_soup",
        "onion_soup_mix",
        "tamarind_soup_base",
        "sinigang_mix",
        "au_jus_mix",
        "gravy",
        "gravy_mix",
        "ranch_mix",
        # juices and zest
        "lemon_juice",
        "lime_juice",
        "orange_juice",
        "pineapple_juice",
        "lemon_zest",
        "lime_zest",
        "orange_zest",
        # milk, cream and butter
        "milk",
        "cream",
        "half_and_half",
        "buttermilk",
        "evaporated_milk",
        "condensed_milk",
        "milk_or_cream",
        "milk_or_water",
        "sour_milk",
        "buttermilk_or_sour_milk",
        "butter",
        # a wrapper, not eaten
        "banana_leaf",
    }
)
COOKED_STAPLES = frozenset(
    {
        "rice",
        "brown_rice",
        "glutinous_rice",
        "wild_rice",
        "long_grain_wild_rice_mix",
        "pasta",
        "macaroni",
        "orzo",
        "cheese_tortellini",
        "gnocchi",
        "egg_noodles",
        "rice_noodles",
        "cellophane_noodles",
        "chow_mein_noodles",
        "ramen",
        "soba_noodles",
        "udon_noodles",
        "somyeon",
        "pancit_canton",
        "sweet_potato_noodles",
        "couscous",
        "quinoa",
        "bulgur",
        "barley",
        "buckwheat",
        "wheat_berries",
        "oats",
        "grits",
    }
)


@cache
def food_groups() -> dict[str, tuple[str, str]]:
    """Each ingredient's release id and food group, by the normalized name the catalog and the planner use.

    An ingredient release v2.1 does not hold (the curated `baby_spinach`) takes the release ingredient it is
    the same as or a variety of in the ingredient hierarchy (`spinach`).
    """
    path = repository_root() / "data-engineering/data/release/v2.1/ingredients.jsonl"
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    groups = {
        name: (name, row["food_group"]) for row in rows for name in [row["ingredient_id"].removeprefix("ING_").lower()]
    }
    entries = runtime().entries

    def release(name: str, seen: frozenset[str] = frozenset()) -> tuple[str, str] | None:
        if name in groups:
            return groups[name]
        parents = [p["id"] for p in entries.get(name, {}).get("parents", []) if p["relation"] in ("same", "variety")]
        return next((found for p in parents if p not in seen and (found := release(p, seen | {name}))), None)

    return groups | {name: found for name in entries if name not in groups and (found := release(name))}


def vegetable_share(lines: Iterable[tuple[str, float | None]]) -> float | None:
    """Vegetables' share of a dish's counted grams, from its (ingredient, grams) lines; None when nothing counts."""
    groups = food_groups()
    vegetables = total = 0.0
    for name, grams in lines:
        name, group = groups.get(name, (name, None))
        if not grams or name in UNCOUNTED or group in UNCOUNTED_GROUPS:
            continue
        weight = float(grams) * (COOKED_YIELD if name in COOKED_STAPLES else 1.0)
        total += weight
        if name in VEGETABLES or (group in VEGETABLE_GROUPS and name not in NOT_VEGETABLES):
            vegetables += weight
    return vegetables / total if total else None


def vegetable_led(lines: Iterable[tuple[str, float | None]]) -> bool:
    share = vegetable_share(lines)
    return share is not None and share >= VEGETABLE_LED_SHARE


def vegetable_role(role_id: str) -> bool:
    """The vegetable role and its copies ("vegetable-2"), as the profile editor and the shape change name them."""
    return re.sub(r"-\d+$", "", role_id) == VEGETABLE_ROLE


def weighed(lines: Iterable[tuple[str, float | None, str | None]]) -> list[tuple[str, float | None]]:
    """(ingredient, quantity, unit) lines as (ingredient, grams): release lines are in grams; others are not weighed."""
    return [(name, quantity if unit == "g" else None) for name, quantity, unit in lines]


def catalog_vegetable_led(recipe) -> bool:
    """`vegetable_led` for a catalog recipe (`app.models.recipe.Recipe`)."""
    lines = recipe.recipe_ingredients
    return vegetable_led(weighed((line.ingredient.normalized_name, line.quantity, line.unit) for line in lines))


def candidate_vegetable_led(recipe) -> bool:
    """`vegetable_led` for a planning candidate (`PlanningRecipeCandidate`)."""
    return vegetable_led(weighed((line.ingredient_id, line.quantity, line.unit) for line in recipe.ingredients))
