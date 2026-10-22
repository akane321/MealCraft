"""Map a baseline's ingredient lines to catalog ingredients, dish by dish (ADR-0069 section 2, ADR-0074 section 2).

The order is ADR-0069's: the catalog id or name, then a listed other name, then similarity, then the parent
in the ingredient hierarchy. Every line records which method mapped it and whether it waits for a person:

- an id or a display name is accepted as it is;
- an other name alone is flagged (the other-name lists are model-generated and unreviewed, ADR-0069 section 3);
- a similarity match must clear `SIMILARITY_FLOOR` and is flagged;
- a line that names a kind of a catalog ingredient ("baby spinach leaves") maps to that ingredient, its parent
  in the hierarchy, and is flagged;
- a line mixing Chinese and Latin text is flagged whatever mapped it, because `fold` reads only the Latin part;
- anything else is unmatched. It keeps its suggestions for the review list and its grams count against coverage.

Coverage is per dish (02-baselines.md section 3.2 item 3): a dish is verifiable when at least 90% of its grams
map. The plan-wide figure is reported too, but never decides a dish.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.agent.ingredient_matcher import IngredientMatcher, fold, spelling_score
from app.evaluation.baseline_output import BaselineResponse

MappingStatus = Literal["matched", "needs_review", "unmatched"]
MappingMethod = Literal["id", "name", "alias", "similarity", "hierarchy"]

# Spelling similarity a line must reach to map without an exact name. 0.85 takes plurals and small typos
# ("tomatoes", "chilies") and refuses neighbours ("brown sugar" / "brown rice"). Set on the developer
# examples in the tests, never on held-out lines.
SIMILARITY_FLOOR = 0.85
_CJK = re.compile(r"[㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class IngredientMapping:
    original_name: str
    quantity_g: float
    ingredient_id: str | None
    status: MappingStatus
    method: MappingMethod | None = None
    needs_review: bool = False
    suggestions: tuple[str, ...] = ()
    review_reasons: tuple[str, ...] = ()

    @property
    def mapped(self) -> bool:
        return self.ingredient_id is not None


@dataclass(frozen=True)
class DishCoverage:
    slot_id: str
    role_id: str | None
    name: str
    servings: float
    cooking_time_minutes: int
    mappings: tuple[IngredientMapping, ...]

    @property
    def total_grams(self) -> float:
        return sum(item.quantity_g for item in self.mappings)

    @property
    def mapped_grams(self) -> float:
        return sum(item.quantity_g for item in self.mappings if item.mapped)

    @property
    def coverage(self) -> float:
        return self.mapped_grams / self.total_grams if self.total_grams else 0.0


@dataclass(frozen=True)
class PlanCoverage:
    dishes: tuple[DishCoverage, ...]

    @property
    def mappings(self) -> tuple[IngredientMapping, ...]:
        return tuple(item for dish in self.dishes for item in dish.mappings)

    @property
    def total_grams(self) -> float:
        return sum(dish.total_grams for dish in self.dishes)

    @property
    def mapped_grams(self) -> float:
        return sum(dish.mapped_grams for dish in self.dishes)

    @property
    def coverage(self) -> float:
        return self.mapped_grams / self.total_grams if self.total_grams else 0.0

    def only(self, dishes: Iterable[DishCoverage]) -> PlanCoverage:
        return PlanCoverage(tuple(dishes))


@dataclass(frozen=True)
class _Index:
    names: dict[str, str]
    by_name: dict[str, set[str]]
    by_alias: dict[str, set[str]]


def _index(names: dict[str, str], aliases: dict[str, list[str]]) -> _Index:
    by_name: dict[str, set[str]] = {}
    by_alias: dict[str, set[str]] = {}
    for ingredient_id, display_name in names.items():
        for word in {fold(ingredient_id), fold(display_name)}:
            by_name.setdefault(word, set()).add(ingredient_id)
        for alias in aliases.get(ingredient_id, []):
            by_alias.setdefault(fold(alias), set()).add(ingredient_id)
    return _Index(names, by_name, by_alias)


def _parent(query: str, index: _Index) -> str | None:
    """The catalog ingredient a longer line names a kind of: the longest whole-word run that is a catalog name."""
    words = query.split()
    for size in range(len(words) - 1, 0, -1):
        for start in range(len(words) - size + 1):
            run = " ".join(words[start : start + size])
            for candidate in (run, run.removesuffix("es"), run.removesuffix("s")):
                ids = index.by_name.get(candidate, set())
                if len(ids) == 1:
                    return next(iter(ids))
    # ponytail: Chinese text has no word breaks, so it gets no parent step; add a segmenter if Chinese lines
    # turn up unmatched in the review list.
    return None


def _map_line(name: str, grams: float, suggested: list[str], index: _Index, floor: float) -> IngredientMapping:
    query = fold(name)
    reasons: list[str] = []
    if _CJK.search(name) and _LATIN.search(name):
        reasons.append("mixes Chinese and Latin text; only the Latin part was matched")

    def mapped(ingredient_id: str, method: MappingMethod, reason: str | None = None) -> IngredientMapping:
        flags = [*reasons, reason] if reason else reasons
        return IngredientMapping(
            name,
            grams,
            ingredient_id,
            "needs_review" if flags else "matched",
            method,
            bool(flags),
            tuple(suggested),
            tuple(flags),
        )

    exact = index.by_name.get(query, set())
    if len(exact) == 1:
        ingredient_id = next(iter(exact))
        return mapped(ingredient_id, "id" if fold(ingredient_id) == query else "name")
    alias = index.by_alias.get(query, set())
    if not exact and len(alias) == 1:
        return mapped(next(iter(alias)), "alias", "matched through an unreviewed other name alone")
    if len(exact | alias) > 1:
        return IngredientMapping(
            name,
            grams,
            None,
            "unmatched",
            suggestions=tuple(sorted(exact | alias)),
            review_reasons=(*reasons, "several catalog ingredients share this name"),
        )

    scored = [
        (max(spelling_score(name, index.names[c]), spelling_score(name, c)), c) for c in suggested if c in index.names
    ]
    score, best = max(scored, default=(0.0, None))
    if best is not None and score >= floor:
        return mapped(best, "similarity", f"spelling similarity {score:.2f}")
    parent = _parent(query, index)
    if parent is not None:
        return mapped(parent, "hierarchy", f"names a kind of {parent}")
    return IngredientMapping(
        name,
        grams,
        None,
        "unmatched",
        suggestions=tuple(suggested),
        review_reasons=(*reasons, "no catalog ingredient above the similarity floor or as a parent"),
    )


def map_lines(
    lines: list[tuple[str, float]],
    *,
    names: dict[str, str],
    aliases: dict[str, list[str]],
    matcher: IngredientMatcher,
    floor: float = SIMILARITY_FLOOR,
) -> list[IngredientMapping]:
    """Map every line in one matcher call (`suggest_all`: one embedding request, however many lines)."""
    index = _index(names, aliases)
    suggestions = matcher.suggest_all([name for name, _ in lines]) if lines else {}
    return [_map_line(name, grams, suggestions.get(name, []), index, floor) for name, grams in lines]


def map_ingredient(
    name: str,
    quantity_g: float,
    *,
    names: dict[str, str],
    aliases: dict[str, list[str]],
    matcher: IngredientMatcher,
    floor: float = SIMILARITY_FLOOR,
) -> IngredientMapping:
    return map_lines([(name, quantity_g)], names=names, aliases=aliases, matcher=matcher, floor=floor)[0]


def map_response_ingredients(
    response: BaselineResponse,
    *,
    names: dict[str, str],
    aliases: dict[str, list[str]],
    matcher: IngredientMatcher,
    floor: float = SIMILARITY_FLOOR,
) -> PlanCoverage:
    if response.plan is None:
        return PlanCoverage(())
    dishes = [(meal.slot_id, dish) for meal in response.plan.meals for dish in meal.dishes]
    lines = [(item.name, item.quantity_g) for _, dish in dishes for item in dish.ingredients]
    mappings = iter(map_lines(lines, names=names, aliases=aliases, matcher=matcher, floor=floor))
    return PlanCoverage(
        tuple(
            DishCoverage(
                slot_id=slot_id,
                role_id=dish.role_id,
                name=dish.name,
                servings=dish.servings,
                cooking_time_minutes=dish.cooking_time_minutes,
                mappings=tuple(next(mappings) for _ in dish.ingredients),
            )
            for slot_id, dish in dishes
        )
    )
