"""Prove each multi-dish episode's class from its pool and the catalog, running no system under test.

A label is accepted only with evidence:
- **feasible**: a witness week exists. That is seven valid meals (one eligible
  dish per required role, distinct, within the meal-time limit) meeting every
  stated repetition request, bought whole-package from the snapshot within the
  budget.
- **infeasible**: a proof of impossibility, one of:
  - no valid meal exists;
  - a repetition request cannot be met by the pool (a recipe the household
    asked for is not eligible, or no-repeats with fewer eligible dishes for a
    required role than there are dinners);
  - the budget is below a lower bound on any week's cost (the cheapest valid
    meal's ingredient use, every night, less the pantry's worth).

Anything else is unproven, and the author must change the episode.

    python -m app.evaluation.multidish_labels FILE...
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from itertools import product
from pathlib import Path

from app.core.paths import repository_root
from app.evaluation.release_catalog import load_release_catalog
from app.evaluation.strict_success import dish_shares, load_tag_implications, meal_minutes, satisfied_tags


def _context(episode: dict):
    catalog = load_release_catalog()
    allergens = {row["normalized_name"]: set(row["allergens"]) for row in catalog.ingredients}
    implications = load_tag_implications(repository_root() / "data/recipes/dietary-tag-implications.json")
    gold = episode["gold"]["applicable_hard_constraints"]
    pool = [catalog.by_slug[slug] for slug in episode["scenario"]["recipe_candidate_slugs"]]
    allowed = set(episode["scenario"]["fairprice_product_ids"])
    per_gram: dict[str, float] = {}
    packages: dict[str, list[tuple[float, float]]] = {}
    for product_row in catalog.products:
        if product_row["external_id"] not in allowed:
            continue
        name = product_row["ingredient_id"]
        per_gram[name] = min(per_gram.get(name, math.inf), product_row["price_sgd"] / product_row["package_size"])
        packages.setdefault(name, []).append((product_row["package_size"], product_row["price_sgd"]))

    def eligible(recipe: dict) -> bool:
        names = {line["ingredient"] for line in recipe["ingredients"]}
        if any(set(gold["allergens_absent"]) & allergens.get(name, {"unchecked"}) for name in names):
            return False
        if names & set(gold["excluded_ingredients_absent"]):
            return False
        return set(gold["dietary_tags_required"]) <= satisfied_tags(recipe["dietary_tags"], implications)

    return gold, pool, eligible, per_gram, packages


def valid_meals(episode: dict) -> list[tuple[tuple[str, dict], ...]]:
    """Every valid meal the pool allows, as (role, recipe) pairs."""
    gold, pool, eligible, _, _ = _context(episode)
    roles = episode["scenario"]["household_profile"]["meal_composition"]
    per_role = {r["role_id"]: [x for x in pool if x["course"] in r["courses"] and eligible(x)] for r in roles}
    limit = gold["max_cooking_time_minutes"]
    required = [r for r in roles if r["required"]]
    optional = [r for r in roles if not r["required"]]
    meals = []
    for extra in range(len(optional) + 1):
        for chosen_optional in [optional[:extra]]:
            chosen = required + chosen_optional
            for combo in product(*[per_role[r["role_id"]] for r in chosen]):
                if len({d["slug"] for d in combo}) != len(combo):
                    continue
                if limit is not None and meal_minutes(list(combo)) > limit:
                    continue
                meals.append(tuple(zip([r["role_id"] for r in chosen], combo, strict=True)))
    return meals


def valid_meal_exists(episode: dict) -> tuple[bool, dict[str, int]]:
    gold, pool, eligible, _, _ = _context(episode)
    roles = episode["scenario"]["household_profile"]["meal_composition"]
    counts = {r["role_id"]: sum(x["course"] in r["courses"] and eligible(x) for x in pool) for r in roles}
    return bool(valid_meals(episode)), counts


def _names(recipe: dict) -> set[str]:
    return {line["ingredient"] for line in recipe["ingredients"]}


def _consumed(meal, size: int, per_gram: dict[str, float]) -> float:
    shares = dish_shares([role for role, _ in meal])
    return sum(
        line["quantity"] * size * shares[role] / recipe["servings"] * per_gram.get(line["ingredient"], math.inf)
        for role, recipe in meal
        for line in recipe["ingredients"]
    )


def evidence(episode: dict) -> dict:
    gold, pool, eligible, per_gram, packages = _context(episode)
    size = episode["scenario"]["household_profile"]["household_size"] or 1
    slots = episode["scenario"]["planning_horizon"]["slots"]
    rules = gold.get("repetition_requirements") or {}
    meals = valid_meals(episode)
    out: dict = {"valid_meals": len(meals)}
    if not meals:
        return {**out, "verdict": "infeasible_proven", "why": "no valid meal exists in the pool"}

    for count in rules.get("recipe_counts") or []:
        if count.get("min_uses") and not any(count["recipe_id"] == r["slug"] for m in meals for _, r in m):
            return {**out, "verdict": "infeasible_proven", "why": f"{count['recipe_id']} is in no valid meal"}
    if rules.get("max_uses_per_recipe") == 1:
        roles = episode["scenario"]["household_profile"]["meal_composition"]
        for role in [r for r in roles if r["required"]]:
            dishes = {r["slug"] for m in meals for k, r in m if k == role["role_id"]}
            if len(dishes) < len(slots):
                return {
                    **out,
                    "verdict": "infeasible_proven",
                    "why": f"no repeats, but only {len(dishes)} {role['role_id']} dishes for {len(slots)} dinners",
                }

    # A witness week: the cheapest meal each night that keeps every stated request reachable.
    uses: dict[str, int] = {}
    week = []
    for night in range(len(slots)):
        left = len(slots) - night

        def ok(meal, left=left) -> bool:
            trial = dict(uses)
            for _, r in meal:
                trial[r["slug"]] = trial.get(r["slug"], 0) + 1
            cap = rules.get("max_uses_per_recipe")
            for count in rules.get("recipe_counts") or []:
                n = trial.get(count["recipe_id"], 0)
                if count.get("max_uses") is not None and n > count["max_uses"]:
                    return False
                if count.get("min_uses", 0) - n > left - 1:
                    return False
            return cap is None or all(n <= cap for n in trial.values())

        choices = sorted(
            (m for m in meals if ok(m)), key=lambda m: (_consumed(m, size, per_gram), [r["slug"] for _, r in m])
        )
        wanted = [
            m
            for m in choices
            if any(
                uses.get(c["recipe_id"], 0) < c.get("min_uses", 0) and c["recipe_id"] in {r["slug"] for _, r in m}
                for c in rules.get("recipe_counts") or []
            )
        ]
        wanted += [
            m
            for m in choices
            if any(
                sum(any(w["ingredient_id"] in _names(r) for _, r in meal) for meal in week) < w["min_meals"]
                and any(w["ingredient_id"] in _names(r) for _, r in m)
                for w in rules.get("ingredient_meals") or []
            )
        ]
        pick = (wanted or choices or [None])[0]
        if pick is None:
            return {
                **out,
                "verdict": "unproven",
                "why": "no witness week meets the repetition requests; change the episode",
            }
        week.append(pick)
        for _, r in pick:
            uses[r["slug"]] = uses.get(r["slug"], 0) + 1
    met_ingredients = all(
        sum(any(w["ingredient_id"] in _names(r) for _, r in meal) for meal in week) >= w["min_meals"]
        for w in rules.get("ingredient_meals") or []
    )
    if not met_ingredients:
        return {
            **out,
            "verdict": "unproven",
            "why": "the witness week misses an ingredient request; change the episode",
        }

    demand: dict[str, float] = {}
    for meal in week:
        shares = dish_shares([role for role, _ in meal])
        for role, recipe in meal:
            for line in recipe["ingredients"]:
                demand[line["ingredient"]] = (
                    demand.get(line["ingredient"], 0.0) + line["quantity"] * size * shares[role] / recipe["servings"]
                )
    pantry = {
        p["ingredient_id"]: p["quantity"]
        for p in episode["scenario"]["pantry"]
        if p["quantity"] is not None and p["unit"] == "g"
    }
    witness_cost = 0.0
    for name, grams in demand.items():
        remaining = max(0.0, grams - pantry.get(name, 0.0))
        if remaining > 0:
            witness_cost += min(math.ceil(remaining / size_g - 1e-9) * price for size_g, price in packages[name])
    witness_cost = round(witness_cost, 2)
    cheapest = min(_consumed(m, size, per_gram) for m in meals)
    pantry_worth = sum(q * per_gram.get(name, 0.0) for name, q in pantry.items())
    lower_bound = round(max(0.0, cheapest * len(slots) - pantry_worth), 2)
    out.update(
        witness_cost_sgd=witness_cost,
        cost_lower_bound_sgd=lower_bound,
        witness=[[r["slug"] for _, r in meal] for meal in week],
    )
    budget = gold.get("budget_sgd")
    if budget is None or budget >= witness_cost:
        return {**out, "verdict": "feasible_proven"}
    if budget < lower_bound:
        return {**out, "verdict": "infeasible_proven", "why": f"budget {budget} is below the lower bound {lower_bound}"}
    return {
        **out,
        "verdict": "unproven",
        "why": f"budget {budget} lies between the lower bound {lower_bound} and the witness {witness_cost}",
    }


def check(episode: dict) -> str | None:
    """Why the label is not proven, or None."""
    label = episode["gold"]["class"]
    if label == "needs_clarification":
        return None
    found = evidence(episode)
    wanted = {"feasible": "feasible_proven", "infeasible": "infeasible_proven"}[label]
    return None if found["verdict"] == wanted else f"{label} but {found['verdict']}: {found.get('why', '')}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    wrong = []
    for path in parser.parse_args().files:
        episode = json.loads(path.read_text(encoding="utf-8"))
        problem = check(episode)
        found = evidence(episode) if episode["gold"]["class"] != "needs_clarification" else {}
        print(
            f"{episode['episode_id']}: {episode['gold']['class']}; {found.get('verdict', 'n/a')} "
            f"witness={found.get('witness_cost_sgd')} bound={found.get('cost_lower_bound_sgd')} {problem or ''}"
        )
        if problem:
            wrong.append(episode["episode_id"])
    if wrong:
        print("labels without proof: " + ", ".join(wrong))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
