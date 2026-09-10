"""Validate authored held-out evaluation episodes.

Six contributors author these episodes in parallel, so the constraints that make
the set usable have to be checked by a program rather than remembered:

  * cross-authoring - nobody writes or reviews episodes that test their own
    module (ADR-0020 section 2);
  * referential integrity - every recipe slug, product id and ingredient id
    resolves against the committed catalogs, so a frozen packet can be compiled;
  * gold-label consistency - an infeasible episode names its conflict, an
    ambiguous one names the missing field, unknown pantry quantities are never
    deductible, and no relaxation option offers to drop a safety constraint;
  * quota and language balance against the plan declared before authoring.

Standard library only, and no container: an author must be able to run it
immediately after saving a file.

    python scripts/check_heldout_episodes.py            # progress + errors
    python scripts/check_heldout_episodes.py --strict   # also require the full
                                                        # quota; used at freeze
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SET_DIR = ROOT / "data" / "evaluation" / "heldout" / "v2"
MANIFEST = SET_DIR / "set-manifest.json"
EPISODES = SET_DIR / "episodes"

RECIPES = ROOT / "data" / "recipes" / "recipes.json"
INGREDIENTS = ROOT / "data" / "ingredients" / "ingredients.json"
PRODUCTS = ROOT / "data" / "fixtures" / "fairprice-products.json"

VALID_CLASSES = {"feasible", "needs_clarification", "infeasible"}
VALID_LANGUAGES = {"en", "zh", "mixed"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "episode_id",
    "category",
    "language",
    "authored_by",
    "reviewed_by",
    "scenario",
    "gold",
}
REQUIRED_SCENARIO = {
    "user_request",
    "household_profile",
    "pantry",
    "planning_horizon",
    "recipe_candidate_slugs",
    "fairprice_product_ids",
}
REQUIRED_GOLD = {
    "class",
    "required_clarification_fields",
    "applicable_hard_constraints",
    "pantry_ground_truth",
    "author_rationale",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def catalogs() -> tuple[set[str], set[str], set[str]]:
    slugs = {row["slug"] for row in load_json(RECIPES)}
    ingredients = {row["normalized_name"] for row in load_json(INGREDIENTS)}
    products = {row["external_id"] for row in load_json(PRODUCTS)}
    return slugs, ingredients, products


def check_authorship(episode: dict, manifest: dict, label: str, errors: list[str]) -> None:
    roles = set(manifest["roles"])
    category = episode.get("category")
    spec = manifest["categories"].get(category)
    if spec is None:
        return

    under_test = set(spec["systems_under_test"])
    author = episode.get("authored_by")
    reviewer = episode.get("reviewed_by")

    if author not in roles:
        errors.append(f"{label}: authored_by '{author}' is not a declared role")
    elif author in under_test:
        errors.append(
            f"{label}: authored by '{author}', which owns a system this category "
            f"evaluates ({sorted(under_test)}). An author who knows where the system "
            "is weak cannot write an independent episode for it."
        )

    policy = manifest["review_policy"]
    if reviewer is None:
        return  # not yet reviewed; only --strict treats this as an error
    if reviewer not in roles:
        errors.append(f"{label}: reviewed_by '{reviewer}' is not a declared role")
        return
    if reviewer == author and not policy["reviewer_may_be_author"]:
        errors.append(f"{label}: reviewed by its own author '{reviewer}'")
    if reviewer in under_test and not policy["reviewer_may_own_system_under_test"]:
        errors.append(
            f"{label}: reviewed by '{reviewer}', which owns a system this category evaluates ({sorted(under_test)})"
        )


def check_references(
    episode: dict,
    slugs: set[str],
    ingredients: set[str],
    products: set[str],
    label: str,
    errors: list[str],
) -> None:
    scenario = episode.get("scenario") or {}

    for slug in scenario.get("recipe_candidate_slugs") or []:
        if slug not in slugs:
            errors.append(f"{label}: unknown recipe slug '{slug}'")
    for product in scenario.get("fairprice_product_ids") or []:
        if product not in products:
            errors.append(f"{label}: unknown product id '{product}'")
    for item in scenario.get("pantry") or []:
        name = item.get("ingredient_id")
        if name not in ingredients:
            errors.append(f"{label}: unknown pantry ingredient '{name}'")

    profile = scenario.get("household_profile") or {}
    for name in profile.get("excluded_ingredients") or []:
        if name not in ingredients:
            errors.append(
                f"{label}: excluded ingredient '{name}' is not a canonical ingredient. "
                "Use the normalized_name from data/ingredients/ingredients.json."
            )

    if not scenario.get("recipe_candidate_slugs"):
        errors.append(f"{label}: recipe_candidate_slugs is empty; a packet cannot be compiled")
    horizon = scenario.get("planning_horizon") or {}
    if not horizon.get("slots"):
        errors.append(f"{label}: planning_horizon.slots is empty")


def check_gold(episode: dict, label: str, errors: list[str]) -> None:
    gold = episode.get("gold") or {}
    scenario = episode.get("scenario") or {}
    missing = REQUIRED_GOLD - set(gold)
    if missing:
        errors.append(f"{label}: gold is missing {sorted(missing)}")
        return

    klass = gold.get("class")
    if klass not in VALID_CLASSES:
        errors.append(f"{label}: gold.class '{klass}' is not one of {sorted(VALID_CLASSES)}")
        return

    clarifications = gold.get("required_clarification_fields") or []
    if klass == "needs_clarification" and not clarifications:
        errors.append(
            f"{label}: class is needs_clarification but no required_clarification_fields "
            "are named, so there is nothing to score the question against"
        )
    if klass == "infeasible":
        if not gold.get("conflict_reason"):
            errors.append(
                f"{label}: class is infeasible but conflict_reason is empty. Refusing "
                "without naming the conflict is not a passing answer."
            )
        if clarifications:
            errors.append(
                f"{label}: class is infeasible but required_clarification_fields is not empty; choose one class"
            )
    if klass == "feasible" and gold.get("conflict_reason"):
        errors.append(f"{label}: class is feasible but conflict_reason is set")

    # A relaxation option may never offer to drop a safety constraint.
    profile = scenario.get("household_profile") or {}
    protected = {str(x).lower() for x in profile.get("allergens") or []}
    protected |= {str(x).lower() for x in profile.get("excluded_ingredients") or []}
    for option in gold.get("allowed_relaxations") or []:
        text = json.dumps(option, ensure_ascii=False).lower()
        for item in protected:
            if item and item in text:
                errors.append(
                    f"{label}: allowed_relaxations mentions the protected constraint "
                    f"'{item}'. Safety constraints are never offered as relaxations."
                )

    # Unknown pantry quantity may affect ranking but must never be deducted.
    truth = gold.get("pantry_ground_truth") or {}
    deductible = {row.get("ingredient_id") for row in truth.get("deductible") or []}
    unknown = set(truth.get("not_deductible_unknown_quantity") or [])
    for item in scenario.get("pantry") or []:
        name = item.get("ingredient_id")
        has_quantity = item.get("quantity") is not None
        if has_quantity and name not in deductible:
            errors.append(
                f"{label}: pantry item '{name}' has a known quantity but is not listed "
                "in gold.pantry_ground_truth.deductible"
            )
        if not has_quantity:
            if name in deductible:
                errors.append(
                    f"{label}: pantry item '{name}' has unknown quantity but is listed as "
                    "deductible. Unknown quantities are never deducted."
                )
            if name not in unknown:
                errors.append(
                    f"{label}: pantry item '{name}' has unknown quantity but is not listed "
                    "in gold.pantry_ground_truth.not_deductible_unknown_quantity"
                )

    if episode.get("category") == "multiturn_replan" and not gold.get("replan_invariants"):
        errors.append(
            f"{label}: a replanning episode must declare replan_invariants, or there is "
            "no way to score whether unrelated meals survived"
        )

    if not str(gold.get("author_rationale") or "").strip():
        errors.append(f"{label}: gold.author_rationale is empty")


def check_unfilled_scaffold(episode: dict, label: str, errors: list[str]) -> None:
    """`scripts/new_episode.py` writes TODO placeholders for every field that
    carries meaning. An episode still holding one has not been authored yet, and
    a half-filled scaffold in a frozen set is worse than a missing episode
    because it looks finished."""
    for path, value in walk_strings(episode):
        if value.startswith("TODO"):
            errors.append(f"{label}: {path} is still a scaffold placeholder")


def walk_strings(node, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def validate(strict: bool) -> tuple[list[str], dict[str, int], dict[str, int], int]:
    errors: list[str] = []
    manifest = load_json(MANIFEST)
    slugs, ingredients, products = catalogs()

    per_category: dict[str, int] = {name: 0 for name in manifest["categories"]}
    per_language: dict[str, int] = {name: 0 for name in manifest["language_plan"]}
    languages_seen: dict[str, set[str]] = {name: set() for name in manifest["categories"]}
    reviewed = 0
    seen_ids: set[str] = set()

    files = sorted(EPISODES.glob("*.json")) if EPISODES.exists() else []
    for path in files:
        label = path.name
        try:
            episode = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{label}: invalid JSON: {exc}")
            continue

        missing = REQUIRED_TOP_LEVEL - set(episode)
        if missing:
            errors.append(f"{label}: missing top-level fields {sorted(missing)}")
            continue
        if episode.get("schema_version") != "heldout-episode-v1":
            errors.append(f"{label}: schema_version must be 'heldout-episode-v1'")

        episode_id = episode.get("episode_id")
        if episode_id != path.stem:
            errors.append(f"{label}: episode_id '{episode_id}' does not match the filename")
        if episode_id in seen_ids:
            errors.append(f"{label}: duplicate episode_id '{episode_id}'")
        seen_ids.add(episode_id)

        category = episode.get("category")
        if category not in manifest["categories"]:
            errors.append(f"{label}: unknown category '{category}'")
        else:
            per_category[category] += 1
            languages_seen[category].add(episode.get("language"))

        language = episode.get("language")
        if language not in VALID_LANGUAGES:
            errors.append(f"{label}: language '{language}' is not one of {sorted(VALID_LANGUAGES)}")
        elif language in per_language:
            per_language[language] += 1

        missing_scenario = REQUIRED_SCENARIO - set(episode.get("scenario") or {})
        if missing_scenario:
            errors.append(f"{label}: scenario is missing {sorted(missing_scenario)}")

        check_authorship(episode, manifest, label, errors)
        check_references(episode, slugs, ingredients, products, label, errors)
        check_gold(episode, label, errors)
        check_unfilled_scaffold(episode, label, errors)

        if episode.get("reviewed_by"):
            reviewed += 1
        elif strict:
            errors.append(f"{label}: not reviewed; a frozen set needs every episode reviewed")

    if strict:
        for category, spec in manifest["categories"].items():
            if per_category[category] != spec["quota"]:
                errors.append(f"category '{category}': {per_category[category]} episodes, quota is {spec['quota']}")
            if len(languages_seen[category]) < manifest["min_languages_per_category"]:
                errors.append(
                    f"category '{category}': uses {len(languages_seen[category])} language(s); "
                    f"the plan requires at least {manifest['min_languages_per_category']} so "
                    "that language does not become a proxy for difficulty"
                )
        for language, planned in manifest["language_plan"].items():
            if per_language[language] != planned:
                errors.append(f"language '{language}': {per_language[language]} episodes, plan is {planned}")

    return errors, per_category, per_language, reviewed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also require the full quota, the declared language balance and a reviewer "
        "on every episode; run this before freezing the set",
    )
    args = parser.parse_args()

    errors, per_category, per_language, reviewed = validate(args.strict)
    manifest = load_json(MANIFEST)
    total = sum(per_category.values())
    quota = sum(spec["quota"] for spec in manifest["categories"].values())

    print(f"Held-out set '{manifest['set_id']}' - status {manifest['status']}")
    print(f"Authored {total}/{quota} episodes, {reviewed} reviewed.")
    for category, spec in manifest["categories"].items():
        print(f"  {category:<22} {per_category[category]:>3}/{spec['quota']}")
    plan = manifest["language_plan"]
    print("  language                " + ", ".join(f"{name} {per_language[name]}/{plan[name]}" for name in plan))

    if errors:
        print("\nProblems:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nNo problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
