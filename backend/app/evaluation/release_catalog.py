"""Release v2.1 as the frozen facts of protocol v2-multidish (docs/evaluation/protocol-v2-multidish.md).

The v2 scorer and packets read the curated catalog's row shape. This projects
release recipes, their ingredients and the FairPrice v2 mapping into that
shape. Quantities are the release's per-line grams; products are sold in
package grams. Only a recipe whose every purchased ingredient has a product is
eligible, as in the product, and only one a planning candidate can hold (1-24
servings, at most 12 hours).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.paths import repository_root
from app.data.release_v2 import map_allergens

RELEASE = Path("data-engineering/data/release/v2.1")
SNAPSHOT = Path("data/products/fairprice-v2-snapshot.json")
NOT_PURCHASED = {"water", "ice"}


def ingredient_key(canonical_ingredient_id: str) -> str:
    """`ING_BROWN_RICE` -> `brown_rice`, the key the product mapping uses."""
    return canonical_ingredient_id.removeprefix("ING_").lower()


@dataclass(frozen=True)
class ReleaseCatalog:
    recipes: list[dict]
    products: list[dict]
    ingredients: list[dict]

    @property
    def by_slug(self) -> dict[str, dict]:
        return {row["slug"]: row for row in self.recipes}


@lru_cache(maxsize=1)
def load_release_catalog(root: Path | None = None) -> ReleaseCatalog:
    root = root or repository_root()
    snapshot = json.loads((root / SNAPSHOT).read_text(encoding="utf-8"))["ingredients"]
    products, priced = [], set()
    seen: dict[str, str] = {}
    for key, entry in sorted(snapshot.items()):
        if entry["status"] != "mapped":
            continue
        # An out-of-stock product prices nothing: the product path never buys one.
        for product in [p for p in entry.get("products") or [] if p.get("in_stock", True)]:
            # One product bought for two ingredients is a separate purchase for each.
            product_id = product["external_id"]
            if seen.setdefault(product_id, key) != key:
                product_id = f"{product_id}@{key}"
            products.append(
                {
                    "external_id": product_id,
                    "ingredient_id": key,
                    "name": product["name"],
                    "package_size": float(product["package_grams"]),
                    "package_unit": "g",
                    "price_sgd": float(product["price_sgd"]),
                    "in_stock": bool(product.get("in_stock", True)),
                }
            )
            priced.add(key)

    ingredients = []
    for line in (root / RELEASE / "ingredients.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ingredients.append(
            {"normalized_name": ingredient_key(row["ingredient_id"]), "allergens": map_allergens(row["allergens"])}
        )

    recipes = []
    for line in (root / RELEASE / "recipes.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        lines = [
            {
                "ingredient": ingredient_key(item["canonical_ingredient_id"]),
                "quantity": float(item["grams"]),
                "unit": "g",
            }
            for item in record["ingredients"]
            if ingredient_key(item["canonical_ingredient_id"]) not in NOT_PURCHASED
        ]
        if not lines or any(item["ingredient"] not in priced for item in lines):
            continue
        # A planning candidate serves 1-24 and cooks within 12 hours; batch bakes of 48 are not dinners.
        if not 1 <= int(record["servings"]) <= 24 or record["prep_minutes"] + record["cook_minutes"] > 720:
            continue
        recipes.append(
            {
                "slug": record["recipe_id"],
                "title": record["title"],
                "course": record["course"],
                "meal_types": record["meal_types"],
                "cuisine": record["cuisine"],
                "servings": int(record["servings"]),
                # The product's cooking time is prep + cook; passive time is not cooking time.
                "prep_time_minutes": int(record["prep_minutes"]),
                "cook_time_minutes": int(record["cook_minutes"]),
                "dietary_tags": list(record["dietary_tags"]),
                # A zero-gram line ("1/8 teaspoon dill weed" rounded to 0 g) stays here: it
                # counts for eligibility and for the pool's products, but buys nothing.
                "ingredients": lines,
                "nutrition": None,  # not computed in the release (protocol section 2)
            }
        )
    return ReleaseCatalog(recipes, products, ingredients)
