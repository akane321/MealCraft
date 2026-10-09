"""Release recipes whose own numbers say a line was lost, kept out of planning (still browsable).

The release computes a dish's nutrition by adding up its ingredient grams (ADR-0030). When a line is lost
or its quantity was not parsed, the dish is still listed but no longer adds up: "Steak Teriyaki" with only
its marinade (64 kcal a serving), "Korean Pork Chops" with no pork. A planner that trusts those numbers
serves a sauce as a dinner and counts it as one. Curated recipes are exempt; they were written by hand.
"""

import re
from functools import cache

# A main under this is a sauce, a marinade or a dish that lost its main line, not a dinner.
MAIN_KCAL_FLOOR = 150

# A protein a title names, and the ingredient words that supply it.
TITLE_PROTEINS = {
    "pork": ("pork", "bacon", "ham", "sausage", "chorizo"),
    "chicken": ("chicken",),
    "beef": ("beef", "steak"),
    "steak": ("steak", "beef"),
    "salmon": ("salmon",),
    "shrimp": ("shrimp", "prawn"),
    "lamb": ("lamb",),
    "turkey": ("turkey",),
    "tofu": ("tofu",),
}

# A wrapper without its advertised filling is not a meal. Keep this deliberately
# conservative: require both a wrapper-style dish name and ingredients made only
# of dough components and seasonings. Broth-based soups and filled recipes
# stay eligible because their protein, vegetable, cheese, or other filling is not
# in this set.
WRAPPER_TITLE = re.compile(r"\b(?:cannelloni|dumplings?|empanadas?|pierogi|ravioli|tortellini|wontons?)\b")
DOUGH_ONLY_INGREDIENTS = frozenset(
    {
        "baking powder",
        "baking soda",
        "black pepper",
        "brown sugar",
        "butter",
        "butter or margarine",
        "egg",
        "flour",
        "granulated sugar",
        "lard",
        "margarine",
        "milk",
        "milk or water",
        "olive oil",
        "salt",
        "self-rising flour",
        "shortening",
        "sugar",
        "vegetable oil",
        "vinegar",
        "water",
    }
)


def incomplete(recipe) -> str | None:
    """Why a release recipe cannot be trusted as a planned dinner, or None."""
    if recipe.release_version is None:
        return None
    title = recipe.title.lower()
    if recipe.course in {"main", "side", "soup"} and WRAPPER_TITLE.search(title):
        ingredients = [
            item.ingredient.normalized_name.replace("_", " ").strip().lower() for item in recipe.recipe_ingredients
        ]
        if ingredients and all(name in DOUGH_ONLY_INGREDIENTS for name in ingredients):
            return "wrapper or dough with no filling"
    kcal = float(recipe.nutrition.calories_kcal) if recipe.nutrition is not None else 0.0
    if recipe.course == "main" and kcal < MAIN_KCAL_FLOOR:
        return f"{kcal:.0f} kcal a serving is not a dinner"
    lines = " ".join(item.ingredient.normalized_name.replace("_", " ") for item in recipe.recipe_ingredients)
    for word, sources in TITLE_PROTEINS.items():
        if re.search(rf"\b{word}s?\b", title) and not any(source in lines for source in sources):
            return f"named {word} but lists none"
    return None


# Words that describe a recipe rather than the dish: "Basic Chinese-Style Fried Rice" is fried rice.
DISH_MODIFIERS = frozenset(
    "recipe easy best quick simple the my a an in flash basic classic homemade authentic traditional "
    "perfect favorite favourite ultimate super delicious yummy famous copycat restaurant style chinese "
    "old fashioned".split()
)


def dish_family(title: str) -> str:
    """A dish's name without descriptive words or anyone's name: "Chinese-Style Fried Rice" -> "fried rice"."""
    text = re.sub(r"\(.*?\)", " ", title.lower())
    words = [
        word for word in re.findall(r"[a-z]+(?:'s)?", text) if word not in DISH_MODIFIERS and not word.endswith("'s")
    ]
    return " ".join(words) or title.lower()


@cache
def dish_kind(title: str) -> str:
    """The last two words of a dish's name once descriptions are gone: "Teriyaki Fried Rice" -> "fried rice"."""
    return " ".join(dish_family(title).split()[-2:])
