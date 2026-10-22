from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.agent.ingredient_matcher import IngredientMatcher, fold
from app.evaluation.baseline_output import BaselineResponse

MappingStatus = Literal["matched", "needs_review", "unmatched"]


@dataclass(frozen=True)
class IngredientMapping:
    original_name: str
    quantity_g: float
    ingredient_id: str | None
    status: MappingStatus
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageResult:
    total_grams: float
    matched_grams: float
    coverage: float
    mappings: tuple[IngredientMapping, ...]


def map_ingredient(
    name: str,
    quantity_g: float,
    *,
    names: dict[str, str],
    aliases: dict[str, list[str]],
    matcher: IngredientMatcher,
) -> IngredientMapping:
    query = fold(name)

    # Exact catalog id / display name / alias can be accepted automatically.
    exact_matches: list[str] = []

    for ingredient_id, display_name in names.items():
        accepted_names = {
            fold(ingredient_id),
            fold(display_name),
            *(fold(alias) for alias in aliases.get(ingredient_id, [])),
        }
        if query in accepted_names:
            exact_matches.append(ingredient_id)

    if len(exact_matches) == 1:
        return IngredientMapping(
            original_name=name,
            quantity_g=quantity_g,
            ingredient_id=exact_matches[0],
            status="matched",
        )

    # Ambiguous or semantic matches must not be silently accepted.
    suggestions = tuple(matcher.suggest(name))

    if suggestions:
        return IngredientMapping(
            original_name=name,
            quantity_g=quantity_g,
            ingredient_id=None,
            status="needs_review",
            suggestions=suggestions,
        )

    return IngredientMapping(
        original_name=name,
        quantity_g=quantity_g,
        ingredient_id=None,
        status="unmatched",
    )


def map_response_ingredients(
    response: BaselineResponse,
    *,
    names: dict[str, str],
    aliases: dict[str, list[str]],
    matcher: IngredientMatcher,
) -> CoverageResult:
    mappings: list[IngredientMapping] = []

    if response.plan is not None:
        for meal in response.plan.meals:
            for dish in meal.dishes:
                for ingredient in dish.ingredients:
                    mappings.append(
                        map_ingredient(
                            ingredient.name,
                            ingredient.quantity_g,
                            names=names,
                            aliases=aliases,
                            matcher=matcher,
                        )
                    )

    total_grams = sum(item.quantity_g for item in mappings)

    matched_grams = sum(item.quantity_g for item in mappings if item.status == "matched")

    coverage = matched_grams / total_grams if total_grams else 0.0

    return CoverageResult(
        total_grams=total_grams,
        matched_grams=matched_grams,
        coverage=coverage,
        mappings=tuple(mappings),
    )
