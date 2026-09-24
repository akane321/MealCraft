"""Choose, for one household, which option of an "A or B" recipe line to cook with.

A combined ingredient (`beef_or_turkey`) is priced as one product, so without a
choice a household that avoids beef either loses the recipe or is sold beef. Here
the line becomes its first option the household can eat and can buy, in the order
most recipes write them. When no option qualifies the line stays combined, and the
ordinary allergen and exclusion checks reject the recipe as before.

Every consumer of recipe lines calls `lines()`, so eligibility, pantry matching,
cost and the shopping list all see the same choice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.data.allergens import allergen_conflicts
from app.data.ingredient_hierarchy import expand_exclusions


class Household(Protocol):
    allergens: Sequence[str]
    excluded_ingredients: Sequence[str]


@dataclass(frozen=True)
class Option:
    normalized_name: str
    display_name: str
    allergens: tuple[str, ...]


@dataclass(frozen=True)
class ChosenIngredient:
    """Stands in for the ORM ingredient of a resolved line; read-only."""

    normalized_name: str
    display_name: str
    allergens: list[str]
    alternatives: None = None


@dataclass(frozen=True)
class ChosenLine:
    """A recipe line cooked with one option of its combined ingredient."""

    ingredient: ChosenIngredient
    quantity: object
    unit: str | None
    preparation: str | None
    chosen_from: str  # the combined ingredient's display name, e.g. "beef or turkey"


def choose(alternatives: Iterable[dict] | None, household: Household) -> Option | None:
    """The first option this household can eat and the planner can buy, or None."""
    if not alternatives:
        return None
    from app.planning.grocery_estimator import priceable_ingredients  # grocery_estimator imports this module

    excluded = set(expand_exclusions(household.excluded_ingredients))
    buyable = priceable_ingredients()
    for raw in alternatives:
        option = Option(raw["normalized_name"], raw["display_name"], tuple(raw.get("allergens") or ()))
        if option.normalized_name in excluded or option.normalized_name not in buyable:
            continue
        present, _ = allergen_conflicts(household.allergens, option.allergens)
        if not present:
            return option
    return None


def lines(recipe, household: Household) -> list:
    """The recipe's ingredient lines as this household would cook them."""
    resolved = []
    for item in recipe.recipe_ingredients:
        option = choose(getattr(item.ingredient, "alternatives", None), household)
        if option is None:
            resolved.append(item)
            continue
        resolved.append(
            ChosenLine(
                ingredient=ChosenIngredient(option.normalized_name, option.display_name, list(option.allergens)),
                quantity=item.quantity,
                unit=item.unit,
                preparation=item.preparation,
                chosen_from=item.ingredient.display_name,
            )
        )
    return resolved
