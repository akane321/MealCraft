"""The full meal structure (ADR-0070) on fixed households: is every lunch and dinner a real meal?

Five households are planned with the full default through `WeeklyMealPlanService.generate`, on the whole release
catalog at fixture prices, as `app.evaluation.plan_timing` plans it. No model is called and no held-out data is
read. For every lunch and dinner the report checks: a filling core (a protein main and a staple, or a dish that
carries its staple), no non-meal dish, no protein source twice among the mains, the energy floor per serving,
dish counts as the table says give or take the one allowed move, and the staple on the list. For every dish:
perishables within their days after the trip, and the kitchen's equipment. A plan of two trips buys each line
on the trip whose days use it.

Wall time differs by machine, so it is printed and never written to `latest.*` (CI diffs them); `--timing-report`
writes it beside them on request. The variety pass always runs every start (ADR-0080), so the plans do not
depend on the machine either.

    python -m app.evaluation.full_default [--timing-report]
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
from collections import Counter
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.routes.meal_plans import build_meal_plan_service
from app.data import meal_structure
from app.data.household_reference import basic_seasonings, hpb
from app.data.release_v2 import release_dir
from app.evaluation.meal_day_week_runner import HOUSEHOLD as HOUSEHOLD_ID
from app.evaluation.meal_day_week_runner import product_database
from app.models.recipe import Recipe, RecipeIngredient
from app.planning.grocery_estimator import not_purchased
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.schemas.meal_plan import MEAL_ORDER, WeeklyMealPlanRequest, default_plan_shape
from app.schemas.planning_v2 import NON_MEAL_ROLES

START = "2027-01-03"  # a Sunday
WEEKEND = ["saturday", "sunday"]


def _rule(text: str, **fields) -> dict:
    return {"source_text": text, "restatement": "-", **fields}


# Fixed households (servings are the HPB defaults of `app.data.household_reference` for each member's band).
CASES = [
    {
        "case": "one-adult",
        "about": "One adult at the HPB defaults; 7 days, no budget.",
        "request": {"household_size": 1, "day_count": 7},
        "household": {"members": [{"name": "Alex", "servings": 1.0}]},
    },
    {
        "case": "four-with-vegetarian",
        "about": (
            "Two adults, a teen and a child, Ann vegetarian (her own diet, not the household's: ADR-0071's "
            "shared-dish model); a grandparent joins weekend dinners, so those dinners are for five."
        ),
        "request": {"household_size": 4, "day_count": 7},
        "household": {
            "members": [
                {"name": "Ann", "servings": 0.88, "dietary_preferences": ["vegetarian"]},
                {"name": "Ben", "servings": 1.12},
                {"name": "Kai", "servings": 1.35},
                {"name": "Mei", "servings": 0.73},
                {"name": "Grandma", "servings": 0.81, "default_present": False},
            ],
            "presence_rules": [
                _rule(
                    "Grandma joins us for dinner on weekends",
                    member_name="Grandma",
                    present=True,
                    weekdays=WEEKEND,
                    meal_types=["dinner"],
                )
            ],
        },
    },
    {
        "case": "six-tight-budget",
        "about": (
            "Six adults on a tight weekly budget (S$420, chosen once on developer runs); it planned when set, so a "
            "refusal fails."
        ),
        "request": {"household_size": 6, "day_count": 7, "weekly_budget_sgd": 420.0},
        "household": {"members": [{"name": f"Adult {n}", "servings": 1.0} for n in range(1, 7)]},
    },
    {
        "case": "two-no-oven-ten-days",
        "about": "Two adults with no oven; 10 days, so two shopping trips (before day 1 and day 8).",
        "request": {"household_size": 2, "day_count": 10},
        "household": {
            "members": [{"name": "Lin", "servings": 0.88}, {"name": "Raj", "servings": 1.12}],
            "missing_equipment": ["oven"],
        },
    },
    {
        "case": "seven-with-young-children",
        "about": (
            "Two adults, three toddlers and two children: seven at the table on about 4.8 portions, so dinner is "
            "the 7+ row (3 protein mains, 2 vegetable dishes) by people present, not by portions; 7 days."
        ),
        "request": {"household_size": 7, "day_count": 7},
        "household": {
            "members": [
                {"name": "Ann", "servings": 0.88},
                {"name": "Ben", "servings": 1.12},
                {"name": "Tod 1", "servings": 0.43},
                {"name": "Tod 2", "servings": 0.47},
                {"name": "Tod 3", "servings": 0.43},
                {"name": "Kid 1", "servings": 0.7},
                {"name": "Kid 2", "servings": 0.75},
            ]
        },
    },
]

# The ADR-0070 dish table, written out here rather than read from the planner, so a bug in the planner's
# own helpers shows as a failed check: (most people at dinner, protein mains, vegetable dishes).
DINNER_ROWS = [(2, 1, 1), (4, 2, 1), (6, 2, 2), (None, 3, 2)]


def expected_dishes(meal: str, people: int) -> Counter:
    """The dishes of a full-default meal by kind (`_kind` of its role ids) with `people` at it."""
    if meal == "breakfast":
        return Counter(main=1)
    if meal == "lunch":
        return Counter(main=1, vegetable=1, staple=1)
    mains, vegetables = next((m, v) for top, m, v in DINNER_ROWS if top is None or people <= top)
    return Counter(main=mains, vegetable=vegetables, soup=1, staple=1)


def _equipment_met(needs, missing) -> bool:
    """Every any-of group of the recipe's equipment has an item the kitchen has (written out, as above)."""
    return not missing or all(set(group) - set(missing) for group in needs or ())


def people_present(household, day: date, meal: str) -> int:
    """The members home for a meal: each usually-home member, then each rule naming the weekday and meal, the
    last one for a member winning (written out, as above, rather than the planner's `slot_people`)."""
    home = {member.name: member.default_present for member in household.members}
    weekday = day.strftime("%A").lower()
    for rule in household.presence_rules:
        if (not rule.weekdays or weekday in rule.weekdays) and (not rule.meal_types or meal in rule.meal_types):
            home[rule.member_name] = rule.present
    return sum(home.values())


def _kind(role_id: str) -> str:
    """ "main-2" -> "main": the kind of dish a role id names."""
    return role_id.split("-")[0]


def _carries_staple(recipe) -> bool:
    """A one-bowl dish, or one tagged as holding its staple (ADR-0070 section 2)."""
    return recipe.meal_role == "one_bowl" or recipe.contains_staple is True


def request_for(case: dict) -> WeeklyMealPlanRequest:
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": START,
            "pricing_mode": "fixture",
            "max_cooking_time_minutes": 240,
            "plan_shape": default_plan_shape().model_dump(mode="json"),
            **case["request"],
            "household": case["household"],
        }
    )


def _recipes(session, slugs) -> dict[str, Recipe]:
    statement = (
        select(Recipe)
        .where(Recipe.slug.in_(sorted(slugs)))
        .options(selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient))
    )
    return {recipe.slug: recipe for recipe in session.scalars(statement).unique()}


def check_week(week: dict, request: WeeklyMealPlanRequest, recipes: dict[str, Recipe]) -> dict:
    """The real-meal checks of one planned week (`week` is the plan response as JSON)."""
    floor = {meal: share * hpb()["adult_reference"]["energy_kcal"] for meal, share in _floors().items()}
    basics = set(basic_seasonings())
    missing = set(request.household.missing_equipment if request.household else [])
    listed: dict[int | None, set[str]] = {}
    for line in week["grocery_estimate"]["items"]:
        listed.setdefault(line.get("shopping_trip"), set()).add(line["ingredient_name"])
    trips = sorted(trip for trip in listed if trip is not None)
    meals: dict[tuple[int, str], list[dict]] = {}
    for dish in week["days"]:
        meals.setdefault((dish["day_index"], dish["meal_type"]), []).append(dish)
    failures: Counter = Counter()
    moves, groups, fried_meals, energy = [], [], 0, []
    for (day, meal), dishes in sorted(meals.items(), key=lambda item: (item[0][0], MEAL_ORDER.index(item[0][1]))):
        tags = {d["role_id"]: recipes[d["recipe"]["slug"]] for d in dishes}
        since_trip = (day - 1) % meal_structure.trip_days() + 1
        for dish in dishes:
            recipe = recipes[dish["recipe"]["slug"]]
            bought = {line.ingredient.normalized_name for line in recipe.recipe_ingredients} - basics
            if since_trip > meal_structure.perishable_days() and any(
                line.ingredient.perishable is True and line.ingredient.normalized_name in bought
                for line in recipe.recipe_ingredients
            ):
                failures["perishable_within_days"] += 1
            if not _equipment_met(recipe.equipment, missing):
                failures["equipment"] += 1
        core = tags.get("main")
        bowl = meal != "breakfast" and core is not None and _carries_staple(core)
        # Dish counts as the table says for the people present, give or take one dish left out (a one-bowl
        # main also stands for the staple); breakfast too.
        people = people_present(request.household, date.fromisoformat(dishes[0]["planned_date"]), meal)
        expected = expected_dishes(meal, people)
        filled = Counter(_kind(role) for role in tags)
        left_out = expected - filled - (Counter(staple=1) if bowl else Counter())
        if filled - expected or sum(left_out.values()) > 1:
            failures["dish_count_within_one_move"] += 1
        if left_out:
            moves.append(f"day {day} {meal}: {', '.join(sorted(left_out))} left out")
        if meal not in ("lunch", "dinner"):
            continue
        if (
            core is None
            or (bowl and "staple" in tags)
            or (not bowl and ("staple" not in tags or core.meal_role != "protein_main"))
        ):
            failures["filling_core_and_staple"] += 1
        if any(recipe.meal_role in NON_MEAL_ROLES for recipe in tags.values()) or any(
            (recipe.meal_role == "salad" and _kind(role) != "vegetable")
            or (recipe.meal_role == "soup" and _kind(role) != "soup")
            for role, recipe in tags.items()
        ):
            failures["no_non_meal_dish"] += 1
        sources = [set(recipe.protein_sources or ()) for role, recipe in tags.items() if _kind(role) == "main"]
        if sum(map(len, sources)) != len(set().union(*sources)):
            failures["protein_sources_distinct"] += 1
        per_serving = sum(d["nutrition_per_person"]["calories_kcal"] for d in dishes)
        energy.append(per_serving >= floor[meal] - 1e-6)
        if not energy[-1]:
            failures["energy_floor"] += 1
        if "staple" in tags:
            staple = {
                line.ingredient.normalized_name
                for line in tags["staple"].recipe_ingredients
                if not not_purchased(line.ingredient.normalized_name)
            } - basics
            trip = None if not trips else 1 + (day - 1) // meal_structure.trip_days()
            if not staple <= listed.get(trip, set()) or tags["staple"].nutrition is None:
                failures["staple_listed_and_counted"] += 1
        groups.append(
            len({meal_structure.cuisine_group(r.cuisine) for role, r in tags.items() if role != "staple"} - {None})
        )
        fried_meals += sum("deep_fry" in (r.cooking_methods or ()) for r in tags.values()) >= 2
    if trips:
        for trip in trips:
            days = range(1 + (trip - 1) * 7, 1 + trip * 7)
            used = {
                line.ingredient.normalized_name
                for (day, _), dishes in meals.items()
                if day in days
                for d in dishes
                for line in recipes[d["recipe"]["slug"]].recipe_ingredients
            }
            if not listed[trip] <= used:
                failures["trip_lines_used_on_their_days"] += 1
    checks = {
        name: failures[name] == 0
        for name in (
            "filling_core_and_staple",
            "no_non_meal_dish",
            "protein_sources_distinct",
            "energy_floor",
            "perishable_within_days",
            "equipment",
            "dish_count_within_one_move",
            "staple_listed_and_counted",
            "trip_lines_used_on_their_days",
        )
    }
    titles = [d["recipe"]["slug"] for d in week["days"] if d["role_id"] != "staple"]
    return {
        "checks": checks,
        "failures": dict(sorted((k, v) for k, v in failures.items() if v)),
        "metrics": {
            "meals": len(meals),
            "dishes": len(week["days"]),
            "distinct_dishes_excluding_staples": len(set(titles)),
            "staples": sorted({d["recipe"]["title"] for d in week["days"] if d["role_id"] == "staple"}),
            "cuisine_groups_per_meal": round(statistics.mean(groups), 2) if groups else None,
            "meals_with_two_deep_fried": fried_meals,
            "energy_floor_pass_rate": round(sum(energy) / len(energy), 3) if energy else None,
            "moves": moves,
            "grocery_lines_by_trip": {str(trip): len(names) for trip, names in sorted(listed.items(), key=str)},
            "purchase_total_sgd": week["grocery_estimate"]["purchase_total_sgd"],
        },
    }


def _floors() -> dict[str, float]:
    shares = meal_structure.meal_structure()["energy_floor_share"]
    return {meal: share for meal, share in shares.items() if meal != "note"}


def _meal_rows(week: dict) -> list[dict]:
    rows = []
    for dish in week["days"]:
        day = date.fromisoformat(dish["planned_date"])
        rows.append(
            {
                "day": dish["day_index"],
                "weekday": day.strftime("%a"),
                "meal": dish["meal_type"],
                "role": dish["role_id"],
                "recipe": dish["recipe"]["title"],
                "servings": dish["servings"],
            }
        )
    return rows


def run_case(plans, session, case: dict) -> tuple[dict, float]:
    request = request_for(case)
    started = time.perf_counter()
    try:
        week = plans.generate(request).model_dump(mode="json")
    except WeeklyPlanSelectionError as error:
        return {"case": case["case"], "about": case["about"], "outcome": "refused", "reason": str(error)}, (
            time.perf_counter() - started
        )
    seconds = time.perf_counter() - started
    recipes = _recipes(session, {d["recipe"]["slug"] for d in week["days"]})
    result = check_week(week, request, recipes)
    return {
        "case": case["case"],
        "about": case["about"],
        "outcome": "planned",
        "passed": all(result["checks"].values()),
        **result,
        "meals": _meal_rows(week),
    }, seconds


def evaluate(repeats: int = 0) -> tuple[dict, dict]:
    """The report, and wall times per case: the report's own run, then `repeats` warm runs."""
    lines = (release_dir() / "recipes.jsonl").read_text("utf-8").splitlines()
    catalog = {"scenario": {"recipe_candidate_slugs": [json.loads(line)["recipe_id"] for line in lines]}}
    seconds, results = {}, []
    with product_database(catalog) as factory, factory() as session:
        plans = build_meal_plan_service(session, HOUSEHOLD_ID)
        for case in CASES:
            result, first = run_case(plans, session, case)
            results.append(result)
            warm = [run_case(plans, session, case)[1] for _ in range(repeats)]
            seconds[case["case"]] = {"first": round(first, 2), "warm": [round(s, 2) for s in warm]}
    report = {
        "report": "full-default-v1",
        "decision": "ADR-0070, ADR-0072, ADR-0075; operations/sprint2-plan/08-household.md section 0",
        "start_date": START,
        "energy_floor_kcal_per_serving": {
            meal: round(share * hpb()["adult_reference"]["energy_kcal"], 1) for meal, share in _floors().items()
        },
        # Every case planned when it was set, so a case that now refuses is a regression, not an outcome.
        "passed": all(r["outcome"] == "planned" and r["passed"] for r in results),
        "cases": results,
    }
    return report, seconds


def markdown(report: dict) -> str:
    lines = [
        "# Full default: is every lunch and dinner a real meal?",
        "",
        "> Scope: five fixed households planned with the full meal structure (ADR-0070) on the whole release "
        "catalog, fixture prices, the product path; developer cases, no held-out data. It is a regression check "
        "of the real-meal rules, not a quality score: PASS says nothing about speed. Wall time is not in this "
        "file (it differs by machine): `timing.md` beside it reads each case against the ADR-0079 guidance.",
        "",
        "Generated by `python -m app.evaluation.full_default`.",
        "",
        f"**Overall result: {'PASS' if report['passed'] else 'FAIL'}** (every case plans and passes every check)",
        "",
        "Energy floor per serving: "
        + ", ".join(f"{meal} {kcal} kcal" for meal, kcal in report["energy_floor_kcal_per_serving"].items())
        + ".",
        "",
    ]
    for case in report["cases"]:
        lines += [f"## {case['case']}", "", case["about"], ""]
        if case["outcome"] == "refused":
            lines += [f"Refused: {case['reason']}", ""]
            continue
        metrics = case["metrics"]
        lines += [
            "| Check | Result |",
            "|---|:---:|",
            *[f"| `{name}` | {'PASS' if ok else 'FAIL'} |" for name, ok in case["checks"].items()],
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Meals | {metrics['meals']} |",
            f"| Dishes | {metrics['dishes']} |",
            f"| Distinct dishes (staples aside) | {metrics['distinct_dishes_excluding_staples']} |",
            f"| Cuisine groups per lunch or dinner | {metrics['cuisine_groups_per_meal']} |",
            f"| Meals with two deep-fried dishes | {metrics['meals_with_two_deep_fried']} |",
            f"| Energy floor pass rate | {metrics['energy_floor_pass_rate']} |",
            f"| Grocery lines by trip | {metrics['grocery_lines_by_trip']} |",
            f"| Purchase total (SGD) | {metrics['purchase_total_sgd']} |",
            "",
            f"Staples: {', '.join(metrics['staples']) or 'none'}.",
            "",
            f"Moves: {'; '.join(metrics['moves']) or 'none'}.",
            "",
            *meal_table(case["meals"]),
        ]
        if case["failures"]:
            lines += [f"Failures: {case['failures']}", ""]
    return "\n".join(lines) + "\n"


def meal_table(rows: list[dict]) -> list[str]:
    """The plan itself, a row a day: each meal's dishes in the plan's order, the staple marked."""
    days: dict[tuple, dict[str, list[str]]] = {}
    for row in rows:
        title = f"{row['recipe']} (staple)" if row["role"] == "staple" else row["recipe"]
        days.setdefault((row["day"], row["weekday"]), {}).setdefault(row["meal"], []).append(title)
    lines = ["| Day | " + " | ".join(meal.title() for meal in MEAL_ORDER) + " |", "|---|" + "---|" * len(MEAL_ORDER)]
    for (day, weekday), meals in sorted(days.items()):
        cells = [" + ".join(meals.get(meal, [])).replace("|", "/") or "-" for meal in MEAL_ORDER]
        lines.append(f"| {day} {weekday} | " + " | ".join(cells) + " |")
    return [*lines, ""]


# ADR-0079: how long is acceptable follows how hard the request is. A simple request should still come back
# quickly; a complex one may take up to about a minute. Only past that is a case marked over, and a case is
# never cut short to meet either figure.
QUICK_SECONDS = 4.0
OVER_SECONDS = 60.0


def timing_band(taken: float) -> str:
    """How a case's warm median reads against the ADR-0079 guidance."""
    if taken > OVER_SECONDS:
        return "over"
    return "quick" if taken <= QUICK_SECONDS else "complex"


BAND_LABEL = {
    "quick": "quick",
    "complex": "within the guidance for a complex request",
    "over": f"over ~{OVER_SECONDS:g} s",
}

# Why a case takes as long as it does, from a cProfile of one warm product run of each case (task 14, 2026-10-21,
# Windows, after the shared-dish candidate changes). Shares are of the profiled run, which the profiler slows about
# twofold. Every case past the quick figure has one: ADR-0079 section 4 asks for the cause of each, not only of the
# ones over a minute. Rewrite a case's entry whenever a change moves its time.
MEAL_CHECKS = (
    "building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> "
    "`meal_permitted` -> `meal_composition.real_meal_issues`)"
)
MEMBER_CHECKS = (
    "`member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per "
    "member and recipe)"
)
# Said honestly for a case nobody has profiled at its current time, rather than a guess.
UNKNOWN_CAUSE = "cause unknown: this time has not been profiled; profile one warm run and add it to SLOW_CAUSES."
SLOW_CAUSES = {
    "one-adult": (
        f"one week-long beam search; {MEAL_CHECKS} is about 40% of the run and reading the candidates (recipes and "
        "fixture prices) about 25%; at three meals a day for seven days that is 21 slots of combinations."
    ),
    "four-with-vegetarian": (
        f"one beam search, three-quarters of the run; {MEAL_CHECKS} is about 63%, and a third of the run is "
        f"{MEMBER_CHECKS}. The vegetarian member's own candidates add up to 40 dishes a kind to the packet "
        "(`product_path._packet_covering`), so a meal has more combinations to check than before the shared-dish "
        "model."
    ),
    "six-tight-budget": (
        "four whole-week beam searches instead of one, 94% of the run: the ranked search keeps no week filled with "
        "no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`, about 64%) run "
        f"as well. Each builds every six-dish dinner of its candidates again; {MEAL_CHECKS} is about 78% of the run, "
        f"and {MEMBER_CHECKS} is about 44%. The variety pass is about 5%. Upgrade path: share the meal checks "
        "between the four searches (they do not depend on the ranking) and cache the member checks. The owner "
        "accepted this case's time (ADR-0079 section 5, ADR-0080): over the line is a known exception, not a "
        "failure."
    ),
    "two-no-oven-ten-days": (
        f"one beam search over ten days and two shopping trips, about two-thirds of the run; {MEAL_CHECKS} is about "
        "42%, and reading the candidates about 15%; the plan has 30 slots of combinations to build."
    ),
    "seven-with-young-children": (
        f"one beam search, 80% of the run, over seven-dish dinners for a household of seven; {MEAL_CHECKS} is about "
        f"69%, and {MEMBER_CHECKS} about 37%."
    ),
}


def timing_markdown(timing: dict) -> str:
    bands = {case: timing_band(row["median"] or row["first"]) for case, row in timing["cases"].items()}
    over = [case for case, band in bands.items() if band == "over"]
    explained = [case for case, band in bands.items() if band in ("complex", "over")]
    lines = [
        "# Full default: plan wall time",
        "",
        "> Scope: the cases of `latest.md`, one machine. The report's run warms the candidate cache; the warm "
        "runs are the same plan again. Median and slowest of the warm runs. ADR-0079 sets how long is "
        "acceptable by how hard the "
        f"request is: a simple request should still come back within about {QUICK_SECONDS:g} s, a complex one "
        f"may take up to about {OVER_SECONDS:g} s, and only past that is a case marked over. A case is never "
        "cut short to meet either figure, and no feature is dropped to make one faster.",
        "",
        f"Machine: {timing['machine']}. The code commit is in `timing.json` beside this file.",
        "",
        "| Case | Report run (s) | Warm median (s) | Warm max (s) | Against the ADR-0079 guidance |",
        "|---|---:|---:|---:|---|",
        *[
            f"| {case} | {row['first']} | {row['median']} | {row['max']} | {BAND_LABEL[bands[case]]} |"
            for case, row in timing["cases"].items()
        ],
        "",
        f"Over ~{OVER_SECONDS:g} s: {', '.join(over) or 'none'}.",
    ]
    for case in explained:
        lines += [
            "",
            f"- `{case}` ({BAND_LABEL[bands[case]]}): {SLOW_CAUSES.get(case, UNKNOWN_CAUSE)}",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-report", type=Path, default=Path("docs/evaluation/full-default/latest.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("docs/evaluation/full-default/latest.md"))
    parser.add_argument("--timing-report", action="store_true", help="also write timing.json and timing.md")
    parser.add_argument("--repeats", type=int, default=None, help="warm runs per case (3 with --timing-report)")
    args = parser.parse_args()
    repeats = args.repeats if args.repeats is not None else (3 if args.timing_report else 0)
    report, seconds = evaluate(repeats)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    args.markdown_report.write_text(markdown(report), encoding="utf-8", newline="\n")
    print(f"Full default: {'PASS' if report['passed'] else 'FAIL'}")
    for case in report["cases"]:
        times = seconds[case["case"]]
        planned = (
            f"{case['metrics']['meals']} meals, {case['metrics']['dishes']} dishes, "
            f"failures {case['failures'] or 'none'}"
            if case["outcome"] == "planned"
            else case["reason"]
        )
        print(f"  {case['case']}: {case['outcome']} ({planned}); first {times['first']} s, warm {times['warm']}")
    if args.timing_report:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
        timing = {
            "machine": f"{platform.processor() or platform.machine()} ({platform.system()})",
            "commit": commit,
            "cases": {
                case: {
                    "first": row["first"],
                    "median": round(statistics.median(row["warm"]), 2) if row["warm"] else None,
                    "max": max(row["warm"]) if row["warm"] else None,
                }
                for case, row in seconds.items()
            },
        }
        folder = args.json_report.parent
        (folder / "timing.json").write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8", newline="\n")
        (folder / "timing.md").write_text(timing_markdown(timing), encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
