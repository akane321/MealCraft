"""Why catalog recipes do or do not reach the planner: the planning-pool report of a release (03 plan section 2.2).

    uv run --project backend python -m app.data.planning_pool      # from the repository root, offline

Loads the committed catalog and release into an in-memory database, as the product import does, and follows
every recipe through the planning pool's gates (`RecipeRepository._load_for_planning`) and then the structured
planner's role gate (`meal_composition.meal_role_of`). Each excluded recipe is counted once, under the first gate it
fails. Writes `data-engineering/docs/planning-pool-report.md` and `.json`; both are generated, do not edit them.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.release_v2 import RELEASE_VERSION, import_release_v2, release_digest, release_dir
from app.data.tag_files import RECIPE_TAGS
from app.db.base import Base
from app.models.recipe import Recipe, RecipeIngredient
from app.planning.grocery_estimator import priceable_ingredients
from app.planning.meal_composition import meal_role_of, unreviewed
from app.planning.recipe_quality import incomplete
from app.repositories.recipe import POOL_COURSES, withdrawn_slugs
from app.schemas.planning_v2 import NON_MEAL_ROLES

REPORT = "data-engineering/docs/planning-pool-report.md"
# How many of the most used unpriced ingredients a "price the top N" line assumes priced.
TOP_UNPRICED = (10, 20, 40)
LISTED_UNPRICED = 20

COURSE = "course is not a dish course"
UNPRICED = "an ingredient has no price"
WITHDRAWN = "withdrawn"
INCOMPLETE = "incomplete recipe"
GATES = (COURSE, UNPRICED, WITHDRAWN, INCOMPLETE)

NO_ROLE = "no meal-role tag"
WAITS = "meal-role tags wait for review"
NO_SOURCE = "main with unknown protein source"


def unpriced(recipe: Recipe, priceable: frozenset[str]) -> list[str]:
    """A release recipe's ingredients the estimator cannot price; a curated recipe is never priced out."""
    if recipe.release_version is None:
        return []
    return sorted({line.ingredient.normalized_name for line in recipe.recipe_ingredients} - priceable)


def pool_gate(recipe: Recipe, priceable: frozenset[str], withdrawn: frozenset[str]) -> str | None:
    """The first planning-pool gate the recipe fails, in `_load_for_planning`'s terms, or None when it is in the
    pool. The pool's courses are every dish course (`POOL_COURSES`), as the planner's cached pool loads them."""
    if recipe.course is not None and recipe.course not in POOL_COURSES:
        return COURSE
    if unpriced(recipe, priceable):
        return UNPRICED
    if recipe.slug in withdrawn or recipe.withdrawn_at is not None:
        return WITHDRAWN
    if incomplete(recipe) is not None:
        return INCOMPLETE
    return None


def role_gate(recipe: Recipe) -> str | None:
    """Why a pool recipe fills no lunch or dinner role of the structured planner, or None when it does."""
    role = meal_role_of(recipe)
    if role is None:
        if recipe.meal_role is None:
            return NO_ROLE
        return WAITS if unreviewed(recipe) else NO_SOURCE
    return f"not a lunch or dinner role ({role})" if role in NON_MEAL_ROLES else None


def incomplete_reason(why: str) -> str:
    if why.startswith("named "):
        return "named meat missing"
    return "too few kcal for a main" if "kcal" in why else why


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report(recipes: list[Recipe], *, priceable: frozenset[str], withdrawn: frozenset[str]) -> dict:
    """The counts of the report for shared catalog recipes (household recipes are left out)."""
    shared = [recipe for recipe in recipes if recipe.owner_household_id is None]
    excluded: dict[str, Counter] = {"release": Counter(), "curated": Counter()}
    incomplete_detail, usable, not_usable = Counter(), Counter(), Counter()
    missing_sets: list[list[str]] = []
    pool = {"release": 0, "curated": 0}
    for recipe in shared:
        part = "curated" if recipe.release_version is None else "release"
        gate = pool_gate(recipe, priceable, withdrawn)
        if gate is not None:
            excluded[part][gate] += 1
            if gate == UNPRICED:
                missing_sets.append(unpriced(recipe, priceable))
            elif gate == INCOMPLETE:
                incomplete_detail[incomplete_reason(incomplete(recipe))] += 1
            continue
        pool[part] += 1
        why = role_gate(recipe)
        if why is None:
            usable[meal_role_of(recipe)] += 1
        else:
            not_usable[why] += 1
    uses = Counter(name for names in missing_sets for name in names)
    ranked = [name for name, _ in sorted(uses.items(), key=lambda item: (-item[1], item[0]))]
    recovered = {
        str(n): sum(1 for names in missing_sets if set(names) <= set(ranked[:n]))
        for n in TOP_UNPRICED
        if n < len(ranked)
    }
    recovered["all"] = len(missing_sets)
    alone = Counter(names[0] for names in missing_sets if len(names) == 1)
    return {
        "recipes": {part: pool[part] + sum(counts.values()) for part, counts in excluded.items()},
        "excluded": {part: {gate: counts[gate] for gate in GATES} for part, counts in excluded.items()},
        "incomplete": dict(sorted(incomplete_detail.items(), key=lambda item: (-item[1], item[0]))),
        "pool": pool,
        "usable_roles": dict(sorted(usable.items(), key=lambda item: (-item[1], item[0]))),
        "not_usable": dict(sorted(not_usable.items(), key=lambda item: (-item[1], item[0]))),
        "usable": sum(usable.values()),
        "unpriced": {
            "ingredients": len(uses),
            "per_recipe": {str(n): c for n, c in sorted(Counter(len(names) for names in missing_sets).items())},
            "top": [
                {"ingredient": name, "recipes": uses[name], "only_missing": alone[name]}
                for name in ranked[:LISTED_UNPRICED]
            ],
            "recovered_if_top_priced": recovered,
        },
    }


def table(rows: list[tuple], head: tuple[str, ...]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |", "| --- |" + " ---: |" * (len(head) - 1)]
    return lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]


def markdown(result: dict) -> str:
    sources = result["sources"]
    release, curated = result["recipes"]["release"], result["recipes"]["curated"]
    lines = [
        "# Planning pool report",
        "",
        "Generated by `python -m app.data.planning_pool` (`backend/app/data/planning_pool.py`); do not edit.",
        f"Release {sources['release_version']} (digest `{sources['release_digest']}`), recipe tags "
        f"`{sources['recipe_tags_sha256']}`, priceable ingredients `{sources['priceable_sha256']}`.",
        "",
        "Every shared catalog recipe is followed through the planning pool's gates (`RecipeRepository."
        "_load_for_planning`) and then the structured planner's role gate (`meal_role_of`). An excluded recipe is "
        "counted once, under the first gate it fails, in the order below. Curated recipes are never priced out and "
        "never judged incomplete.",
        "",
        "## From release to planner",
        "",
    ]
    rows = [("Recipes", release, curated)]
    rows += [
        (f"Excluded: {gate}", result["excluded"]["release"][gate], result["excluded"]["curated"][gate])
        for gate in GATES
    ]
    rows += [("**In the planning pool**", result["pool"]["release"], result["pool"]["curated"])]
    lines += table(rows, ("", "Release", "Curated"))
    lines += [
        "",
        f"Of the {sum(result['pool'].values())} recipes in the pool, **{result['usable']}** fill a lunch or dinner "
        "role of the structured planner; the rest are left out by the role gate:",
        "",
    ]
    lines += table(list(result["not_usable"].items()), ("Role gate", "Recipes"))
    lines += ["", "Roles of the recipes that fill one:", ""]
    lines += table(list(result["usable_roles"].items()), ("Meal role", "Recipes"))
    lines += ["", "## Incomplete recipes", ""]
    lines += table(list(result["incomplete"].items()), ("Reason (`recipe_quality.incomplete`)", "Recipes"))
    priced = result["unpriced"]
    lines += [
        "",
        "## Ingredients with no price",
        "",
        f"{result['excluded']['release'][UNPRICED]} release recipes are excluded only because "
        f"{priced['ingredients']} distinct ingredients have no price. Unpriced ingredients per such recipe:",
        "",
    ]
    lines += table(list(priced["per_recipe"].items()), ("Unpriced ingredients", "Recipes"))
    lines += ["", f"The {LISTED_UNPRICED} most used, with the recipes each is the only missing price of:", ""]
    lines += table(
        [(f"`{row['ingredient']}`", row["recipes"], row["only_missing"]) for row in priced["top"]],
        ("Ingredient", "Recipes", "Only missing price"),
    )
    lines += ["", "Recipes that would pass the price gate if the most used unpriced ingredients were priced:", ""]
    lines += table(
        [(f"top {n}" if n != "all" else "all", count) for n, count in priced["recovered_if_top_priced"].items()],
        ("Priced", "Recipes"),
    )
    lines += [
        "",
        "A recovered recipe still meets the later gates (withdrawn, incomplete, role), so these are upper bounds.",
        "",
        "Candidates the release build dropped before release are counted in the release's own quality report, "
        f"`data-engineering/data/release/{sources['release_version']}/quality_report.md`.",
    ]
    return "\n".join(lines) + "\n"


def load(session: Session) -> list[Recipe]:
    data = repository_root() / "data"
    import_catalog(session, load_catalog(data / "ingredients/ingredients.json", data / "recipes/recipes.json"))
    import_release_v2(session)
    session.commit()
    statement = select(Recipe).options(
        joinedload(Recipe.nutrition),
        selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient),
    )
    return list(session.scalars(statement).unique().all())


def main() -> None:
    root = repository_root()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        recipes = load(session)
        result = report(recipes, priceable=priceable_ingredients(), withdrawn=frozenset(withdrawn_slugs()))
    directory = release_dir()
    result["sources"] = {
        "release_version": RELEASE_VERSION,
        "release_digest": release_digest(directory),
        "recipe_tags_sha256": fingerprint(root / RECIPE_TAGS),
        "priceable_sha256": hashlib.sha256("\n".join(sorted(priceable_ingredients())).encode()).hexdigest(),
    }
    out = root / REPORT
    out.write_text(markdown(result), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out}: {sum(result['pool'].values())} in the pool, {result['usable']} fill a lunch or dinner role")


if __name__ == "__main__":
    main()
