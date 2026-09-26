"""Run protocol v3-meal-day-week episodes through the product planner and score them.

Each episode is planned the way the product plans a week: an in-memory database
holds only the episode's drawn pool (release v2.1, imported by the product's own
importer), `WeeklyMealPlanService.generate` plans the household's plan shape with
fixture prices, and a shape-change episode then reads the household's words with
the product's rules (`read_shape_change`), previews the change
(`MealPlanReplanningService.preview_shape`) and confirms it. The final week is
answered in the common output and scored by the strict scorer, plus the v3 checks
below. No model is called and nothing is priced live.

    python -m app.evaluation.meal_day_week_runner --episodes data/evaluation/dev/v3-meal-day-week/episodes \\
        --json-report docs/evaluation/v3-meal-day-week/dev/latest.json \\
        --markdown-report docs/evaluation/v3-meal-day-week/dev/latest.md
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.replanning import AgentReplanInterpreter
from app.agent.shape_change import read_shape_change
from app.api.routes.meal_plans import build_meal_plan_service
from app.core.paths import repository_root
from app.data.allergens import checked_allergens
from app.data.alternatives import options as alternative_options
from app.data.release_v2 import import_release_v2, release_dir
from app.db.base import Base
from app.evaluation.common_output import CommonEpisodeResponse
from app.evaluation.multidish_labels import DAYS, meal_nutrients, slot_roles
from app.evaluation.release_catalog import fixture_products, load_release_catalog
from app.evaluation.strict_success import Catalogs, Check, Tolerances, dish_shares, load_tag_implications, score_episode
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.recipe import clear_planning_pool
from app.schemas.meal_plan import WeeklyMealPlanRequest, WeeklyMealPlanResponse
from app.services.replanning import MealPlanReplanningService, MealPlanReplanValidationError

PROTOCOL = "v3-meal-day-week"
SYSTEM = "P"  # the product path
HOUSEHOLD = 1
# A household that states no time limit: the widest the product request accepts.
NO_TIME_LIMIT = 240
PARAMETERS = {
    "system": "product path: WeeklyMealPlanService.generate, then read_shape_change, preview_shape and confirm",
    "pricing_mode": "fixture",
    "max_cooking_time_minutes_when_unstated": NO_TIME_LIMIT,
    "shape_change_today": "the week's first day, so every day is still ahead",
    "per_day_nutrition": "sent as the product's per_day target",
    "nutrition_tolerance_relative": Tolerances().nutrition_relative,
}


@contextmanager
def product_database(episode: dict):
    """A fresh in-memory product database holding only the episode's drawn pool."""
    pool = set(episode["scenario"]["recipe_candidate_slugs"])
    source = release_dir()
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with tempfile.TemporaryDirectory() as directory:
        for name in ("release_manifest.json", "ingredients.jsonl"):
            shutil.copy(source / name, Path(directory) / name)
        lines = (source / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if json.loads(line)["recipe_id"] in pool]
        (Path(directory) / "recipes.jsonl").write_text("\n".join(kept) + "\n", encoding="utf-8")
        with factory() as session:
            import_release_v2(session, Path(directory))
    clear_planning_pool()  # candidates are cached per database; never reuse another episode's
    try:
        yield factory
    finally:
        clear_planning_pool()
        engine.dispose()


def plan_request(episode: dict) -> WeeklyMealPlanRequest:
    """What the household's profile tells the product: its shape and every stated limit."""
    scenario = episode["scenario"]
    profile = scenario["household_profile"]
    hard = episode["gold"]["applicable_hard_constraints"]
    targets = [
        {
            "metric": band["metric"],
            "scope": "per_day",
            **{k: band[key] for k, key in (("lower", "min"), ("upper", "max")) if band.get(key) is not None},
        }
        for band in hard["nutrition_bands"]
    ]
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": scenario["planning_horizon"]["start_date"],
            "household_size": profile["household_size"],
            "max_cooking_time_minutes": hard["max_cooking_time_minutes"] or NO_TIME_LIMIT,
            "allergens": profile["allergens"],
            "excluded_ingredients": profile["excluded_ingredients"],
            "dietary_preferences": profile["dietary_preferences"],
            "weekly_budget_sgd": hard["budget_sgd"],
            "nutrition_constraints": targets,
            "plan_shape": profile["plan_shape"],
            "pricing_mode": "fixture",
        }
    )


def _product_ids() -> dict[tuple[str, str], str]:
    """(product external id, ingredient) -> the frozen price row's id."""
    ids = {}
    for row in [*fixture_products(), *load_release_catalog().products]:  # a snapshot row wins a tie
        external = row["external_id"].removeprefix("fixture:").split("@")[0]
        ids[external, row["ingredient_id"]] = row["external_id"]
    return ids


def answer(episode: dict, plan: WeeklyMealPlanResponse) -> dict:
    """The product's week in the common output, with the frozen facts' recipe and product ids."""
    # The product's slug for a release recipe ends with its id's hex (`app.data.release_v2.recipe_slug`).
    by_hex = {slug.removeprefix("RCP2_").lower(): slug for slug in episode["scenario"]["recipe_candidate_slugs"]}
    size = plan.household_size
    assignments = [
        {
            "slot_id": f"{DAYS[dish.day_index - 1]}-{dish.meal_type}",
            "role_id": dish.role_id,
            "recipe_id": by_hex[dish.recipe.slug.rsplit("-", 1)[-1]],
            "servings": size * dish.portion_share,
        }
        for dish in plan.days
    ]
    ids = _product_ids()
    shopping = []
    for line in plan.grocery_estimate.items:
        external = line.product.external_id if line.product else None
        shopping.append(
            {
                "ingredient_id": line.ingredient_name,
                "required_quantity": line.required_quantity,
                "unit": line.unit,
                "pantry_deduction": line.pantry_deduction,
                "product_id": ids.get((external, line.ingredient_name), external),
                "packages": line.packages_required,
                "line_cost_sgd": line.purchase_cost_sgd,
            }
        )
    return {
        "episode_id": episode["episode_id"],
        "system_id": SYSTEM,
        "status": "plan",
        "plan": {
            "assignments": assignments,
            "shopping": shopping,
            "total_cost_sgd": plan.grocery_estimate.purchase_total_sgd,
            "within_budget": plan.grocery_estimate.within_weekly_budget,
        },
    }


def _meals(response: dict) -> dict[str, dict[str, str]]:
    meals: dict[str, dict[str, str]] = {}
    for a in (response.get("plan") or {}).get("assignments", []):
        meals.setdefault(a["slot_id"], {})[a["role_id"]] = a["recipe_id"]
    return meals


def _roles(roles: list | None) -> list | None:
    if roles is None:
        return None
    return [(r["role_id"], sorted(r["courses"]), r.get("required", True)) for r in roles]


def _why(error: Exception) -> dict:
    """Why the product refused, from its planning trace: every hard check its tried weeks failed or left open."""
    trace = getattr(error, "trace", None) or {}
    codes: dict[str, int] = {}
    for attempt in trace.get("validation_attempts") or []:
        for check in attempt["checks"]:
            if check["hard"] and check["status"] != "passed":
                key = f"{check['code']} {check['status']}"
                codes[key] = codes.get(key, 0) + 1
    search = trace.get("search") or {}
    return {
        "status": trace.get("status"),
        "evidence": trace.get("evidence"),
        "weeks_tried": len(trace.get("validation_attempts") or []),
        "unmet_checks": dict(sorted(codes.items())),
        "search_exhausted": search.get("exhausted"),
        "input_issues": trace.get("input_issues"),
    }


def run_episode(episode: dict) -> tuple[dict, dict]:
    """The product's answer, and what happened on the way (the initial week, the change it read)."""
    extra: dict = {}
    with product_database(episode) as factory, factory() as session:
        plans = build_meal_plan_service(session, HOUSEHOLD)
        try:
            plan = plans.generate(plan_request(episode))
        except WeeklyPlanSelectionError as error:
            refusal = {"episode_id": episode["episode_id"], "system_id": SYSTEM, "status": "infeasible"}
            return {**refusal, "infeasible": {"conflict": str(error)}}, {"refusal": _why(error)}
        invariants = episode["gold"].get("replan_invariants")
        if not invariants:
            return answer(episode, plan), extra
        extra["before"] = _meals(answer(episode, plan))
        text = episode["scenario"]["shape_change_request"]
        # The conversation's routing (AgentService._change_shape): one-dish events first, then the day, then the shape.
        interpreter = AgentReplanInterpreter()
        intent = None
        if interpreter._event_type(text.lower()) is None:
            intent = read_shape_change(text, plan=plan, day_index=interpreter.day_index(text.lower(), plan))
        extra["understood"] = intent.request.model_dump(mode="json", exclude={"reason"}) if intent else None
        if intent is not None:
            changes = MealPlanReplanningService(
                repository=plans.repository,
                recipe_repository=plans.recipe_repository,
                recommendation_service=plans.recommendation_service,
                grocery_aggregator=plans.grocery_aggregator,
                meal_plan_service=plans,
            )
            try:
                start = date.fromisoformat(episode["scenario"]["planning_horizon"]["start_date"])
                event = changes.preview_shape(plan_id=plan.id, request=intent.request, today=start)
                plan = changes.confirm(plan_id=plan.id, event_id=event.id).plan
            except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
                extra["change_error"] = str(error)
        return answer(episode, plan), extra


def scoring_view(episode: dict) -> dict:
    """The episode as the strict scorer reads it: the final week's slots and their roles.

    Per-day nutrition is scored by `v3_checks`, the strict scorer knowing only
    per-serving and horizon bands; the frozen prices include the fixture file's.
    """
    view = copy.deepcopy(episode)
    final = slot_roles(episode, after_change=True)
    view["scenario"]["planning_horizon"]["slots"] = list(final)
    view["scenario"]["slot_roles"] = final
    view["gold"]["applicable_hard_constraints"]["nutrition_bands"] = []
    return view


def v3_checks(episode: dict, response: dict, extra: dict, catalogs: Catalogs) -> list[Check]:
    """Per-day nutrition and, for a shape change, what was read and what stayed."""
    checks = []
    meals = _meals(response)
    bands = episode["gold"]["applicable_hard_constraints"]["nutrition_bands"]
    tolerance = Tolerances().nutrition_relative
    if bands:
        broken = []
        for day in DAYS:
            day_meals = [
                [(role, catalogs.recipes[recipe]) for role, recipe in dishes.items()]
                for slot, dishes in meals.items()
                if slot.startswith(day)
            ]
            for band in bands:
                if any(dish_shares([role for role, _ in meal]) is None for meal in day_meals):
                    broken.append(f"{day}: a meal has no shares")
                    continue
                total = sum(meal_nutrients(meal, band["metric"]) for meal in day_meals)
                if band.get("min") is not None and total < band["min"] * (1 - tolerance):
                    broken.append(f"{day} {band['metric']} {total:.0f} < {band['min']}")
                if band.get("max") is not None and total > band["max"] * (1 + tolerance):
                    broken.append(f"{day} {band['metric']} {total:.0f} > {band['max']}")
        checks.append(
            Check("nutrition_per_day", "failed" if broken else "passed", "; ".join(broken) or "every day in band")
        )
    invariants = episode["gold"].get("replan_invariants")
    if invariants:
        wanted, read = invariants["shape_change"], extra.get("understood")
        same = read is not None and all(
            (_roles(read[k]) if k == "roles" else read[k]) == (_roles(wanted[k]) if k == "roles" else wanted[k])
            for k in ("meal_type", "roles", "day_indexes")
        )
        checks.append(
            Check("shape_request_understood", "passed" if same else "failed", f"read {read}, wanted {wanted}")
        )
        before = extra.get("before", {})
        moved = [slot for slot in invariants["unchanged_slots"] if before.get(slot) != meals.get(slot)]
        checks.append(
            Check(
                "unchanged_meals_identical",
                "failed" if moved else "passed",
                f"changed: {', '.join(moved)}" if moved else "every other meal is exactly as it was",
            )
        )
        lost = [
            f"{slot}:{role}"
            for slot, roles in invariants["kept_dishes"].items()
            for role in roles
            if (before.get(slot) or {}).get(role) != (meals.get(slot) or {}).get(role)
        ]
        if invariants["kept_dishes"]:
            checks.append(
                Check(
                    "kept_dishes_identical",
                    "failed" if lost else "passed",
                    f"replaced: {', '.join(lost)}" if lost else "the dishes left in the meal are the ones it had",
                )
            )
        if extra.get("change_error"):
            checks.append(Check("shape_change_applied", "failed", extra["change_error"]))
    return checks


def _secondary(episode: dict, response: dict) -> dict:
    """Measures strict success does not score: variety, meal fit and cost."""
    plan = response.get("plan")
    if not plan:
        return {}
    recipes = load_release_catalog().by_slug
    dishes = plan["assignments"]
    fit = sum(a["slot_id"].split("-", 1)[1] in recipes[a["recipe_id"]]["meal_types"] for a in dishes)
    return {
        "dishes": len(dishes),
        "distinct_recipes": len({a["recipe_id"] for a in dishes}),
        "meal_fit": f"{fit}/{len(dishes)}",
        "total_cost_sgd": plan["total_cost_sgd"],
    }


def scorer_catalogs(episode: dict) -> Catalogs:
    """The frozen facts as this household cooks them.

    An "A or B" line (`data/ingredients/alternatives.json`) is its first option the
    household can eat and buy, the rule the product states in `app.planning.alternatives`;
    this is the scorer's own copy of it. The frozen prices include the fixture file's.
    """
    catalog = load_release_catalog()
    profile = episode["scenario"]["household_profile"]
    banned, excluded = set(profile["allergens"]), set(profile["excluded_ingredients"])
    allergens = {row["normalized_name"]: set(row["allergens"]) for row in catalog.ingredients}
    products = [*catalog.products, *fixture_products()]
    priced = {row["ingredient_id"] for row in products}

    def cooked(name: str) -> str:
        options = alternative_options().get(name, ())
        return next(
            (o for o in options if o in priced and o not in excluded and not banned & allergens.get(o, set())), name
        )

    recipes = [
        {**r, "ingredients": [{**line, "ingredient": cooked(line["ingredient"])} for line in r["ingredients"]]}
        for r in catalog.recipes
    ]
    return Catalogs.build(
        recipes,
        products,
        catalog.ingredients,
        tag_implications=load_tag_implications(repository_root() / "data/recipes/dietary-tag-implications.json"),
        checked_allergens=checked_allergens(),
    )


def evaluate(episodes: list[dict]) -> dict:
    rows = []
    for episode in episodes:
        catalogs = scorer_catalogs(episode)
        response, extra = run_episode(episode)
        score = score_episode(scoring_view(episode), CommonEpisodeResponse.model_validate(response), catalogs)
        if episode["gold"]["class"] == "feasible" and response["status"] == "plan":
            score.checks.extend(v3_checks(episode, response, extra, catalogs))
        rows.append(
            {
                "episode_id": episode["episode_id"],
                "category": episode["category"],
                "language": episode["language"],
                "class": episode["gold"]["class"],
                "answered": response["status"],
                "strict_success": score.strict_success,
                "failed": score.failed_codes,
                "indeterminate": score.indeterminate_codes,
                "details": {c.code: c.detail for c in score.checks if c.blocks_success},
                **({"conflict": response["infeasible"]["conflict"]} if response["status"] == "infeasible" else {}),
                **{k: v for k, v in extra.items() if k in {"understood", "change_error", "refusal"}},
                **_secondary(episode, response),
            }
        )
    by_category = {}
    for category in dict.fromkeys(r["category"] for r in rows):
        mine = [r for r in rows if r["category"] == category]
        by_category[category] = {
            "strict_success": f"{sum(r['strict_success'] for r in mine)}/{len(mine)}",
            "failure_mechanisms": dict(
                sorted({c: sum(c in r["failed"] for r in mine) for r in mine for c in r["failed"]}.items())
            ),
        }
    return {
        "protocol": PROTOCOL,
        "system": SYSTEM,
        "parameters": PARAMETERS,
        "summary": {
            "strict_success": f"{sum(r['strict_success'] for r in rows)}/{len(rows)}",
            "by_category": by_category,
        },
        "episodes": rows,
    }


def code_revision() -> str:
    """The commit the report was computed at; `+dirty` when the backend or the episodes differ from it."""
    root = repository_root()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "backend", "data"], cwd=root, capture_output=True, text=True, check=True
    )
    return head.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")


def markdown(report: dict) -> str:
    lines = [
        f"# Protocol {PROTOCOL}: {report['episode_set']}",
        "",
        "Generated by `python -m app.evaluation.meal_day_week_runner`: the product path, fixture prices, no model "
        "calls. **Developer episodes: not held-out evidence.**",
        "",
        "The code revision it ran at is `code_revision` in `latest.json` beside this file.",
        "",
        "| Category | Strict success | Failure mechanisms |",
        "| --- | ---: | --- |",
    ]
    for category, s in report["summary"]["by_category"].items():
        mechanisms = ", ".join(f"{k} {v}" for k, v in s["failure_mechanisms"].items()) or "-"
        lines.append(f"| {category} | {s['strict_success']} | {mechanisms} |")
    lines += [
        f"| **all** | **{report['summary']['strict_success']}** | |",
        "",
        "| Episode | Category | Lang | Class | Answered | Success | Failed checks | Dishes | Distinct | Meal fit "
        "| Cost |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for r in report["episodes"]:
        lines.append(
            f"| {r['episode_id']} | {r['category']} | {r['language']} | {r['class']} | {r['answered']} "
            f"| {'yes' if r['strict_success'] else 'no'} | {', '.join(r['failed']) or '-'} | {r.get('dishes', '-')} "
            f"| {r.get('distinct_recipes', '-')} | {r.get('meal_fit', '-')} | {r.get('total_cost_sgd', '-')} |"
        )
    lines += ["", "## Parameters", ""]
    lines += [f"- {key}: {value}" for key, value in report["parameters"].items()]
    lines += ["", "Counts only, no rates (ADR-0028).", "", "## Inputs", ""]
    lines += [f"- `{path}`: `{digest}`" for path, digest in sorted(report["inputs"].items())]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()
    root = repository_root()
    files = sorted(args.episodes.glob("*.json"))
    report = evaluate([json.loads(path.read_text(encoding="utf-8")) for path in files])
    report["episode_set"] = "held-out set" if "heldout" in args.episodes.parts else "developer set"
    report["code_revision"] = code_revision()
    inputs = {
        str(path.resolve().relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    for fixed in (
        "data-engineering/data/release/v2.1/recipes.jsonl",
        "data-engineering/data/release/v2.1/ingredients.jsonl",
        "data/products/fairprice-v2-snapshot.json",
        "data/fixtures/fairprice-products.json",
    ):
        inputs[fixed] = hashlib.sha256((root / fixed).read_bytes()).hexdigest()
    report["inputs"] = inputs
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.json_report.write_text(text, encoding="utf-8", newline="\n")
    args.markdown_report.write_text(markdown(report), encoding="utf-8", newline="\n")
    print(f"{report['summary']['strict_success']} strict successes")
    for category, s in report["summary"]["by_category"].items():
        print(f"  {category}: {s['strict_success']} {s['failure_mechanisms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
