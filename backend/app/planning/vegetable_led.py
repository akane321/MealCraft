"""A vegetable dish is vegetable-led, with at most a measured small flesh seasoning (owner, 2026-10-22).

The `vegetable` role admitted any side or salad, so the walkthrough's dinners got "Fettuccine Noodles"
and "Refried Beans" as their vegetable. A dish may fill the role only when
vegetables are at least half of what it is made of, by the grams of its ingredient lines and each
ingredient's release food group:

- vegetables: the release's `vegetable` and `herb` groups and edamame, less the starchy tubers
  (potatoes, cassava, taro);
- not counted at all: water and the other liquids (broths, milk, cream, juices, drinks), fats and oils,
  seasonings, sauces and condiments (tomato sauce and paste too), sugars and syrups, leavening. They
  cook or flavour a dish; with them counted, a cabbage slaw in a sweet dressing was not led by its cabbage;
- everything else is food that is not a vegetable: grains, pasta, bread, potatoes, beans and pulses,
  meat, fish, eggs, cheese, fruit, nuts.

Owner amendment 2026-10-23: starchy tubers also count as vegetables only when other vegetables
already reach 40% of counted food. Total vegetables must still reach 50%; the flesh caps do not change.

Dry rice, pasta, noodles and grains count at 2.5 times their weight, about what they weigh cooked: by
raw weight, Spanish rice and Mexican rice were more tomato than rice. A curated ingredient takes the
group of the release ingredient it is a kind of (`baby_spinach` is `spinach`); one with no group at all is
counted as not a vegetable, so it never makes a dish vegetable-led.

A whole cabbage, cauliflower, lettuce or broccoli written without a unit ("1 small head cabbage",
"1/2 cauliflower") was weighed by release v2.1 as one leaf or floret: 100 g, 25 g, 10 g, 20 g. Release v2.2
weighs most such lines as a head (data-engineering/scripts/correct_release_v22.py); for any it leaves, a
line is recognised by its grams being exactly its count times that piece weight, and is counted at the
weight the line states for itself ("1 small head cabbage (about 1 lb.)" is 454 g), or else at the
release's own weight for a head of that vegetable (`WHOLE`). Only the share reads this; shopping keeps
the release's grams.

The threshold of one half is where release v2.1's (and v2.2's) sides and salads turn from mostly other dishes into
mostly vegetable dishes. Their shares are bimodal, most under 0.1 or over 0.9; of the few in between,
those under one half are mostly rice, couscous, potato, bean and meat dishes, those over it mostly
vegetable dishes. Yogurt raitas and tomato-heavy rice dishes still reach it.

Listed cured/dried flesh and minced land-animal meat may season a vegetable dish up to 20% of counted
weight. Other flesh is limited to 5%; when both occur, total flesh must still be at most 20%.
An unweighed flesh line cannot qualify as a little. Bonito flakes are weighed flesh for this role;
the older stock/sauce/fat exemptions otherwise remain (ADR-0082 supplements ADR-0054).
This role is not a vegetarian-diet claim: each member's ingredient and diet checks still apply.
Meat or fish is an ingredient of animal flesh (the release's
`dietary_origin`), except the seasonings, stocks and cooking fats made from it (`SEASONING_FROM_FLESH`):
fish sauce and Worcestershire flavour a dish the way salt does. Eggs and dairy are not meat. A line whose
wording names a meat or fish the release mapped to something else is meat too: "1 garlic cloves, minced
or 4 ounces cooked chicken" is mapped to garlic alone (`MEAT_WORDS`).

The role is the one the profile editor and the shape change call `vegetable` (a second one is
`vegetable-2`), as the main dish is the role called `main`; a household's other roles are unchanged.
"""

import json
import math
import re
from collections.abc import Iterable
from functools import cache

from app.core.paths import repository_root
from app.data.ingredient_hierarchy import runtime

VEGETABLE_ROLE = "vegetable"
VEGETABLE_LED_SHARE = 0.5
NON_TUBER_VEGETABLE_SHARE = 0.4
MEAT_SEASONING_SHARE = 0.2
FLESH_SHARE = 0.05
COOKED_YIELD = 2.5
SEASONING_MEAT_IDS = frozenset(
    {
        "bacon",
        "turkey_bacon",
        "pancetta",
        "ham",
        "prosciutto",
        "chorizo",
        "salami",
        "pepperoni",
        "sausage",
        "lap_cheong",
        "ground_beef",
        "ground_pork",
        "corned_beef",
        "pastrami",
        "salt_cod",
        "smoked_haddock",
        "bonito_flakes",
        "dried_shrimp",
        "dried_anchovy",
        "ikan_bilis",
    }
)
LAND_MEAT = r"(?:meat|beef|pork|chicken|turkey|lamb|mutton|veal|duck)"
MINCED_MEAT = re.compile(
    rf"\b(?:ground|minced)\s+(?:(?:lean|fresh|boneless|skinless)\s+)*{LAND_MEAT}\b"
    rf"|\b{LAND_MEAT}(?:\s+(?:breasts?|thighs?|meat))?\s*[,;]?\s*(?:finely\s+)?"
    r"(?:ground|minced)\b(?!\s+[a-z])",
    re.I,
)
PRESERVED_MEAT = re.compile(
    rf"\b(?:dried|smoked|cured|salted)\s+(?:(?:small|baby)\s+)*"
    rf"(?:{LAND_MEAT}|fish|salmon|cod|shrimps?|prawns?|anchov(?:y|ies)|bonito)\b"
    r"|\b(?:shrimps?|prawns?|anchov(?:y|ies))\s*,?\s*dried\b"
    r"|\b(?:lap[\s-]+cheong|ikan[\s-]+bilis|bonito[\s-]+flakes?)\b",
    re.I,
)

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
STARCHY_TUBERS = NOT_VEGETABLES - {"french_fried_onions"}
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
# Animal-derived ingredients that season, moisten or cook a dish rather than being its meat or fish: every
# other ingredient of release `dietary_origin` "flesh" is meat, poultry, fish or seafood.
SEASONING_FROM_FLESH = frozenset(
    {
        # condiments made from anchovy, fish or shellfish (owner, 2026-10-02: seasoning, not fish)
        "fish_sauce",
        "worcestershire",
        "oyster_sauce",
        "shrimp_paste",
        "nuoc_cham",
        "steak_sauce",
        "bonito_flakes",
        # stocks, broths, soups and gravies
        "broth",
        "beef_broth",
        "chicken_broth",
        "chicken_or_veg_broth",
        "fish_broth",
        "squid_broth",
        "clam_juice",
        "bouillon",
        "dashi",
        "dashida",
        "soup",
        "chicken_soup",
        "onion_soup_mix",
        "gravy",
        "gravy_mix",
        "au_jus_mix",
        # rendered fats and gelatin
        "lard",
        "bacon_grease",
        "fish_oil",
        "gelatin",
        "marshmallow",
    }
)
# A whole vegetable the release weighed as one piece: (the grams of that piece, the release's grams for a head).
WHOLE = {
    "cabbage": (100.0, 908.0),
    "cauliflower": (25.0, 588.0),
    "lettuce": (10.0, 539.0),
    "broccoli": (20.0, 300.0),
}
# Lines that count parts of the vegetable, not whole ones ("14 leaves green cabbage", "20 broccoli florets").
PARTS = re.compile(r"\b(?:leaf|leaves|florets?|spears?|hearts?|handfuls?|pieces?)(?![a-z])", re.IGNORECASE)
# A number: "1", "1/2", "1 1/2", "0.25".
NUMBER = r"(?:(\d+)\s+(?=\d+/))?(\d+(?:\.\d+)?)(?:/(\d+))?"
# The count a line starts with.
COUNT = re.compile(rf"\s*{NUMBER}")
# A weight a line states for itself: "(about 1 lb.)", "(500 g)", "16 oz", "(2-pound)".
WEIGHT = re.compile(rf"{NUMBER}[\s-]*(lb|pound|oz|ounce|kg|g|gram)s?\b", re.IGNORECASE)
GRAMS_PER = {"lb": 453.592, "pound": 453.592, "oz": 28.3495, "ounce": 28.3495, "kg": 1000.0, "g": 1.0, "gram": 1.0}
# Meat or fish named in a line's wording ("or 4 ounces cooked chicken"), not as a stock, rendered fat, sauce,
# paste, instant ramen or eggs ("chicken broth", "bacon drippings", "shrimp paste", "duck eggs"), and not a
# mushroom or vegetarian stand-in. An explicit vegetable option after a stock/broth is non-meat for that line.
MEAT_WORDS = re.compile(
    r"(?<!vegetarian )(?<!vegan )(?<!mock )\b(?:chicken|beef|pork|bacon|ham|turkey|lamb|mutton|veal|sausages?|salami"
    r"|pepperoni|chorizo|prosciutto|pancetta|duck|fish|salmon|tuna|cod|shrimps?|prawns?|crabs?|crabmeat|lobsters?"
    r"|clams?|mussels?|oysters?|scallops?|squid|octopus|anchov(?:y|ies)|sardines?)\b"
    r"(?![\s-]*(?:stock|broth|bouillon|consomm|sauce|paste|flavou?r|ramen|eggs?|mushrooms?|(?:fat|grease|drippings)\b)"
    r"|\s*(?:\(\s*or\s+vegetable\s*\)|or\s+vegetable)\s+(?:broth|stock))",
    re.IGNORECASE,
)


@cache
def food_groups() -> dict[str, tuple[str, str, str]]:
    """Each ingredient's release id, food group and dietary origin, by the normalized name the catalog and the
    planner use.

    An ingredient the release does not hold (the curated `baby_spinach`) takes the release ingredient it is
    the same as or a variety of in the ingredient hierarchy (`spinach`).
    """
    path = repository_root() / "data-engineering/data/release/v2.2/ingredients.jsonl"
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    groups = {
        name: (name, row["food_group"], row["dietary_origin"])
        for row in rows
        for name in [row["ingredient_id"].removeprefix("ING_").lower()]
    }
    entries = runtime().entries

    def release(name: str, seen: frozenset[str] = frozenset()) -> tuple[str, str, str] | None:
        if name in groups:
            return groups[name]
        parents = [p["id"] for p in entries.get(name, {}).get("parents", []) if p["relation"] in ("same", "variety")]
        return next((found for p in parents if p not in seen and (found := release(p, seen | {name}))), None)

    return groups | {name: found for name in entries if name not in groups and (found := release(name))}


def _number(whole: str | None, numerator: str, denominator: str | None) -> float:
    return int(whole or 0) + float(numerator) / int(denominator or 1)


def whole_grams(name: str, grams, text: str | None):
    """A line's grams; a whole vegetable the release weighed as one leaf or floret (`WHOLE`) at the weight the
    line states, or else at a head's weight."""
    if name not in WHOLE or not grams or not text or PARTS.search(text) or not (found := COUNT.match(text)):
        return grams
    count = _number(*found.groups())
    piece, head = WHOLE[name]
    if not math.isclose(float(grams), count * piece, abs_tol=0.05):
        return grams
    if stated := WEIGHT.search(text):
        *number, unit = stated.groups()
        return _number(*number) * GRAMS_PER[unit.lower()]
    return count * head


def counted_weights(lines: Iterable[tuple]) -> list[tuple[str, float]]:
    """Solid-food weights under the vegetable-share convention, retaining the original ingredient id."""
    groups = food_groups()
    weights = []
    for name, grams, *text in lines:
        release, group, _ = groups.get(name, (name, None, None))
        grams = whole_grams(release, grams, text[0] if text else None)
        if not grams or release in UNCOUNTED or (group in UNCOUNTED_GROUPS and release != "bonito_flakes"):
            continue
        weights.append((name, float(grams) * (COOKED_YIELD if release in COOKED_STAPLES else 1.0)))
    return weights


def vegetable_share(lines: Iterable[tuple]) -> float | None:
    """Vegetables' share of counted grams; None when nothing counts."""
    groups = food_groups()
    vegetables = tubers = total = 0.0
    for name, weight in counted_weights(lines):
        release, group, _ = groups.get(name, (name, None, None))
        total += weight
        if release in STARCHY_TUBERS:
            tubers += weight
        if release in VEGETABLES or (group in VEGETABLE_GROUPS and release not in NOT_VEGETABLES):
            vegetables += weight
    if total and vegetables / total >= NON_TUBER_VEGETABLE_SHARE:
        vegetables += tubers
    return vegetables / total if total else None


def meat_or_fish(name: str, text: str | None = None) -> bool:
    """Meat, poultry, fish or seafood: animal flesh that is not a seasoning, stock or fat made from it, or a line
    whose wording names one (`MEAT_WORDS`) that the release mapped to something else."""
    release, _, origin = food_groups().get(name, (name, None, None))
    return release == "bonito_flakes" or (
        release not in SEASONING_FROM_FLESH and (origin == "flesh" or bool(text and MEAT_WORDS.search(text)))
    )


def seasoning_meat(name: str, text: str | None = None) -> bool:
    """Only the actual ingredient id/wording establishes preserved or minced meat, never the recipe title."""
    release = food_groups().get(name, (name, None, None))[0]
    text = re.split(r"\b(?:with|plus)\b", text or "", maxsplit=1, flags=re.I)[0]
    if re.search(r"\b(?:and|or)\b", text, re.I) and len(MEAT_WORDS.findall(text)) > 1:
        return False  # One combined amount cannot establish separate preserved/fresh shares.
    return release in SEASONING_MEAT_IDS or bool(text and (MINCED_MEAT.search(text) or PRESERVED_MEAT.search(text)))


def vegetable_led(lines: Iterable[tuple]) -> bool:
    """Half vegetables, total measured flesh <=20%, other flesh <=5%; never a diet claim."""
    lines = list(lines)
    share = vegetable_share(lines)
    flesh = meat_share(lines)
    fresh = meat_share(lines, fresh_only=True)
    return (
        share is not None
        and share >= VEGETABLE_LED_SHARE
        and flesh is not None
        and flesh <= MEAT_SEASONING_SHARE
        and fresh is not None
        and fresh <= FLESH_SHARE
    )


def meat_share(lines: Iterable[tuple], *, fresh_only: bool = False) -> float | None:
    """Flesh over counted food; unknown/invalid flesh quantity is not a small seasoning."""
    lines = list(lines)
    if any(
        meat_or_fish(name, *text)
        and (grams is None or grams <= 0 or food_groups().get(name, (name, None, None))[2] != "flesh")
        for name, grams, *text in lines
    ):
        return None
    total = sum(weight for _, weight in counted_weights(lines))
    meat = sum(
        float(grams)
        for name, grams, *text in lines
        if meat_or_fish(name, *text) and (not fresh_only or not seasoning_meat(name, *text))
    )
    return meat / total if total else (0.0 if not meat else None)


def vegetable_role(role_id: str) -> bool:
    """The vegetable role and its copies ("vegetable-2"), read as every other gate reads a role id: the part before
    the first hyphen (`meal_composition.role_base`), so "vegetable-side" is a vegetable role everywhere."""
    return role_id.split("-")[0] == VEGETABLE_ROLE


def weighed(lines: Iterable[tuple]) -> list[tuple]:
    """(ingredient, quantity, unit, original text) lines as (ingredient, grams, original text): release lines are
    in grams; others are not weighed."""
    return [(name, quantity if unit == "g" else None, text) for name, quantity, unit, text in lines]


def catalog_vegetable_led(recipe) -> bool:
    """`vegetable_led` for a catalog recipe (`app.models.recipe.Recipe`)."""
    lines = recipe.recipe_ingredients
    return vegetable_led(
        weighed((line.ingredient.normalized_name, line.quantity, line.unit, line.original_text) for line in lines)
    )


def candidate_vegetable_led(recipe) -> bool:
    """`vegetable_led` for a planning candidate (`PlanningRecipeCandidate`)."""
    return vegetable_led(
        weighed((line.ingredient_id, line.quantity, line.unit, line.original_text) for line in recipe.ingredients)
    )


def row_vegetable_led(recipe: dict) -> bool:
    """`vegetable_led` for a release catalog row (`app.evaluation.release_catalog`): the label tool's and the
    strict scorer's."""
    return vegetable_led((line["ingredient"], line["quantity"], line.get("text")) for line in recipe["ingredients"])
