"""Recipe and package unit bases shared by grocery estimation and product parsing.

`app.evaluation.strict_success` keeps its own table on purpose: the scorer must
not share code with the planner it scores.
"""

from collections import defaultdict
from collections.abc import Iterable

UNIT_BASE: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "tbsp": ("ml", 15.0),
    "tsp": ("ml", 5.0),
    "whole": ("whole", 1.0),
    "pc": ("whole", 1.0),
    "pcs": ("whole", 1.0),
}

# Grams in one 236.6 ml US cup of the liquids recipes measure both by weight and by volume: the curated
# catalog has millilitres of milk and tablespoons of oil, the release catalog grams of both. Copied from
# the release ingredients' `unit_grams` (data-engineering/data/release/v2.1/ingredients.jsonl), the
# weights the reviewed FairPrice mapping converts bottles with ("830 ml x 1.031 g/ml"); a test holds the
# two equal. Only quantities of the ingredient itself are converted (a recipe line, a pantry entry), never
# a product: a jar of stock cubes is not a litre of stock.
CUP_ML = 236.6
GRAMS_PER_CUP: dict[str, float] = {
    "milk": 244,
    "cream": 238,
    "yogurt": 245,
    "coconut_milk": 226,
    "olive_oil": 216,
    "peanut_oil": 216,
    "vegetable_oil": 218,
    "sesame_oil": 218,
    "coconut_oil": 218,
    "sunflower_oil": 218,
    "soy_sauce": 255,
    "chicken_broth": 236.6,
    "beef_broth": 240,
    "vegetable_broth": 239,
}


def weighed(lines: Iterable[tuple[str, str | None]]) -> frozenset[str]:
    """Of (ingredient, base unit) lines, the ingredients measured in both g and ml whose density is known.

    One shopping list buys each of them by weight, so it has one line and one product for it. An
    ingredient with no known density keeps a line in each unit; one measured in one unit keeps it.
    """
    units: dict[str, set] = defaultdict(set)
    for name, unit in lines:
        units[name].add(unit)
    return frozenset(name for name, seen in units.items() if {"g", "ml"} <= seen and name in GRAMS_PER_CUP)


def in_grams(quantity: float | None, unit: str | None, ingredient: str) -> tuple[float | None, str | None]:
    """Millilitres of an ingredient with a known density in grams; any other quantity as it is."""
    grams = GRAMS_PER_CUP.get(ingredient)
    if unit != "ml" or grams is None:
        return quantity, unit
    return (quantity * grams / CUP_ML if quantity is not None else None), "g"
