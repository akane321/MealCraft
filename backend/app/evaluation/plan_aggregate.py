"""The formal run's `plan` aggregate: the metric table of 02-baselines section 6, from each case's local record.

Computed after every arm has finished, from `response`, `scored` and the final exchange of each record (a held-out
run keeps all three in `.local/evaluation/`), so it can change nothing an arm saw. Only counts and means reach `--out`.

A hard constraint is one of four states on a plan: violated, within, `unknown` (stated, but this plan cannot be
judged) or `not_applicable` (the case states none). The rate is violated over known, and the unknown count stands
beside it, so a rate is never inflated by dropping an unknown silently:

- `allergen_violation`: the gold's allergens against `scored.recomputation`, not `scored.allergen_safe`, which reads
  only the development gold and a stated household and so is always true on the held-out interchange. An allergen
  the plan holds is a violation even with lines unknown, unless the limit is one member's and some dish is marked
  `not_for` someone (who may be that member); otherwise incomplete allergens, or an allergen no check covers, are
  unknown. Names are read as the runtime vocabulary or through `allergen_keywords`.
- `over_budget`: the recomputed whole-package total (no total, as with `needs_data` or `limit_exceeded`: unknown)
  against `weekly_budget_sgd`, or the development `budget_sgd`. A week or trip budget on a plan of n seven-day periods
  allows n budgets. Whole cents, no tolerance. The total is one consolidated purchase, so past seven days it can
  prove over budget only: at or under n budgets is unknown. So is an over total with a pantry stated, as the
  recomputation buys everything. `unknown_known_lines_over_n` counts unknowns whose priced lines alone already pass.
- `nutrition_out_of_bounds`: `sodium_limit_mg` per person on each meal or each day, with `dinner_sodium_share` on the
  dinners under a daily limit; the development `nutrition_bands` through `strict_success`. A real excess is reported
  even when another meal cannot be computed; any other scope, or a limit enabled with no number, is unknown.

`meal_likeness` counts lunches and dinners, with the checks of `full_default`: the filling core and the non-meal dish
read the catalog's tags through `recipe_reference`, so a dish naming no catalog recipe is unknown, and the energy floor
reads the recomputed nutrition, so a line without facts is unknown. A case stating its own `meal_structure` is
`not_applicable` for the filling core, which is the full default's. People at a meal are the largest `servings`
among its dishes. `calls` come from each arm's ledger meter: for the product arms one a message, whatever it sent.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date
from math import ceil
from types import SimpleNamespace
from typing import Any

from app.data.tag_files import recipe_tags
from app.evaluation import full_default
from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping
from app.evaluation.baseline_recomputation import NUTRIENT_FIELDS, allergen_keywords, dish_nutrition_per_serving
from app.evaluation.baseline_resources import BaselineResources
from app.evaluation.heldout_report import CaseOutcome, _withhold_small
from app.evaluation.heldout_statistics import MetricSpec, compare
from app.evaluation.pure_llm_baseline import episode_id_of
from app.evaluation.strict_success import _check_nutrition

NOT_APPLICABLE = "not_applicable"
HARD = ("allergen_violation", "over_budget", "nutrition_out_of_bounds")
MEAL_CHECKS = ("filling_core", "energy_floor", "no_non_meal_dish")
# In the paired comparison: a pass, so that the rates read the same way as `success` there. Known on both sides only.
PASSES = {"allergen_violation": "allergen_safe", "over_budget": "within_budget", "nutrition_out_of_bounds": "in_bounds"}
NOTE = "Rates are numerator over known; unknown and not_applicable counts stand beside them."
UNSCORED = {
    "scoring_error": True,
    "allergen_violation": None,
    "over_budget": None,
    "known_lines_over": False,
    "nutrition_out_of_bounds": None,
    "gram_coverage": None,
    "verifiable_dish_share": None,
    "pricing_status": "unscored",
    "price_sgd": None,
    "distinct_dishes": None,
    "meals": [],
}


def _stated(gold: dict[str, Any]) -> list[dict[str, Any]]:
    """The gold's constraints, and what an intent gold states only in its expected fields."""
    rows = list(gold.get("hard_constraints") or [])
    named = {row.get("field") for row in rows}
    expected = gold.get("expected_fields") or {}
    for name in ("allergens", "members", "weekly_budget_sgd", "sodium_limit_mg", "sodium_limit_enabled"):
        if name in expected and name not in named:
            scope = "week" if name == "weekly_budget_sgd" else expected.get("allergen_avoidance_scope")
            rows.append({"field": name, "operator": "eq", "value": expected[name], "scope": scope})
    if "dinner_sodium_share" in expected and "dinner_sodium_share" not in named:
        rows.append({"field": "dinner_sodium_share", "operator": "eq", "value": expected["dinner_sodium_share"]})
    return rows


def _number(row: dict[str, Any]) -> float | None:
    value = row.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or row.get("operator") not in ("le", "eq"):
        return None
    return float(value)


def requested_allergens(episode: dict[str, Any]) -> tuple[list[str], bool]:
    """(allergens to avoid, whether any is one member's). Development episodes as `score` reads them."""
    gold = episode.get("gold") or {}
    wanted: list[str] = []
    member = False
    for row in _stated(gold):
        if row.get("field") == "allergens" and row.get("operator") != "include":
            value = row.get("value")
            wanted += [value] if isinstance(value, str) else list(value or [])
            member |= row.get("scope") == "member"
        elif row.get("field") == "members":
            named = [name for person in row.get("value") or [] for name in person.get("allergens") or []]
            wanted += named
            member |= bool(named)
    development = (gold.get("applicable_hard_constraints") or {}).get("allergens_absent")
    if development is None:
        household = episode.get("scenario", {}).get("household_profile") or {}
        development = household.get("allergens") or []
    return wanted + list(development), member


def allergen_state(episode: dict[str, Any], recomputed: dict | None, plan: dict, checked: Iterable[str]) -> Any:
    wanted, member = requested_allergens(episode)
    if not wanted:
        return NOT_APPLICABLE
    if recomputed is None:
        return None
    vocabulary = {name.lower() for name in checked}
    targets: set[str] = set()
    uncovered = False
    for name in wanted:
        low = name.strip().casefold()
        found = {low} if low in vocabulary else allergen_keywords(low)
        uncovered |= not found
        targets |= found
    if targets & {name.lower() for name in recomputed["allergens"]}:
        return None if member and any(d.get("not_for") for m in plan["meals"] for d in m["dishes"]) else True
    return None if uncovered or not recomputed["allergens_complete"] else False


def budget_state(gold: dict[str, Any], recomputed: dict | None, plan: dict) -> tuple[Any, bool]:
    """(state, whether an unknown's priced lines alone already pass the budget)."""
    rows = [row for row in _stated(gold) if row.get("field") == "weekly_budget_sgd"]
    limits = [(_number(row), row.get("scope")) for row in rows]
    development = (gold.get("applicable_hard_constraints") or {}).get("budget_sgd")
    if development is not None:
        limits.append((float(development), "plan"))
    if not limits:
        return NOT_APPLICABLE, False
    if recomputed is None:
        return None, False
    days = sorted(date.fromisoformat(meal["date"]) for meal in plan["meals"])
    periods = ceil(((days[-1] - days[0]).days + 1) / 7)
    multiples = {"week": periods, "trip": periods, "household": periods, "plan": 1}
    allowed = [
        (value * multiples[scope], multiples[scope])
        for value, scope in limits
        if value is not None and scope in multiples
    ]
    total = recomputed["purchase_total_sgd"]
    known = sum(item["purchase_cost_sgd"] or 0 for item in recomputed["price_results"])
    if total is None or len(allowed) < len(limits):
        return None, total is None and any(round(known * 100) > round(limit * 100) for limit, _ in allowed)
    if any(round(total * 100) > round(limit * 100) for limit, _ in allowed):
        pantry = any(row.get("field") == "pantry" for row in _stated(gold)) or (gold.get("expected_fields") or {}).get(
            "pantry"
        )
        deductible = (gold.get("pantry_ground_truth") or {}).get("deductible")
        return (None, False) if pantry or deductible else (True, False)
    # ponytail: one consolidated total cannot show each period within its budget; price per period to settle it.
    return (None if any(n > 1 for _, n in allowed) else False), False


def nutrition_state(gold: dict[str, Any], meals: list[dict] | None) -> Any:
    rows = _stated(gold)
    limits = [row for row in rows if row.get("field") == "sodium_limit_mg"]
    enabled = any(row.get("field") == "sodium_limit_enabled" and row.get("value") is True for row in rows)
    bands = (gold.get("applicable_hard_constraints") or {}).get("nutrition_bands")
    if not limits and not enabled and not bands:
        return NOT_APPLICABLE
    if meals is None:
        return None
    states: list[bool | None] = [None] if (enabled and not limits) else []
    share = next((row.get("value") for row in rows if row.get("field") == "dinner_sodium_share"), None)
    for row in limits:
        limit = _number(row)
        if limit is None or row.get("scope") not in ("meal", "day"):
            states.append(None)
        elif row["scope"] == "meal":
            states += [_over([meal], limit) for meal in meals]
        else:
            for day in {meal["date"] for meal in meals}:
                states.append(_over([meal for meal in meals if meal["date"] == day], limit))
            if isinstance(share, (int, float)):
                states += [_over([meal], limit * share) for meal in meals if meal["meal_type"] == "dinner"]
    if bands:
        recipes = [
            {"slug": dish["name"], "nutrition": dish["per_serving"]} for meal in meals for dish in meal["dishes"]
        ]
        status = _check_nutrition({"nutrition_bands": bands}, recipes, 0.0).outcome
        states.append({"passed": False, "failed": True}.get(status))
    return True if True in states else (None if None in states else False)


def _over(meals: list[dict], limit: float) -> bool | None:
    known = [meal["per_person"]["sodium_mg"] for meal in meals if meal["per_person"]]
    if sum(known) > limit:
        return True
    return None if len(known) < len(meals) else False


def _meals(record: dict[str, Any], facts: dict) -> list[dict]:
    """Each planned meal with its date, per-person nutrition (None when a line has no facts) and dishes' tags."""
    plan = record["exchanges"][-1]["output"]["plan"]
    scored = iter(record["scored"]["dishes"])
    tags = recipe_tags()
    meals = []
    for meal, answered in zip(plan["meals"], record["response"]["plan"]["meals"], strict=True):
        dishes = []
        for dish, said in zip(meal["dishes"], answered["dishes"], strict=True):
            lines = tuple(IngredientMapping(**line) for line in next(scored)["mappings"])
            whole = DishCoverage("", None, "", 1, 0, lines)
            total = dish_nutrition_per_serving(whole, facts)
            servings = said["servings"]
            entry = tags.get(dish.get("recipe_reference") or "") or {}
            dishes.append(
                {
                    "name": dish["name"],
                    "role": dish.get("role") or "",
                    "total": total,
                    "servings": servings,
                    "per_serving": total and {field: value / servings for field, value in total.items()},
                    "tag": SimpleNamespace(**entry) if entry.get("meal_role") else None,
                }
            )
        people = max(dish["servings"] for dish in dishes)
        per_person = None
        if all(dish["total"] for dish in dishes):
            per_person = {f: sum(dish["total"][f] for dish in dishes) / people for f in NUTRIENT_FIELDS}
        meals.append({"date": meal["date"], "meal_type": meal["meal_type"], "dishes": dishes, "per_person": per_person})
    return meals


def meal_checks(meal: dict, own_structure: bool) -> dict[str, Any]:
    """One lunch or dinner against `full_default`'s checks; a check it cannot compute is None."""
    known: dict[str, Any] = {}
    for dish in meal["dishes"]:
        if dish["tag"]:  # two dishes of one role, as a baseline may give, stay two: `main`, `main-2`
            known[dish["role"] if dish["role"] not in known else f"{dish['role']}-{len(known) + 1}"] = dish["tag"]
    whole = len(known) == len(meal["dishes"])
    core: Any = NOT_APPLICABLE if own_structure else (full_default.has_filling_core(known) if whole else None)
    no_non_meal = full_default.no_non_meal_dish(known)
    energy = None
    if meal["per_person"]:
        energy = meal["per_person"]["calories_kcal"] >= full_default.energy_floor_kcal(meal["meal_type"]) - 1e-6
    return {
        "filling_core": core,
        # A dish the tags already fail settles it, whatever the unknown ones are.
        "no_non_meal_dish": False if not no_non_meal else (True if whole else None),
        "energy_floor": energy,
    }


def case_row(episode: dict[str, Any], record: dict | None, resources: BaselineResources) -> dict[str, Any]:
    """One arm's one case as the aggregate reads it; never leaves this module."""
    if record is None:
        return {"status": "missing"}
    row: dict[str, Any] = {
        "elapsed_seconds": record.get("elapsed_seconds") or 0.0,
        "calls": record.get("calls") or 0,
        "usd": record.get("cost_usd") or 0.0,
    }
    if record.get("status") != "answered":
        return row | {"status": "call_failed"}
    if not record.get("valid_output"):
        return row | {"status": "invalid"}
    answered = (record.get("response") or {}).get("plan")
    if answered is None:
        return row | {"status": "no_plan"}
    try:
        return row | {"status": "plan"} | _plan_metrics(episode, record, resources)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, StopIteration):
        return row | {"status": "plan"} | UNSCORED  # counted, never fatal after a paid run


def _plan_metrics(episode: dict[str, Any], record: dict[str, Any], resources: BaselineResources) -> dict[str, Any]:
    gold = episode.get("gold") or {}
    scored = record.get("scored") or {}
    recomputed = scored.get("recomputation")
    plan = record["exchanges"][-1]["output"]["plan"]
    meals = _meals(record, resources.ingredient_facts) if "error" not in scored else None
    verification = scored.get("verification") or {}
    over_budget, known_lines_over = budget_state(gold, recomputed, plan)
    own = "meal_structure" in (gold.get("expected_fields") or {}) or any(
        item.get("field") == "meal_structure" for item in _stated(gold)
    )
    # As `full_default` counts them: staples aside.
    names = {
        dish["name"].casefold()
        for meal in record["response"]["plan"]["meals"]
        for dish in meal["dishes"]
        if dish.get("role_id") != "staple"
    }
    return {
        "scoring_error": "error" in scored,
        "allergen_violation": allergen_state(episode, recomputed, plan, resources.checked_allergens),
        "over_budget": over_budget,
        "known_lines_over": known_lines_over,
        "nutrition_out_of_bounds": nutrition_state(gold, meals),
        "gram_coverage": verification.get("gram_coverage"),
        "verifiable_dish_share": verification.get("verifiable_dish_share"),
        "pricing_status": (recomputed or {}).get("pricing_status", "unscored"),
        "price_sgd": (recomputed or {}).get("purchase_total_sgd"),
        "distinct_dishes": len(names),
        "meals": [meal_checks(meal, own) for meal in meals or [] if meal["meal_type"] in ("lunch", "dinner")],
    }


def _mean(values: list[float | None]) -> dict[str, Any]:
    known = [value for value in values if value is not None]
    return {
        "mean": round(sum(known) / len(known), 4) if known else None,
        "known_n": len(known),
        "unknown_n": len(values) - len(known),
    }


def _states(values: list[Any]) -> dict[str, Any]:
    """True over known, with the unknown and not-applicable counts beside it."""
    known = [value for value in values if value is True or value is False]
    hits = sum(known)
    return {
        "numerator_n": hits,
        "known_n": len(known),
        "unknown_n": sum(value is None for value in values),
        NOT_APPLICABLE + "_n": sum(value == NOT_APPLICABLE for value in values),
        "rate": round(hits / len(known), 6) if known else None,
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [row for row in rows if row["status"] == "plan"]
    statuses = Counter(row["status"] for row in rows)
    meals = [meal for row in plans for meal in row["meals"]]
    budget = _states([row["over_budget"] for row in plans])
    budget["unknown_known_lines_over_n"] = sum(row["known_lines_over"] for row in plans)
    recorded = [row for row in rows if row["status"] != "missing"]
    return {
        "remaining_n": len(rows),  # the cases, as in the other aggregates: what small-cell hiding reads
        "plans_n": len(plans),
        "no_plan_n": statuses["no_plan"],
        "call_failed_n": statuses["call_failed"],
        "missing_n": statuses["missing"],
        "invalid_output": {
            "numerator_n": statuses["invalid"],
            "of_all_cases_n": len(rows),
            "rate": round(statuses["invalid"] / len(rows), 6) if rows else None,
        },
        "plans_not_scored_n": sum(row["scoring_error"] for row in plans),
        "hard_constraints": {
            "allergen_violation": _states([row["allergen_violation"] for row in plans]),
            "over_budget": budget,
            "nutrition_out_of_bounds": _states([row["nutrition_out_of_bounds"] for row in plans]),
        },
        "verifiability": {
            "gram_coverage": _mean([row["gram_coverage"] for row in plans]),
            "verifiable_dish_share": _mean([row["verifiable_dish_share"] for row in plans]),
        },
        "quality": {
            "distinct_dishes": _mean([row["distinct_dishes"] for row in plans]),
            "price_sgd": _mean([row["price_sgd"] for row in plans]),
            "pricing_status": dict(sorted(Counter(row["pricing_status"] for row in plans).items())),
        },
        "meal_likeness": {
            "lunch_and_dinner_n": len(meals),
            **{check: _states([meal[check] for meal in meals]) for check in MEAL_CHECKS},
        },
        "cost": {
            "records_n": len(recorded),
            "elapsed_seconds_total": round(sum(row["elapsed_seconds"] for row in recorded), 3),
            "elapsed_seconds_mean": _mean([row["elapsed_seconds"] for row in recorded])["mean"],
            "calls_total": sum(row["calls"] for row in recorded),
            "usd_total": round(sum(row["usd"] for row in recorded), 6),
        },
    }


def _groups(rows: list[dict[str, Any]], pick: Callable[[dict], str]) -> dict[str, dict]:
    return {name: summary([row for row in rows if pick(row) == name]) for name in sorted({pick(row) for row in rows})}


def aggregate(rows: list[dict[str, Any]], *, min_cell_n: int) -> dict[str, Any]:
    """By arm, then overall and by category, language and source, with `heldout_report`'s small-cell hiding."""
    systems = {}
    for system_id in sorted({row["system_id"] for row in rows}):
        own = [row for row in rows if row["system_id"] == system_id]
        systems[system_id] = _withhold_small(
            {
                "overall": summary(own),
                "by_category": _groups(own, lambda row: row["category"]),
                "by_language": _groups(own, lambda row: row["language"]),
                "by_source": _groups(own, lambda row: row["source"]),
                "cells": _groups(own, lambda row: f"{row['category']}|{row['language']}|{row['source']}"),
            },
            min_cell_n,
        )
    return {"note": NOTE, "systems": systems}


def comparison(rows: list[dict[str, Any]], product: str) -> dict[str, Any]:
    """The product against every arm on the three constraints, on the cases known for both."""
    outcomes = [
        CaseOutcome(
            case_ref=row["case"],
            system_id=row["system_id"],
            run=1,
            category=row["category"],
            language=row["language"],
            source=row["source"],
            status="success" if row["status"] == "plan" else "failure",  # neither is read as a failed constraint
            binary_metrics={
                PASSES[name]: not row[name] for name in HARD if row.get(name) is True or row.get(name) is False
            },
        )
        for row in rows
    ]
    specs = [MetricSpec(name=name, kind="binary") for name in PASSES.values()]
    try:
        report = compare(outcomes, product_system_id=product, metrics=specs)
    except ValueError as error:  # no product or no other arm
        return {"not_computed": str(error)}
    return {
        "method": report["method"],
        "note": "Pass rates on the cases where both arms planned, the case states the constraint and both are known. "
        f"The metrics are the passes of {', '.join(HARD)}; bootstrap and McNemar as in heldout_statistics.",
        "product_system_id": product,
        "seed": report["seed"],
        "bootstrap_samples": report["bootstrap_samples"],
        "comparisons": {
            baseline: {name: body["metrics"][name] for name in PASSES.values()}
            for baseline, body in report["comparisons"].items()
        },
    }


def build(
    episodes: list[dict[str, Any]],
    records: dict[str, dict[str, dict]],
    labels: Callable[[dict[str, Any]], tuple[str, str, str]],
    resources: BaselineResources,
    *,
    min_cell_n: int,
    product: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(aggregate, comparison). `records` is arm -> case -> record, as the formal run reads them."""
    rows = []
    for episode in episodes:
        case = episode_id_of(episode)
        category, language, source = labels(episode)
        for system_id, by_case in records.items():
            common = {"case": case, "system_id": system_id, "category": category, "language": language}
            rows.append(common | {"source": source} | case_row(episode, by_case.get(case), resources))
    return aggregate(rows, min_cell_n=min_cell_n), comparison(rows, product)
