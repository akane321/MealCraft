"""The frozen facts every ingredient-level baseline is scored on (02-baselines.md sections 3.1 and 4).

- Names, nutrition and allergens: release v2.2 `ingredients.jsonl` (the frozen data version; v2.1 until
  2026-10-23), with the curated catalog's allergen lists (`data/ingredients/ingredients.json`) added for the ids
  both hold, as the product's import does: an allergen list only ever grows.
- Hierarchy step: the `same` and `variety` links of `data/ingredients/hierarchy` whose parent the release names.
- Allergen vocabulary: `checked_allergens()` (`data/ingredients/allergen-vocabulary.json`). An allergen outside
  it is unverifiable for every ingredient (`app.data.allergens`).
- Prices: the frozen FairPrice v2 snapshot through `load_release_catalog`, whole packages only.
- Not bought: water and ice always; the basic seasonings (`data/ingredients/basic-seasonings-v1.json`) unless
  the household lists them as missing or excludes them. They still count for every safety check.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases
from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.data.household_reference import basic_seasonings
from app.data.ingredient_hierarchy import read_links
from app.data.release_v2 import map_allergens
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.release_catalog import CURATED, NOT_PURCHASED, SNAPSHOT, load_release_catalog
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

# The frozen data version the baselines and the product are scored on (02-baselines.md section 4); a change is
# logged in the Knowledge baseline freeze log (operations/sprint2-plan/02-baselines-freeze-log.md).
RELEASE = Path("data-engineering/data/release/v2.2")
RELEASE_INGREDIENTS = RELEASE / "ingredients.jsonl"
RELEASE_MANIFEST = RELEASE / "release_manifest.json"


@dataclass(frozen=True)
class BaselineResources:
    names: dict[str, str]
    aliases: dict[str, list[str]]
    matcher: IngredientMatcher
    ingredient_facts: dict[str, IngredientEvaluationFacts]
    frozen_products: list[PlanningProductOption]
    not_purchased: frozenset[str]
    checked_allergens: frozenset[str] = frozenset()
    basic_seasonings: frozenset[str] = frozenset()
    parents: dict[str, str] = field(default_factory=dict)
    # Snapshot ingredient keys the release names nothing for: priced, but no line can ever map to them.
    unnamed_product_ingredients: tuple[str, ...] = ()
    release_version: str | None = None
    data_digests: tuple[tuple[str, str], ...] = ()

    def not_bought(self, household: dict) -> frozenset[str]:
        """Water, ice and the basics this household is taken to have (`app.planning.household_slots`)."""
        keep = {*(household.get("missing_basics") or []), *(household.get("excluded_ingredients") or [])}
        return self.not_purchased | (self.basic_seasonings - keep)


def load_resources(root: Path | None = None) -> BaselineResources:
    root = root or repository_root()
    release = load_release_catalog(root, RELEASE)
    names = {row["normalized_name"]: row["display_name"] for row in release.ingredients}
    aliases = {key: values for key, values in catalog_aliases().items() if key in names}
    products = [
        PlanningProductOption(
            ingredient_id=row["ingredient_id"],
            product_id=row["external_id"],
            package_quantity=row["package_size"],
            package_unit=row["package_unit"],
            price_sgd=row["price_sgd"],
            available=row["in_stock"],
        )
        for row in release.products
    ]
    manifest = json.loads((root / RELEASE_MANIFEST).read_text(encoding="utf-8"))
    return BaselineResources(
        names=names,
        aliases=aliases,
        matcher=IngredientMatcher(names, aliases=aliases, mode="spelling"),
        ingredient_facts=_ingredient_facts(root),
        frozen_products=products,
        not_purchased=frozenset(NOT_PURCHASED),
        checked_allergens=checked_allergens(),
        basic_seasonings=frozenset(basic_seasonings()),
        parents=hierarchy_parents(names, root),
        unnamed_product_ingredients=tuple(sorted({p.ingredient_id for p in products} - set(names))),
        release_version=manifest.get("release_version"),
        data_digests=tuple(
            (str(path), hashlib.sha256((root / path).read_bytes()).hexdigest())
            for path in (RELEASE_INGREDIENTS, RELEASE_MANIFEST, SNAPSHOT, CURATED)
        ),
    )


def hierarchy_parents(names: dict[str, str], root: Path | None = None) -> dict[str, str]:
    """Hierarchy id -> the one release id it is (`same`) or is a kind of (`variety`); ids with several are left out."""
    parents: dict[str, str] = {}
    for child, entry in read_links(root).entries.items():
        if child in names:
            continue
        ups = {link["id"] for link in entry.get("parents", []) if link["relation"] in {"same", "variety"}} & set(names)
        if len(ups) == 1:
            parents[child] = ups.pop()
    return parents


def _ingredient_facts(root: Path) -> dict[str, IngredientEvaluationFacts]:
    curated = {
        row["normalized_name"]: set(row["allergens"])
        for row in json.loads((root / CURATED).read_text(encoding="utf-8"))
    }
    facts: dict[str, IngredientEvaluationFacts] = {}
    for line in (root / RELEASE_INGREDIENTS).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ingredient_id = row["ingredient_id"].removeprefix("ING_").lower()
        form = (row.get("forms") or {}).get(row["ingredient_id"], {})
        nutrition = form.get("nutrition_per_100g")
        nutrients = None
        if nutrition is not None:
            nutrients = PlanningNutrients(
                calories_kcal=nutrition["energy_kcal"],
                protein_g=nutrition["protein_g"],
                carbohydrate_g=nutrition["carbohydrate_g"],
                fat_g=nutrition["fat_g"],
                sodium_mg=nutrition["sodium_mg"],
                sugar_g=nutrition["sugar_g"],
            )
        allergens = None
        if row.get("allergen_status") == "confirmed":
            allergens = tuple(sorted(set(map_allergens(row["allergens"])) | curated.get(ingredient_id, set())))
        facts[ingredient_id] = IngredientEvaluationFacts(allergens=allergens, nutrition_per_100g=nutrients)
    return facts
