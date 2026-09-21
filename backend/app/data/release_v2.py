"""Import data-engineering release v2 into the runtime catalog, next to the curated recipes.

The curated catalog (`data/recipes/recipes.json`, 30 recipes) stays as it is:
held-out episodes, planning fixtures and tests name its slugs. Release v2 recipes
are added beside it and carry `release_version = "v2"`, an `external_id` (the
release `recipe_id`) and a slug prefixed with `v2-`, so the two never collide.

What the mapping decides, and why:

- Allergens. The release uses its own names (`milk`, `eggs`, `crustaceans`, ...);
  the runtime vouches only for `data/ingredients/allergen-vocabulary.json`. Each
  release name maps to a runtime name. Molluscs map to `shellfish` and
  `gluten_candidate` to `gluten`, both erring towards exclusion. Sulfites have no
  runtime name; a request naming them is already unverifiable for every recipe,
  so dropping them loses nothing. An ingredient's list is the union of its
  release list and every line-level list seen for it, so no line can carry an
  allergen its ingredient does not.
- Quantities. Every release line has a gram weight, and the planner sums lines by
  (ingredient, unit). Lines are therefore stored as grams in `g`, with the source
  wording kept in `original_text`. Repeated ingredients in one recipe stay as
  separate lines; the planner adds them. A weight that rounds to 0 g (11 lines in
  v2, mostly dill) is stored as an unknown quantity rather than a false zero.
- Ingredients shared with the curated catalog (same normalized name) are reused,
  not duplicated. Their display name is left alone and their allergen list only
  ever grows.
- A recipe with fewer than two ingredient lines or no instruction is skipped,
  matching the curated catalog's own floor.

`catalog_imports` holds the digest of the release files. Importing a release whose
digest is already recorded does nothing, so the command is cheap to run at every
start.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.models.meal_plan import MealPlanEntry, MealPlanEvent
from app.models.recipe import CatalogImport, Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep

RELEASE_VERSION = "v2"
SLUG_PREFIX = "v2-"
RELEASE_FILES = ("release_manifest.json", "ingredients.jsonl", "recipes.jsonl")

# Importer logic is part of the digest, so a change here re-imports an
# already-recorded release instead of being skipped as unchanged.
IMPORTER_VERSION = "2"  # 2: incomplete-list check and stricter allergens

# Some RecipeNLG sources list only part of a dish ("Crab Meat Quiche" listing
# its crust), so allergens and dietary tags derived from the listed ingredients
# miss what the title or the steps name. A recipe whose title or steps name a
# food carrying an allergen that no listed ingredient carries is not imported:
# a wrong exclusion costs one recipe, a missed one serves an allergen unchecked.
# A vegetarian or vegan recipe whose text names meat or fish keeps its place but
# loses those tags. Phrases that only look like a trigger are removed first.
LOOKALIKES = re.compile(
    r"coconut (?:milk|cream)|peanut butter|cream of tartar|butternut|butter ?beans?|butterfly|"
    r"cream(?:ed|ing)? (?:together|the|until|in)|scallop(?:ed)? potato\w*|egg ?plant|nut ?meg|water ?chestnut|"
    r"imitation crab\w*|crab ?sticks?|spaghetti squash|"
    r"(?:rice|corn|almond|coconut|tapioca|potato|chickpea|gram|oat|millet|teff|sorghum|buckwheat) "
    r"(?:flour|noodles?|tortillas?|starch|milk|bread|cream)|cornflour|rice paper|gluten[- ]free \w+|"
    r"(?:dairy|egg|nut|soy)[- ]free \w+|soy ?milk|almond milk|oat milk|vegan \w+",
    re.IGNORECASE,
)
ALLERGEN_WORDS = {
    "shellfish": r"crab|shrimps?|prawns?|lobsters?|scallops?|clams?|mussels?|oysters?|squid|calamari|crawfish|octopus",
    "fish": r"salmon|tuna|cod|tilapia|anchov\w*|sardines?|halibut|trout|mackerel|catfish|haddock|snapper|fish",
    "egg": r"eggs?|yolks?|omelets?|omelettes?|quiche|frittata|meringue",
    "dairy": r"cheese|cheddar|parmesan|mozzarella|milk|butter|cream|yogh?urt|ricotta|feta",
    "peanut": r"peanuts?",
    "tree_nut": r"almonds?|walnuts?|pecans?|cashews?|pistachios?|hazelnuts?|macadamias?",
    "sesame": r"sesame|tahini",
    "soy": r"soy|soya|tofu|edamame|miso|tempeh",
    "gluten": r"flour|bread|breadcrumbs?|pasta|spaghetti|macaroni|noodles?|wheat|barley|rye|couscous|crackers?|"
    r"tortillas?|croutons?",
}
ALLERGEN_PATTERNS = {name: re.compile(rf"\b(?:{words})\b", re.IGNORECASE) for name, words in ALLERGEN_WORDS.items()}
MEAT = re.compile(
    r"\b(?:chicken|beef|pork|bacon|ham|sausages?|lamb|turkey|meat|steak|veal|duck|gelatin|anchov\w*|fish|"
    r"shrimps?|prawns?|crab|tuna|salmon)\b",
    re.IGNORECASE,
)
MEAT_FREE_TAGS = {"vegetarian", "vegan"}
# A dietary tag the recipe's own allergens contradict is dropped (kimchi's fish in a
# "vegetarian" fried rice). Tags are derived by rule, so a contradiction is a gap.
TAG_CONTRADICTED_BY = {
    "vegetarian": {"fish", "shellfish"},
    "vegan": {"fish", "shellfish", "dairy", "egg"},
    "dairy-free": {"dairy"},
    "gluten-free": {"gluten"},
}

# Release v2 ingredients whose rule-derived allergens miss what the usual product
# carries. Added here, only ever stricter, until a release carries them itself.
STRICTER_ALLERGENS = {
    "ING_BUTTER_OR_MARGARINE": ("milk",),
    "ING_CELERY_SOUP": ("milk", "gluten_candidate"),
    "ING_CHICKEN_SOUP": ("milk", "gluten_candidate"),
    "ING_MUSHROOM_SOUP": ("milk", "gluten_candidate"),
    "ING_TORTILLA": ("gluten_candidate",),
    "ING_CEREAL_RICE": ("gluten_candidate",),
}


def recipe_allergens(record: dict) -> list[str]:
    stricter = [
        a for item in record["ingredients"] for a in STRICTER_ALLERGENS.get(item["canonical_ingredient_id"], ())
    ]
    return map_allergens([*record["allergens"], *stricter])


def unlisted_allergens(record: dict, listed: Iterable[str]) -> list[str]:
    """Checked allergens the title or steps name that no listed ingredient carries."""
    text = LOOKALIKES.sub(" ", " ".join([record["title"], *(step["text"] for step in record["instructions"])]))
    have = set(listed)
    return sorted(name for name, pattern in ALLERGEN_PATTERNS.items() if name not in have and pattern.search(text))


def names_meat(record: dict) -> bool:
    text = LOOKALIKES.sub(" ", " ".join([record["title"], *(step["text"] for step in record["instructions"])]))
    return bool(MEAT.search(text))


# Release allergen name -> runtime checked allergen, or None when the runtime has no name for it.
ALLERGEN_MAP: dict[str, str | None] = {
    "milk": "dairy",
    "eggs": "egg",
    "fish": "fish",
    "gluten": "gluten",
    "gluten_candidate": "gluten",
    "peanuts": "peanut",
    "sesame": "sesame",
    "crustaceans": "shellfish",
    "molluscs": "shellfish",
    "soy": "soy",
    "tree_nuts": "tree_nut",
    "sulfites": None,
}

CHUNK = 500


def release_dir() -> Path:
    return repository_root() / "data-engineering" / "data" / "release" / RELEASE_VERSION


def release_digest(directory: Path) -> str:
    digest = hashlib.sha256(f"importer:{IMPORTER_VERSION}".encode())
    for name in RELEASE_FILES:
        digest.update(name.encode())
        digest.update((directory / name).read_bytes())
    return digest.hexdigest()


def map_allergens(values: Iterable[str]) -> list[str]:
    mapped = set()
    for value in values:
        if value not in ALLERGEN_MAP:
            raise ValueError(f"release allergen with no runtime mapping: {value}")
        target = ALLERGEN_MAP[value]
        if target is not None:
            mapped.add(target)
    unchecked = mapped.difference(checked_allergens())
    if unchecked:
        raise ValueError(f"mapped allergens outside the checked vocabulary: {sorted(unchecked)}")
    return sorted(mapped)


def normalized_name(ingredient_id: str) -> str:
    if not ingredient_id.startswith("ING_"):
        raise ValueError(f"unexpected release ingredient id: {ingredient_id}")
    return ingredient_id[4:].lower()


def recipe_slug(recipe_id: str, title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:100].strip("-") or "recipe"
    return f"{SLUG_PREFIX}{words}-{recipe_id.split('_', 1)[-1].lower()}"


def _jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


@dataclass
class ImportReport:
    release_version: str
    digest: str
    skipped_unchanged: bool = False
    ingredients_added: int = 0
    ingredients_reused: int = 0
    recipes_imported: int = 0
    recipes_skipped: list[str] = field(default_factory=list)
    recipes_incomplete: dict[str, list[str]] = field(default_factory=dict)
    meat_free_tags_removed: list[str] = field(default_factory=list)
    recipes_removed: int = 0
    recipes_retained_in_use: int = 0

    def summary(self) -> str:
        if self.skipped_unchanged:
            return f"Release {self.release_version} already imported (digest {self.digest[:12]}); nothing to do"
        return (
            f"Release {self.release_version} imported: {self.recipes_imported} recipes, "
            f"{self.ingredients_added} new ingredients, {self.ingredients_reused} already in the catalog, "
            f"{len(self.recipes_skipped)} recipes skipped, "
            f"{len(self.recipes_incomplete)} left out because their text names an unlisted allergen, "
            f"{len(self.meat_free_tags_removed)} lost vegetarian/vegan tags, "
            f"{self.recipes_removed} stale recipes removed, "
            f"{self.recipes_retained_in_use} stale recipes kept because a meal plan uses them"
        )


def import_release_v2(session: Session, directory: Path | None = None, *, force: bool = False) -> ImportReport:
    directory = directory or release_dir()
    manifest = json.loads((directory / "release_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("release_version") != RELEASE_VERSION:
        raise ValueError(f"expected release {RELEASE_VERSION}, found {manifest.get('release_version')}")
    report = ImportReport(release_version=RELEASE_VERSION, digest=release_digest(directory))

    recorded = session.get(CatalogImport, RELEASE_VERSION)
    if recorded is not None and recorded.digest == report.digest and not force:
        report.skipped_unchanged = True
        return report

    recipes = list(_jsonl(directory / "recipes.jsonl"))
    ingredient_ids = _import_ingredients(session, directory, recipes, report)
    _import_recipes(session, recipes, ingredient_ids, report)

    # _import_recipes expunges the session between chunks, so fetch the row again.
    recorded = session.get(CatalogImport, RELEASE_VERSION)
    if recorded is None:
        recorded = CatalogImport(release_version=RELEASE_VERSION)
        session.add(recorded)
    recorded.digest = report.digest
    recorded.recipe_count = report.recipes_imported
    recorded.ingredient_count = report.ingredients_added + report.ingredients_reused
    session.commit()
    return report


def _import_ingredients(session: Session, directory: Path, recipes: list[dict], report: ImportReport) -> dict[str, int]:
    line_allergens: dict[str, set[str]] = {}
    for recipe in recipes:
        for line in recipe["ingredients"]:
            line_allergens.setdefault(line["canonical_ingredient_id"], set()).update(line["allergens"])

    existing = {row.normalized_name: row for row in session.scalars(select(Ingredient))}
    rows: dict[str, Ingredient] = {}
    for record in _jsonl(directory / "ingredients.jsonl"):
        release_id = record["ingredient_id"]
        name = normalized_name(release_id)
        allergens = map_allergens(
            [*record["allergens"], *line_allergens.get(release_id, ()), *STRICTER_ALLERGENS.get(release_id, ())]
        )
        row = existing.get(name)
        if row is None:
            row = Ingredient(normalized_name=name, display_name=record["canonical_name"][:160], allergens=allergens)
            session.add(row)
            report.ingredients_added += 1
        else:
            row.allergens = sorted(set(row.allergens or []).union(allergens))
            report.ingredients_reused += 1
        rows[release_id] = row

    missing = sorted(set(line_allergens).difference(rows))
    if missing:
        raise ValueError(f"recipe lines reference ingredients absent from the release: {missing[:5]}")
    session.flush()
    return {release_id: row.id for release_id, row in rows.items()}


def _import_recipes(
    session: Session, recipes: list[dict], ingredient_ids: dict[str, int], report: ImportReport
) -> None:
    kept_ids: set[str] = set()
    existing_ids = dict(
        session.execute(select(Recipe.external_id, Recipe.id).where(Recipe.release_version == RELEASE_VERSION)).all()
    )
    for start in range(0, len(recipes), CHUNK):
        for record in recipes[start : start + CHUNK]:
            steps = [step["text"].strip() for step in record["instructions"] if step["text"].strip()]
            if len(record["ingredients"]) < 2 or not steps:
                report.recipes_skipped.append(record["recipe_id"])
                continue
            missing = unlisted_allergens(record, recipe_allergens(record))
            if missing:
                report.recipes_incomplete[record["recipe_id"]] = missing
                continue
            recipe_id = existing_ids.get(record["recipe_id"])
            if recipe_id is not None:
                session.execute(delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id))
                session.execute(delete(RecipeStep).where(RecipeStep.recipe_id == recipe_id))
                recipe = session.get(Recipe, recipe_id)
            else:
                recipe = Recipe(external_id=record["recipe_id"], release_version=RELEASE_VERSION)
                session.add(recipe)
            _fill_recipe(recipe, record, report)
            recipe.recipe_ingredients = [
                RecipeIngredient(
                    ingredient_id=ingredient_ids[line["canonical_ingredient_id"]],
                    quantity=_grams(line),
                    unit="g" if _grams(line) else None,
                    grams=_grams(line),
                    preparation="; ".join(line["preparation"])[:160] or None,
                    original_text=line["original_text"],
                    sort_order=index,
                )
                for index, line in enumerate(record["ingredients"], start=1)
            ]
            recipe.steps = [
                RecipeStep(step_number=index, instruction=text) for index, text in enumerate(steps, start=1)
            ]
            kept_ids.add(record["recipe_id"])
            report.recipes_imported += 1
        session.flush()
        session.expunge_all()

    stale = {external_id: pk for external_id, pk in existing_ids.items() if external_id not in kept_ids}
    if stale:
        in_use = set(
            session.scalars(select(MealPlanEntry.recipe_id).where(MealPlanEntry.recipe_id.in_(stale.values())))
        ) | set(
            session.scalars(
                select(MealPlanEvent.proposed_recipe_id).where(MealPlanEvent.proposed_recipe_id.in_(stale.values()))
            )
        )
        removable = [pk for pk in stale.values() if pk not in in_use]
        if removable:
            session.execute(delete(RecipeIngredient).where(RecipeIngredient.recipe_id.in_(removable)))
            session.execute(delete(RecipeStep).where(RecipeStep.recipe_id.in_(removable)))
            session.execute(delete(RecipeNutrition).where(RecipeNutrition.recipe_id.in_(removable)))
            session.execute(delete(Recipe).where(Recipe.id.in_(removable)))
        report.recipes_removed = len(removable)
        report.recipes_retained_in_use = len(stale) - len(removable)


def _grams(line: dict) -> Decimal | None:
    """The line's weight at the column's precision; a weight that rounds to zero is stored as unknown."""
    grams = round(Decimal(str(line["grams"])), 2)
    return grams if grams > 0 else None


def _fill_recipe(recipe: Recipe, record: dict, report: ImportReport) -> None:
    nutrition = record["nutrition"]
    source = record["source"]
    recipe.slug = recipe_slug(record["recipe_id"], record["title"])
    recipe.title = record["title"][:200]
    recipe.description = (
        f"{record['cuisine'].replace('_', ' ').title()} {record['course'].replace('_', ' ')} from {source['dataset']}."
    )
    recipe.cuisine = record["cuisine"]
    recipe.meal_type = record["course"]
    recipe.course = record["course"]
    recipe.meal_types = list(record["meal_types"])
    recipe.difficulty = record["difficulty"]
    recipe.servings = int(record["servings"])
    recipe.servings_basis = record["servings_basis"]
    recipe.prep_time_minutes = int(record["prep_minutes"])
    recipe.cook_time_minutes = int(record["cook_minutes"])
    recipe.passive_time_minutes = int(record["passive_minutes"])
    recipe.time_basis = record["time_basis"]
    allergens = set(recipe_allergens(record))
    meat = names_meat(record)
    tags = [
        tag
        for tag in record["dietary_tags"]
        if not (allergens & TAG_CONTRADICTED_BY.get(tag, set())) and not (meat and tag in MEAT_FREE_TAGS)
    ]
    if MEAT_FREE_TAGS & set(record["dietary_tags"]) - set(tags):
        report.meat_free_tags_removed.append(record["recipe_id"])
    recipe.dietary_tags = tags
    recipe.allergens = recipe_allergens(record)
    recipe.source = {
        "dataset": source["dataset"],
        "source_id": source["source_id"],
        "source_url": source["source_url"],
        "license": source["license"],
    }
    recipe.video_url = record.get("video_url")
    if recipe.nutrition is None:
        recipe.nutrition = RecipeNutrition()
    recipe.nutrition.calories_kcal = nutrition["energy_kcal"]
    recipe.nutrition.protein_g = nutrition["protein_g"]
    recipe.nutrition.carbohydrate_g = nutrition["carbohydrate_g"]
    recipe.nutrition.fat_g = nutrition["fat_g"]
    recipe.nutrition.sodium_mg = nutrition["sodium_mg"]
    recipe.nutrition.sugar_g = nutrition["sugar_g"]
