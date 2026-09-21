"""Re-derive planning scenario expectations for a larger catalog, from the catalog alone.

The v1 planning scenarios were labelled against the 30-recipe curated catalog.
A scenario is feasible when at least one recipe the weekly planner may draw
from satisfies every hard constraint in its request, so adding recipes can turn
an infeasible scenario feasible and never the reverse. This script decides the
label for a larger catalog without running any system under test: it reads the
catalog files and applies the constraints as stated, so the label cannot have
been fitted to a system's output.

    python scripts/derive_catalog_labels.py            # writes planning-catalog-v2.1.json per split, and the record
    python scripts/derive_catalog_labels.py --check    # fails when a committed file is stale

The planner's pool on the larger catalog is every curated recipe plus every
release recipe whose course fills a meal (main, soup) and whose every
ingredient can be priced: listed in the curated product fixture's ingredient
keys, or mapped (or not purchased) in the release FairPrice snapshot.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURATED_RECIPES = ROOT / "data" / "recipes" / "recipes.json"
CURATED_INGREDIENTS = ROOT / "data" / "ingredients" / "ingredients.json"
IMPLICATIONS = ROOT / "data" / "recipes" / "dietary-tag-implications.json"
FIXTURE = ROOT / "data" / "fixtures" / "fairprice-products.json"
RELEASE = ROOT / "data-engineering" / "data" / "release" / "v2.1"
SNAPSHOT = ROOT / "data" / "products" / "fairprice-v2-snapshot.json"
MIN_CONFIDENCE_NOTE = "mappings under the snapshot's confidence floor are absent from it"
LABEL = "catalog-v2.1"
# Per split: the v1 scenarios, relabelled, followed by scenarios written for the
# larger catalog (whose labels the author gives and this script checks).
SETS = {
    "developer": (
        ROOT / "data" / "evaluation" / "dev" / "planning-v1.json",
        ROOT / "data" / "evaluation" / "dev" / "planning-catalog-v2.1-new.json",
    ),
    "heldout": (
        ROOT / "data" / "evaluation" / "heldout" / "planning-v1.json",
        ROOT / "data" / "evaluation" / "heldout" / "planning-catalog-v2.1-new.json",
    ),
}
VOCABULARY = ROOT / "data" / "ingredients" / "allergen-vocabulary.json"
DIETS = {"vegetarian", "vegan", "gluten-free", "dairy-free"}
RECORD = ROOT / "docs" / "evaluation" / f"{LABEL}-labels.json"
MEAL_COURSES = {"main", "soup"}
# Release allergen names -> runtime names; sulfites have no runtime name.
ALLERGEN = {
    "milk": "dairy",
    "eggs": "egg",
    "tree_nuts": "tree_nut",
    "peanuts": "peanut",
    "crustaceans": "shellfish",
    "molluscs": "shellfish",
    "gluten_candidate": "gluten",
}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def closure(tags: set[str], implications: dict[str, set[str]]) -> set[str]:
    out, frontier = set(tags), list(tags)
    while frontier:
        for entailed in implications.get(frontier.pop(), set()):
            if entailed not in out:
                out.add(entailed)
                frontier.append(entailed)
    return out


def planning_pool() -> list[dict]:
    """Every recipe the weekly planner may draw from, as plain facts."""
    implications = {tag: set(entry["entails"]) for tag, entry in _json(IMPLICATIONS)["implications"].items()}
    allergens_of = {row["normalized_name"]: set(row.get("allergens") or []) for row in _json(CURATED_INGREDIENTS)}
    pool = []
    curated = _json(CURATED_RECIPES)
    for recipe in curated["recipes"] if isinstance(curated, dict) else curated:
        names = [item["ingredient"] for item in recipe["ingredients"]]
        pool.append(
            {
                "id": recipe["slug"],
                "minutes": recipe["prep_time_minutes"] + recipe["cook_time_minutes"],
                "allergens": set().union(*(allergens_of.get(name, set()) for name in names)),
                "tags": closure(set(recipe.get("dietary_tags") or []), implications),
                "ingredients": set(names),
                "sodium_mg": recipe["nutrition"]["sodium_mg"],
            }
        )
    fixture_keys = {key for product in _json(FIXTURE) for key in product.get("ingredient_keys", [])}
    snapshot = _json(SNAPSHOT)["ingredients"]
    priceable = fixture_keys | {
        name for name, entry in snapshot.items() if entry["status"] in {"mapped", "not_purchased"}
    }
    for recipe in _jsonl(RELEASE / "recipes.jsonl"):
        names = {line["canonical_ingredient_id"][4:].lower() for line in recipe["ingredients"]}
        if recipe["course"] not in MEAL_COURSES or not names <= priceable:
            continue
        pool.append(
            {
                "id": recipe["recipe_id"],
                "minutes": recipe["prep_minutes"] + recipe["cook_minutes"],
                "allergens": {ALLERGEN.get(a, a) for a in recipe["allergens"]} - {"sulfites"},
                "tags": closure(set(recipe["dietary_tags"]), implications),
                "ingredients": names,
                "sodium_mg": recipe["nutrition"]["sodium_mg"],
            }
        )
    return pool


def eligible(request: dict, pool: list[dict]) -> list[dict]:
    """Recipes meeting the request's recipe-level hard constraints."""
    limit = request.get("max_cooking_time_minutes", 60)  # the request schema's default
    allergens = set(request.get("allergens") or [])
    excluded = set(request.get("excluded_ingredients") or [])
    diets = set(request.get("dietary_preferences") or [])
    sodium = request.get("max_sodium_mg_per_meal")
    return [
        recipe
        for recipe in pool
        if recipe["minutes"] <= limit
        and not recipe["allergens"] & allergens
        and not recipe["ingredients"] & excluded
        and diets <= recipe["tags"]
        and (sodium is None or recipe["sodium_mg"] <= sodium)
    ]


PRICE_CONSTRAINTS = ("budget_per_meal_sgd", "weekly_budget_sgd")
DAYS = 7  # a weekly plan is seven dinners


def forced_repetitions(request: dict, pool: list[dict]) -> tuple[int | None, int]:
    """Eligible dishes, and the adjacent repetitions any valid week must contain (protocol v1.1).

    Two or more eligible dishes can alternate, so no repetition is forced; one
    dish forces a repeat on every day after the first. A budget is left to the
    planner's pricing, which this script does not model, so a budgeted scenario
    is recorded as forcing none: the strict rule applies to it.
    """
    if any(key in request for key in PRICE_CONSTRAINTS):
        return None, 0
    count = len(eligible(request, pool))
    return count, DAYS - 1 if count == 1 else 0


def relabel(scenarios: list[dict], pool: list[dict]) -> tuple[list[dict], list[dict]]:
    """New scenarios and the evidence for every label that changed."""
    out, changes = [], []
    for scenario in scenarios:
        new = dict(scenario)
        if not scenario["expected_feasible"]:
            if any(key in scenario["request"] for key in PRICE_CONSTRAINTS):
                raise SystemExit(f"{scenario['id']}: an infeasible scenario with a budget needs pricing to relabel")
            matches = eligible(scenario["request"], pool)
            if matches:
                new["expected_feasible"] = True
                changes.append(
                    {
                        "id": scenario["id"],
                        "name": scenario["name"],
                        "from": False,
                        "to": True,
                        "eligible_recipes": len(matches),
                        "examples": sorted(recipe["id"] for recipe in matches)[:5],
                    }
                )
        out.append(new)
    return out, changes


def target(path: Path) -> Path:
    return path.with_name(f"planning-{LABEL}.json")


def check_new(scenarios: list[dict], pool: list[dict], known_ids: set[str]) -> list[str]:
    """Problems with scenarios written for the larger catalog; their labels are the author's."""
    checked = set(_json(VOCABULARY)["checked"])
    ingredients = set().union(*(recipe["ingredients"] for recipe in pool))
    problems = []
    for scenario in scenarios:
        request, where = scenario["request"], scenario.get("id", "?")
        if where in known_ids:
            problems.append(f"{where}: id already used")
        known_ids.add(where)
        unknown = set(request.get("allergens") or []) - checked
        unknown |= set(request.get("dietary_preferences") or []) - DIETS
        unknown |= set(request.get("excluded_ingredients") or []) - ingredients
        if unknown:
            problems.append(f"{where}: names nothing in the catalog vocabulary: {sorted(unknown)}")
        found = len(eligible(request, pool))
        priced = any(key in request for key in PRICE_CONSTRAINTS)
        if not scenario["expected_feasible"] and priced:
            problems.append(f"{where}: an infeasible label with a budget cannot be checked without pricing")
        elif not priced and scenario["expected_feasible"] != bool(found):
            problems.append(f"{where}: labelled {scenario['expected_feasible']} but {found} recipes are eligible")
        elif priced and scenario["expected_feasible"] and not found:
            problems.append(f"{where}: labelled feasible but no recipe meets its non-budget constraints")
    return problems


def render(scenarios: list[dict]) -> str:
    return json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    pool = planning_pool()
    outputs = {}
    record = {
        "label": LABEL,
        "rule": (
            "A scenario is feasible when at least one recipe in the planning pool meets every recipe-level "
            "hard constraint (time as prep plus cook, allergens, excluded ingredients, dietary requirements "
            "with their definitional entailments, sodium). A larger catalog can only add feasible scenarios, "
            "so only scenarios labelled infeasible are re-derived; feasible ones keep their label."
        ),
        "pool": {
            "recipes": len(pool),
            "definition": "curated recipes plus release main/soup recipes whose every ingredient is priceable; "
            + MIN_CONFIDENCE_NOTE,
        },
        "sets": {},
    }
    problems = []
    for name, (path, new_path) in SETS.items():
        scenarios, changes = relabel(_json(path), pool)
        new = _json(new_path) if new_path.exists() else []
        problems += check_new(new, pool, {s["id"] for s in scenarios})
        outputs[target(path)] = render(scenarios + new)
        eligibility = {}
        for scenario in scenarios + new:
            if scenario["expected_feasible"]:
                count, forced = forced_repetitions(scenario["request"], pool)
                eligibility[scenario["id"]] = {"eligible_recipes": count, "forced_repetitions": forced}
        record["sets"][name] = {
            "eligibility": eligibility,
            "source": path.relative_to(ROOT).as_posix(),
            "new_scenarios": new_path.relative_to(ROOT).as_posix() if new else None,
            "new_count": len(new),
            "derived": target(path).relative_to(ROOT).as_posix(),
            "changed": changes,
        }
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    outputs[RECORD] = json.dumps(record, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        stale = [p for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"stale: {path.relative_to(ROOT).as_posix()}", file=sys.stderr)
        return 1 if stale else 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    for name, entry in record["sets"].items():
        print(name, [(c["id"], c["eligible_recipes"]) for c in entry["changed"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
