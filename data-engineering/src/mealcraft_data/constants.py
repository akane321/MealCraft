from __future__ import annotations

SCHEMA_VERSION = "mealcraft.recipe.v1"
TRANSFORMATION_VERSION = "mealcraft-data-cleaning/0.1.0"
RECIPENLG_LICENSE = "Non-commercial research and educational use only"

UNICODE_FRACTIONS = {
    "¼": 0.25,
    "½": 0.5,
    "¾": 0.75,
    "⅐": 1 / 7,
    "⅑": 1 / 9,
    "⅒": 0.1,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}

INFORMAL_QUANTITY_TERMS = (
    "to taste",
    "as needed",
    "as required",
    "handful",
    "pinch",
    "dash",
    "of choice",
)

