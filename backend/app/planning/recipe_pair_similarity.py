"""Offline recipe-to-recipe signals; no model calls and no eligibility decisions.

Keep the three signals separate until a developer-calibrated policy defines near
duplicates. The request-to-recipe matcher serves a different purpose.
"""

import re
from dataclasses import dataclass
from math import sqrt

from app.models.recipe import Recipe
from app.planning import recipe_similarity
from app.planning.recipe_quality import dish_family


@dataclass(frozen=True)
class RecipePairSignals:
    title_overlap: float | None
    ingredient_overlap: float | None
    vector_cosine: float | None
    vector_status: str
    shared_preparation: str | None = None


@dataclass(frozen=True)
class _Features:
    title_words: frozenset[str]
    ingredients: frozenset[str]
    vector: tuple[float, ...] | None
    preparation: str | None


def _preparation(title: str) -> str | None:
    words = re.sub(r"[^a-z]+", " ", title.lower()).split()
    # A named fried-rice preparation, not a soup/cake containing fried rice.
    if "fried rice" in " ".join(words) and not set(words) & {
        "soup",
        "salad",
        "cake",
        "cakes",
        "balls",
        "parcels",
        "stuffed",
    }:
        return "fried_rice"
    return None


def _overlap(left: frozenset[str], right: frozenset[str]) -> float | None:
    # Empty evidence is unknown, including the tempting empty == empty case.
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


class RecipePairIndex:
    """Prepare only the supplied candidate pool, once, then compare stable recipe keys.

    Ingredient overlap uses canonical normalized names, deduplicated per recipe;
    it does not infer ingredient equivalence or safety. Quantized vectors are
    renormalized before comparing them. Missing or damaged vectors stay unknown.
    """

    def __init__(self, recipes: list[Recipe]) -> None:
        catalog = recipe_similarity._catalog()
        self.vector_source: dict | None = None
        self._catalog_status = "catalog_missing"
        vectors, rows, size = {}, b"", 0
        if catalog is not None:
            meta, vectors, rows = catalog
            size = meta.get("dimensions", 0)
            keys = meta.get("keys", [])
            valid = type(size) is int and size > 0 and len(keys) == len(vectors) and len(rows) == len(keys) * size
            self._catalog_status = "available" if valid else "catalog_invalid"
            self.vector_source = {
                "model": meta.get("model"),
                "dimensions": size,
                "texts_sha256": meta.get("texts_sha256"),
            }
        self._features: dict[str, _Features] = {}
        for recipe in recipes:
            key = recipe_similarity.recipe_key(recipe)
            if key in self._features:
                raise ValueError(f"Duplicate recipe key: {key}")
            vector = None
            if self._catalog_status == "available" and key in vectors:
                offset = vectors[key] * size
                row = tuple(b - 256 if b > 127 else b for b in rows[offset : offset + size])
                norm = sqrt(sum(value * value for value in row))
                if norm:
                    vector = tuple(value / norm for value in row)
            self._features[key] = _Features(
                frozenset(dish_family(recipe.title).split()) if recipe.title.strip() else frozenset(),
                frozenset(
                    line.ingredient.normalized_name
                    for line in recipe.recipe_ingredients
                    if line.ingredient.normalized_name
                ),
                vector,
                _preparation(recipe.title),
            )

    def compare(self, left_key: str, right_key: str) -> RecipePairSignals:
        left, right = self._features[left_key], self._features[right_key]
        cosine = None
        status = self._catalog_status
        if status == "available":
            if left.vector is None or right.vector is None:
                status = "recipe_vector_missing_or_zero"
            else:
                cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(left.vector, right.vector, strict=True))))
        return RecipePairSignals(
            _overlap(left.title_words, right.title_words),
            _overlap(left.ingredients, right.ingredients),
            cosine,
            status,
            left.preparation if left.preparation == right.preparation else None,
        )
