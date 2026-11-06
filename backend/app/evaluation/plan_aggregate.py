"""The formal run's `plan` aggregate: the metric table of 02-baselines section 6, from each case's local record.

Computed after every arm has finished, from `response`, `scored` and the final exchange of each record (a held-out
run keeps all three in `.local/evaluation/`), so it can change nothing an arm saw. Only counts and means reach `--out`.

A hard constraint is one of four states on a plan: violated, within, `unknown` (stated, but this plan cannot be
judged) or `not_applicable` (the case states none). Arms know different amounts, so a rate over known alone leans
against the one that knows less: `violation_rate` is violations over known, and beside it stand `violation_rate_lower`
(violations over applicable) and `violation_rate_upper` ((violations + unknown) over applicable). Applicable is known
plus unknown: the arm's plans on cases stating the constraint, the same rule for every arm. `stated_cases_n` is every
case stating it, which is the same number for every arm, and `stated_without_plan_n` those where the arm gave no plan.

- `allergen_violation`: the gold's allergens against `scored.recomputation`, not `scored.allergen_safe`, which reads
  only the development gold and a stated household and so is always true on the held-out interchange. An allergen
  the plan holds is a violation even with lines unknown. One member's allergen is judged per dish, the same way for
  every arm: the dish holding it is unknown only if its `not_for` names every member who avoids it (counted as
  `unknown_marked_not_for_n`; a name the gold does not know may be that member under another id), and otherwise a
  violation. Only the product fills `not_for`, as a baseline's plan has no way to say it. Incomplete allergens, or an
  allergen no check covers, are unknown. Names are read as the runtime vocabulary or through `allergen_keywords`.
- `over_budget`: the recomputed whole-package total (no total, as with `needs_data` or `limit_exceeded`: unknown)
  against `weekly_budget_sgd`, or the development `budget_sgd`. A week or trip budget on a request of n seven-day
  periods allows n budgets; the periods come from the case's horizon, and only a case stating none reads the plan's own
  span. Whole cents, no tolerance. The total is one consolidated purchase, so past seven days it can prove over budget
  only: at or under n budgets is unknown. So is an over total with a pantry stated, as the recomputation buys
  everything. `unknown_known_lines_over_n` counts unknowns whose priced lines alone already pass.
- `nutrition_out_of_bounds`: `sodium_limit_mg` per person on each meal or each day, with `dinner_sodium_share` on the
  dinners under a daily limit; the development `nutrition_bands` through `strict_success`, per the arm's own serving.
  A real excess is reported even when another meal cannot be computed; any other scope, or a limit enabled with no
  number, is unknown.

`meal_likeness` counts lunches and dinners, with the checks of `full_default`: the filling core and the non-meal dish
read the catalog's tags through `recipe_reference`, so a dish naming no catalog recipe is unknown, and the energy floor
reads the recomputed nutrition, so a line without facts is unknown. A case stating its own `meal_structure` is
`not_applicable` for the filling core, which is the full default's. Per person always divides by the case's household
(`household_size`, the `members`, the development profile), never an arm's own `servings`; no household stated, or an
`attendance` stated, leaves per-person sodium and the energy floor unknown. A plan's meal checks are rates over the
meals it has, so `coverage` sets planned days and meals against the requested ones, as a short plan is also cheaper.

A count of cases is not enough for small-cell hiding when a rate rests on few of them: a rate, mean or bound on fewer
than `min_cell_n` known cases (`known_cases_n` for the meal checks), or a paired block on fewer than that many pairs, is
withheld with its counts of unknown and not applicable kept, and a lone small value of a dimension takes the smallest
other with it. Counts name their direction: `violations_n` under `hard_constraints`, `passes_n` under `meal_likeness`.
`calls_counted_as` says what an arm's `calls_total` counts: its ledger meter is one a message for the product arms,
whatever each sent, and one a model call for the others. A fault in one metric leaves that metric unknown and the rest
of the plan standing, counted in `plans_not_scored_n`.
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
from app.evaluation.baseline_recomputation import (
    NUTRIENT_FIELDS,
    allergen_keywords,
    dish_nutrition_per_serving,
    line_allergens,
)
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
NOTE = (
    "Rates are over known; the lower and upper bounds are over applicable (known + unknown), with the unknown and "
    "not_applicable counts beside them. A value resting on fewer known cases than the minimum is withheld."
)
FAULTS = (AttributeError, KeyError, IndexError, TypeError, ValueError, StopIteration)
KEPT_WHEN_WITHHELD = {
    "known_n",
    "known_cases_n",
    "unknown_n",
    NOT_APPLICABLE + "_n",
    "applicable_n",
    "stated_cases_n",
    "stated_without_plan_n",
}
UNKNOWN_DETAILS = ("unknown_known_lines_over_n", "unknown_marked_not_for_n")
SECTIONS = ("hard_constraints", "verifiability", "quality", "meal_likeness", "coverage")
PAIR_COUNTS = ("paired_n", "product_unpaired_n", "baseline_unpaired_n")


def _stated(gold: dict[str, Any]) -> list[dict[str, Any]]:
    """The gold's constraints, and what an intent gold states only in its expected fields."""
    rows = list(gold.get("hard_constraints") or [])
    named = {row.get("field") for row in rows}
    expected = gold.get("expected_fields") or {}
    for name in (
        "allergens",
        "members",
        "weekly_budget_sgd",
        "sodium_limit_mg",
        "sodium_limit_enabled",
        "household_size",
        "horizon_days",
        "meal_types",
        "attendance",
    ):
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


def requested_allergens(episode: dict[str, Any]) -> dict[str, frozenset[str] | None]:
    """Allergen to avoid -> who: None for the whole household, else member ids (empty: a member the gold does not name).
    Development episodes as `score` reads them."""
    gold = episode.get("gold") or {}
    wanted: dict[str, frozenset[str] | None] = {}

    def add(name: str, who: frozenset[str] | None) -> None:
        key = name.strip().casefold()
        held = wanted.get(key, frozenset())
        wanted[key] = None if who is None or held is None else held | who

    for row in _stated(gold):
        if row.get("field") == "allergens" and row.get("operator") != "include":
            value = row.get("value")
            who = None
            if row.get("scope") == "member":
                who = frozenset(str(member).casefold() for member in row.get("target_member_ids") or [])
            for name in [value] if isinstance(value, str) else list(value or []):
                add(name, who)
        elif row.get("field") == "members":
            for person in row.get("value") or []:
                for name in person.get("allergens") or []:
                    add(name, frozenset({str(person.get("member_id")).casefold()}))
    development = (gold.get("applicable_hard_constraints") or {}).get("allergens_absent")
    if development is None:
        household = episode.get("scenario", {}).get("household_profile") or {}
        development = household.get("allergens") or []
    for name in development:
        add(name, None)
    return wanted


def _member_ids(gold: dict[str, Any]) -> set[str]:
    return {
        str(person.get("member_id")).casefold()
        for row in _stated(gold)
        if row.get("field") == "members"
        for person in row.get("value") or []
    }


def _covers(not_for: Iterable[str], targets: set[str], ids: set[str]) -> bool:
    """Whether `not_for` names every target. The gold's ids need not be the plan's names, so a name the gold does not
    know may be a target under another id; one it knows as someone else is not."""
    marked = {str(name).casefold() for name in not_for}
    return bool(marked) and len(marked - ids) >= len(targets - marked)


def allergen_state(
    episode: dict[str, Any],
    recomputed: dict | None,
    dishes: list[tuple[set[str], list[str]]] | None,
    checked: Iterable[str],
) -> tuple[Any, bool]:
    """(state, whether it is unknown because the dishes holding it are marked `not_for` its members).

    `dishes` is each dish's allergens and `not_for`; None when they cannot be read, which leaves a member's allergen
    unknown and a household's still a violation."""
    wanted = requested_allergens(episode)
    if not wanted:
        return NOT_APPLICABLE, False
    if recomputed is None:
        return None, False
    vocabulary = {name.lower() for name in checked}
    everyone: set[str] = set()
    members: dict[str, set[str]] = {}
    uncovered = False
    for name, who in wanted.items():
        found = {name} if name in vocabulary else allergen_keywords(name)
        uncovered |= not found
        for allergen in found:
            if who is None:
                everyone.add(allergen)
            else:
                members.setdefault(allergen, set()).update(who)
    present = {name.lower() for name in recomputed["allergens"]}
    if everyone & present:
        return True, False
    held = members.keys() & present
    if not held:
        return (None if uncovered or not recomputed["allergens_complete"] else False), False
    if dishes is None:
        return None, False
    ids = _member_ids(episode.get("gold") or {}).union(*members.values())
    marked = False
    for allergens, not_for in dishes:
        hits = held & allergens
        if hits:
            if not _covers(not_for, set().union(*(members[name] for name in hits)), ids):
                return True, False
            marked = True
    return None, marked


def _dish_allergens(record: dict[str, Any], facts: dict) -> list[tuple[set[str], list[str]]]:
    """Each dish's allergens, by the recomputation's own reading of its lines, with its `not_for`."""
    planned = [dish for meal in record["exchanges"][-1]["output"]["plan"]["meals"] for dish in meal["dishes"]]
    return [
        (
            {
                name.lower()
                for line in scored["mappings"]
                for name in line_allergens(IngredientMapping(**line), facts)[0]
            },
            dish.get("not_for") or [],
        )
        for dish, scored in zip(planned, record["scored"]["dishes"], strict=True)
    ]


def requested_slots(episode: dict[str, Any]) -> tuple[int | None, int | None]:
    """(days, meals) the case asks for; None where it does not say."""
    slots = ((episode.get("scenario") or {}).get("planning_horizon") or {}).get("slots")
    if slots:  # `mon-dinner`
        return len({slot.split("-")[0] for slot in slots}), len(slots)
    values = {row.get("field"): row.get("value") for row in _stated(episode.get("gold") or {})}
    days = episode.get("horizon_days") or values.get("horizon_days")
    types = values.get("meal_types")
    return days, days * len(types) if days and types else None


def budget_state(
    gold: dict[str, Any], recomputed: dict | None, plan: dict | None, requested_days: int | None = None
) -> tuple[Any, bool]:
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
    span = requested_days
    if not span:
        days = sorted(date.fromisoformat(meal["date"]) for meal in plan["meals"])
        span = (days[-1] - days[0]).days + 1
    periods = ceil(span / 7)
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


def _people(episode: dict[str, Any]) -> float | None:
    """The people at a meal, as the case states them."""
    rows = _stated(episode.get("gold") or {})
    # ponytail: attendance makes per-person unknown; read `absent_member_ids` per slot if those cases must be judged.
    if any(row.get("field") == "attendance" for row in rows):
        return None
    for row in rows:
        if row.get("field") == "household_size" and _number(row):
            return _number(row)
    for row in rows:
        if row.get("field") == "members" and row.get("value"):
            return float(len(row["value"]))
    size = ((episode.get("scenario") or {}).get("household_profile") or {}).get("household_size")
    return float(size) if size else None


def _meals(record: dict[str, Any], facts: dict, people: float | None) -> list[dict]:
    """Each planned meal with its date, per-person nutrition (None when a line has no facts or the case states no
    household) and dishes' tags."""
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
        per_person = None
        if people and all(dish["total"] for dish in dishes):
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
    gold = episode.get("gold") or {}
    stated = {
        "allergen_violation": bool(requested_allergens(episode)),
        "over_budget": budget_state(gold, None, None)[0] != NOT_APPLICABLE,
        "nutrition_out_of_bounds": nutrition_state(gold, None) != NOT_APPLICABLE,
    }
    if record is None:
        return {"status": "missing", "stated": stated}
    row: dict[str, Any] = {
        "stated": stated,
        "elapsed_seconds": record.get("elapsed_seconds") or 0.0,
        "calls": record.get("calls") or 0,
        "usd": record.get("cost_usd") or 0.0,
    }
    if record.get("status") != "answered":
        return row | {"status": "call_failed"}
    if not record.get("valid_output"):
        return row | {"status": "invalid"}
    if (record.get("response") or {}).get("plan") is None:
        return row | {"status": "no_plan"}
    return row | {"status": "plan"} | _plan_metrics(episode, record, resources)


def _plan_metrics(episode: dict[str, Any], record: dict[str, Any], resources: BaselineResources) -> dict[str, Any]:
    gold = episode.get("gold") or {}
    scored = record.get("scored") or {}
    recomputed = scored.get("recomputation")
    faults: list[bool] = []

    def safe(compute: Callable[[], Any], fallback: Any = None) -> Any:
        """A fault costs that metric alone, counted, and is never fatal after a paid run."""
        try:
            return compute()
        except FAULTS:
            faults.append(True)
            return fallback

    facts = resources.ingredient_facts
    failed = "error" in scored
    plan = safe(lambda: record["exchanges"][-1]["output"]["plan"])
    meals = None if failed else safe(lambda: _meals(record, facts, _people(episode)))
    dishes = None if failed else safe(lambda: _dish_allergens(record, facts))
    days, meal_count = safe(lambda: requested_slots(episode), (None, None))
    allergen, marked = safe(
        lambda: allergen_state(episode, recomputed, dishes, resources.checked_allergens), (None, False)
    )
    over_budget, known_lines_over = safe(lambda: budget_state(gold, recomputed, plan, days), (None, False))
    nutrition = safe(lambda: nutrition_state(gold, meals))
    own = "meal_structure" in (gold.get("expected_fields") or {}) or any(
        item.get("field") == "meal_structure" for item in _stated(gold)
    )
    # As `full_default` counts them: staples aside.
    distinct = safe(
        lambda: len(
            {
                dish["name"].casefold()
                for meal in record["response"]["plan"]["meals"]
                for dish in meal["dishes"]
                if dish.get("role_id") != "staple"
            }
        )
    )
    planned_days = safe(lambda: len({meal["date"] for meal in plan["meals"]}))
    planned_meals = safe(lambda: len({(meal["date"], meal["meal_type"]) for meal in plan["meals"]}))
    checks = safe(
        lambda: [meal_checks(meal, own) for meal in meals or [] if meal["meal_type"] in ("lunch", "dinner")], []
    )
    verification = scored.get("verification") or {}
    return {
        "scoring_error": failed or bool(faults),
        "allergen_violation": allergen,
        "marked_not_for": marked,
        "over_budget": over_budget,
        "known_lines_over": known_lines_over,
        "nutrition_out_of_bounds": nutrition,
        "gram_coverage": verification.get("gram_coverage"),
        "verifiable_dish_share": verification.get("verifiable_dish_share"),
        "pricing_status": (recomputed or {}).get("pricing_status", "unscored"),
        "price_sgd": (recomputed or {}).get("purchase_total_sgd"),
        "distinct_dishes": distinct,
        "planned_days": planned_days,
        "requested_days": days,
        "planned_meals": planned_meals,
        "requested_meals": meal_count,
        "meals": checks,
    }


def _mean(values: list[float | None]) -> dict[str, Any]:
    known = [value for value in values if value is not None]
    return {
        "mean": round(sum(known) / len(known), 4) if known else None,
        "known_n": len(known),
        "unknown_n": len(values) - len(known),
    }


def _known(value: Any) -> bool:
    return value is True or value is False


def _states(values: list[Any], noun: str, plural: str) -> dict[str, Any]:
    """True over known and its bounds over applicable, named for what True means, with the other counts beside it."""
    known = [value for value in values if _known(value)]
    hits = sum(known)
    unknown = sum(value is None for value in values)
    applicable = len(known) + unknown
    return {
        f"{plural}_n": hits,
        "known_n": len(known),
        "unknown_n": unknown,
        NOT_APPLICABLE + "_n": sum(value == NOT_APPLICABLE for value in values),
        "applicable_n": applicable,
        f"{noun}_rate": round(hits / len(known), 6) if known else None,
        f"{noun}_rate_lower": round(hits / applicable, 6) if applicable else None,
        f"{noun}_rate_upper": round((hits + unknown) / applicable, 6) if applicable else None,
    }


def _hard(rows: list[dict[str, Any]], plans: list[dict[str, Any]], name: str) -> dict[str, Any]:
    block = _states([row[name] for row in plans], "violation", "violations")
    block["stated_cases_n"] = sum(row["stated"][name] for row in rows)
    block["stated_without_plan_n"] = block["stated_cases_n"] - block["applicable_n"]
    return block


def _meal_check(plans: list[dict[str, Any]], check: str) -> dict[str, Any]:
    block = _states([meal[check] for row in plans for meal in row["meals"]], "pass", "passes")
    block["known_cases_n"] = sum(any(_known(meal[check]) for meal in row["meals"]) for row in plans)
    return block


def _coverage(plans: list[dict[str, Any]], unit: str) -> dict[str, Any]:
    """Planned against requested, where both are known."""
    pairs = [(row[f"planned_{unit}"], row[f"requested_{unit}"]) for row in plans]
    known = [(planned, requested) for planned, requested in pairs if planned is not None and requested is not None]
    return {
        "known_n": len(known),
        "unknown_n": len(pairs) - len(known),
        "short_n": sum(planned < requested for planned, requested in known),
        "exact_n": sum(planned == requested for planned, requested in known),
        "over_n": sum(planned > requested for planned, requested in known),
        "planned_mean": _mean([planned for planned, _ in known])["mean"],
        "requested_mean": _mean([requested for _, requested in known])["mean"],
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [row for row in rows if row["status"] == "plan"]
    statuses = Counter(row["status"] for row in rows)
    meals = [meal for row in plans for meal in row["meals"]]
    allergen = _hard(rows, plans, "allergen_violation")
    allergen["unknown_marked_not_for_n"] = sum(row["marked_not_for"] for row in plans)
    budget = _hard(rows, plans, "over_budget")
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
            "allergen_violation": allergen,
            "over_budget": budget,
            "nutrition_out_of_bounds": _hard(rows, plans, "nutrition_out_of_bounds"),
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
            **{check: _meal_check(plans, check) for check in MEAL_CHECKS},
        },
        "coverage": {"days": _coverage(plans, "days"), "meals": _coverage(plans, "meals")},
        "cost": {
            "records_n": len(recorded),
            "elapsed_seconds_total": round(sum(row["elapsed_seconds"] for row in recorded), 3),
            "elapsed_seconds_mean": _mean([row["elapsed_seconds"] for row in recorded])["mean"],
            "calls_total": sum(row["calls"] for row in recorded),
            "usd_total": round(sum(row["usd"] for row in recorded), 6),
        },
    }


def _blocks(body: dict[str, Any]) -> dict[str, dict]:
    """Every value resting on its own known count, by path."""
    return {
        f"{section}.{name}": block
        for section in SECTIONS
        for name, block in body[section].items()
        if isinstance(block, dict) and "known_n" in block
    }


def _resting_on(block: dict[str, Any]) -> int:
    return block.get("known_cases_n", block["known_n"])


def _hide(block: dict[str, Any], minimum: int) -> None:
    for key in set(block) - KEPT_WHEN_WITHHELD:
        del block[key]
    block["withheld"] = f"fewer than {minimum} known cases"


def _guard(body: dict[str, Any], minimum: int) -> dict[str, Any]:
    """Withhold what rests on too few known cases, whatever the count of cases (the module docstring)."""
    for block in _blocks(body).values():
        if block["unknown_n"] < minimum:
            for detail in UNKNOWN_DETAILS:
                block.pop(detail, None)
        if _resting_on(block) < minimum:
            _hide(block, minimum)
    if body["cost"]["records_n"] < minimum:
        body["cost"] = {"records_n": body["cost"]["records_n"], "withheld": f"fewer than {minimum} records"}
    return body


def _groups(rows: list[dict[str, Any]], pick: Callable[[dict], str], minimum: int) -> dict[str, dict]:
    groups = {
        name: _guard(summary([row for row in rows if pick(row) == name]), minimum)
        for name in sorted({pick(row) for row in rows})
    }
    # One value hidden: the overall total minus the shown ones gives it back, so the smallest other goes with it.
    for path in {path for body in groups.values() for path in _blocks(body)}:
        blocks = [_blocks(body)[path] for body in groups.values()]
        shown = [block for block in blocks if "withheld" not in block]
        hidden = [block for block in blocks if "withheld" in block and _resting_on(block) > 0]
        if len(hidden) == 1 and shown:
            _hide(min(shown, key=_resting_on), minimum)
    return groups


def aggregate(rows: list[dict[str, Any]], *, min_cell_n: int, product: str) -> dict[str, Any]:
    """By arm, then overall and by category, language and source, with `heldout_report`'s small-cell hiding."""
    systems = {}
    for system_id in sorted({row["system_id"] for row in rows}):
        own = [row for row in rows if row["system_id"] == system_id]
        systems[system_id] = _withhold_small(
            {
                "overall": _guard(summary(own), min_cell_n),
                "by_category": _groups(own, lambda row: row["category"], min_cell_n),
                "by_language": _groups(own, lambda row: row["language"], min_cell_n),
                "by_source": _groups(own, lambda row: row["source"], min_cell_n),
                "cells": _groups(own, lambda row: f"{row['category']}|{row['language']}|{row['source']}", min_cell_n),
            },
            min_cell_n,
        )
        is_product = system_id == product or system_id.startswith(f"{product}/")
        systems[system_id]["calls_counted_as"] = "messages" if is_product else "model_calls"
    return {"note": NOTE, "systems": systems}


def _pair(body: dict[str, Any], minimum: int) -> dict[str, Any]:
    if body["paired_n"] >= minimum:
        return body
    return {key: body[key] for key in PAIR_COUNTS} | {"withheld": f"fewer than {minimum} paired cases"}


def comparison(rows: list[dict[str, Any]], product: str, *, min_cell_n: int) -> dict[str, Any]:
    """The product against every arm on the three constraints, on the cases known for both, withheld under
    `min_cell_n` pairs."""
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
            baseline: {name: _pair(body["metrics"][name], min_cell_n) for name in PASSES.values()}
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
    return aggregate(rows, min_cell_n=min_cell_n, product=product), comparison(rows, product, min_cell_n=min_cell_n)
