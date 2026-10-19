"""The shared-dish model (ADR-0071 sections 1 and 2) against the merged union it replaces.

Ten fixed households are planned twice through `WeeklyMealPlanService.generate`, on the whole release catalog at
fixture prices, as `app.evaluation.full_default` plans them:

- **merged**: layer 08 PR-1's behaviour, kept here as the baseline. Every member's allergens, exclusions and
  diets are merged into one household union, including the allergens marked "only I avoid it", and no member
  carries limits of their own. One vegetarian member makes the whole week vegetarian.
- **shared**: the shared-dish model. The household avoids the allergens nobody marked "only I avoid it"; every
  other limit stays with its member. A dish is served when at least one present member can eat it, is cooked for
  the servings of those members, and every present member has a filling core and a vegetable of their own at
  every lunch and dinner.

The report compares the two on the recipes a household may choose from, the dishes planned, how different they
are, what the week costs, whether every member was covered, and each member's energy attainment. Every check is
computed here from the plan response and the catalog, never through the planner's own helpers: the presence
rules, who can eat what, the servings of each dish and each member's energy are all worked out again. A safety
violation is a dish counted as a member's food that breaks that member's own limits, or any dish holding an
allergen the whole household avoids; the report fails on one.

Wall time differs by machine, so it is printed and written to `timing.md`, never to `latest.*` (CI diffs those).

    python -m app.evaluation.shared_dish [--timing-report]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.routes.meal_plans import build_meal_plan_service
from app.core.paths import repository_root
from app.data import meal_structure
from app.data.household_reference import hpb
from app.data.release_v2 import release_dir
from app.evaluation.meal_day_week_runner import HOUSEHOLD as HOUSEHOLD_ID
from app.evaluation.meal_day_week_runner import product_database
from app.models.recipe import Recipe, RecipeIngredient
from app.planning import product_path
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.schemas.meal_plan import MEAL_ORDER, WeeklyMealPlanRequest, default_plan_shape

START = "2027-01-03"  # a Sunday
DAYS = 3  # three days is nine meals a household, which exercises every rule within a bounded run time
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND = ["saturday", "sunday"]
IMPLICATIONS_FILE = "data/recipes/dietary-tag-implications.json"


def _rule(text: str, **fields) -> dict:
    return {"source_text": text, "restatement": "-", **fields}


def _energy(age_band: str, sex: str | None) -> float:
    """The HPB daily energy need in kcal for a band and sex, read from the reference table here rather than
    through the planner's own lookup; a band with no sex is the mean of both rows."""
    rows = [row for row in hpb()["rows"] if row["age_band"] == age_band and (sex is None or row["sex"] == sex)]
    return sum(row["energy_kcal"] for row in rows) / len(rows)


def member(name: str, age_band: str = "adult", sex: str | None = None, **limits) -> dict:
    """One member: HPB portions (energy over the adult reference, as the profile resolves them) and their own
    limits. `daily_energy_kcal` is their own target, which the meal's energy floor is a share of."""
    energy = _energy(age_band, sex)
    servings = min(3.0, max(0.25, round(energy / hpb()["adult_reference"]["energy_kcal"], 2)))
    return {"name": name, "servings": servings, "daily_energy_kcal": round(energy, 1), **limits}


# Ten fixed households. Each one's members carry their own limits; `merged_request` below turns them into the
# union PR-1 saved, so the two plans differ only in where the limits live.
CASES = [
    {
        "case": "four-one-vegetarian",
        "about": "Two adults, a teen and a child; Ann is vegetarian.",
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child"),
            ]
        },
    },
    {
        "case": "two-one-vegetarian",
        "about": "Two adults, one of them vegetarian: the smallest household the model has to serve.",
        "request": {"household_size": 2},
        "household": {
            "members": [
                member("Lin", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Raj", "adult", "male"),
            ]
        },
    },
    {
        "case": "with-a-child",
        "about": "Two adults and a child who will not eat mushroom; the child's exclusion is the child's own.",
        "request": {"household_size": 3},
        "household": {
            "members": [
                member("Ann", "adult", "female"),
                member("Ben", "adult", "male"),
                member("Mei", "child", excluded_ingredients=["mushroom"]),
            ]
        },
    },
    {
        "case": "weekday-lunch-away",
        "about": "Four, one vegetarian; the child eats lunch at school on weekdays, so those lunches are for three.",
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child"),
            ],
            "presence_rules": [
                _rule(
                    "the kids eat lunch at school on weekdays",
                    member_name="Mei",
                    present=False,
                    weekdays=WEEKDAYS,
                    meal_types=["lunch"],
                )
            ],
        },
    },
    {
        "case": "weekend-guest",
        "about": "Four, one vegetarian; a grandparent who is vegetarian too joins weekend dinners.",
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child"),
                member("Grandma", "senior", default_present=False, dietary_preferences=["vegetarian"]),
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
        "case": "peanut-whole-household",
        "about": "Four; Mei is allergic to peanut and the whole household avoids it, which is the default.",
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female"),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child", allergens=["peanut"]),
            ]
        },
    },
    {
        "case": "peanut-only-mei-avoids",
        "about": (
            'The same household with "only Mei avoids it" on, so peanut is left out of Mei\'s dishes and the '
            "others may have it. The merged baseline is the same week as the case above: the union cannot tell "
            "the two apart."
        ),
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female"),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child", allergens=["peanut"], self_only_allergens=["peanut"]),
            ]
        },
    },
    {
        "case": "mixed-diets",
        "about": "Four with two different diets: Ann vegetarian, Kai dairy-free.",
        "request": {"household_size": 4},
        "household": {
            "members": [
                member("Ann", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male", dietary_preferences=["dairy-free"]),
                member("Mei", "child"),
            ]
        },
    },
    {
        "case": "six-one-vegetarian",
        "about": "Six adults, one of them vegetarian: dinner is the 5-6 row of the ADR-0070 table.",
        "request": {"household_size": 6},
        "household": {
            "members": [
                member("Adult 1", "adult", "female", dietary_preferences=["vegetarian"]),
                *(member(f"Adult {n}", "adult", "male" if n % 2 else "female") for n in range(2, 7)),
            ]
        },
    },
    {
        "case": "tight-budget",
        "about": (
            "Four, one vegetarian, on a tight weekly budget for three days (S$120, chosen once on developer runs)."
        ),
        "request": {"household_size": 4, "weekly_budget_sgd": 120.0},
        "household": {
            "members": [
                member("Ann", "adult", "female", dietary_preferences=["vegetarian"]),
                member("Ben", "adult", "male"),
                member("Kai", "teen", "male"),
                member("Mei", "child"),
            ]
        },
    },
]


def _request(case: dict, arrangement: str) -> WeeklyMealPlanRequest:
    """The planning request of one arrangement. `merged` writes every member's limits into the household-wide
    union PR-1 saved (the allergens marked "only I avoid it" included) and leaves the members without limits of
    their own; `shared` keeps each limit with its member and the household avoids only the allergens nobody
    marked."""
    members = case["household"]["members"]
    if arrangement == "merged":
        household = {
            **case["household"],
            "members": [
                {key: value for key, value in m.items() if key in ("name", "servings", "default_present")}
                for m in members
            ],
        }
        limits = {
            "allergens": sorted({a for m in members for a in m.get("allergens", ())}),
            "excluded_ingredients": sorted({i for m in members for i in m.get("excluded_ingredients", ())}),
            "dietary_preferences": sorted({d for m in members for d in m.get("dietary_preferences", ())}),
        }
    else:
        # `self_only_allergens` is the profile's own key: the planner reads a member's full allergen list and the
        # household-wide list, so the scenario's mark only decides which allergens the household avoids.
        household = {
            **case["household"],
            "members": [{k: v for k, v in m.items() if k != "self_only_allergens"} for m in members],
        }
        whole = {a for m in members for a in set(m.get("allergens", ())) - set(m.get("self_only_allergens", ()))}
        limits = {"allergens": sorted(whole), "excluded_ingredients": [], "dietary_preferences": []}
    return WeeklyMealPlanRequest.model_validate(
        {
            "start_date": START,
            "day_count": DAYS,
            "pricing_mode": "fixture",
            "max_cooking_time_minutes": 240,
            "plan_shape": default_plan_shape().model_dump(mode="json"),
            **case["request"],
            **limits,
            "household": household,
        }
    )


def _entailed(tags) -> set[str]:
    """The dietary tags a recipe satisfies, closed over the entailments that hold by definition. The table is
    read here (`data/recipes/dietary-tag-implications.json`), not through the planner's closure."""
    table = _implications()
    resolved: set[str] = set()
    frontier = list(tags)
    while frontier:
        tag = frontier.pop()
        if tag in resolved:
            continue
        resolved.add(tag)
        frontier.extend(table.get(tag, ()))
    return resolved


_TABLE: dict[str, list[str]] = {}


def _implications() -> dict[str, list[str]]:
    if not _TABLE:
        payload = json.loads((repository_root() / IMPLICATIONS_FILE).read_text(encoding="utf-8"))
        _TABLE.update({tag: list(entry["entails"]) for tag, entry in (payload.get("implications") or {}).items()})
    return _TABLE


def _recipe_facts(recipe: Recipe) -> dict:
    """What the checks need of one catalog recipe, read from the row rather than from a planner helper."""
    lines = recipe.recipe_ingredients
    return {
        "allergens": {*(recipe.allergens or ()), *(a for line in lines for a in (line.ingredient.allergens or ()))},
        "ingredients": {line.ingredient.normalized_name for line in lines},
        "tags": _entailed(recipe.dietary_tags or ()),
        "meal_role": recipe.meal_role,
        "carries_staple": recipe.meal_role == "one_bowl" or recipe.contains_staple is True,
    }


def _can_eat(limits: dict, facts: dict) -> bool:
    """Whether a dish is one member's food: their own allergens, exclusions and diet, matched here by hand.

    Exclusions are matched as the household states them. A member who says "no pork" and a recipe whose line is
    bacon is not caught here, where the planner expands the hierarchy; the scenarios name ingredients directly,
    so the check stays independent without repeating that expansion.
    """
    if facts["allergens"] & set(limits.get("allergens", ())):
        return False
    if facts["ingredients"] & set(limits.get("excluded_ingredients", ())):
        return False
    return set(limits.get("dietary_preferences", ())) <= facts["tags"]


def _present(household: dict, day: date, meal: str) -> list[dict]:
    """The members home for a meal: each usually-home member, then each rule naming the weekday and meal, the
    last one for a member winning (written out here, not the planner's own presence reading)."""
    home = {m["name"]: m.get("default_present", True) for m in household["members"]}
    weekday = day.strftime("%A").lower()
    for rule in household.get("presence_rules", ()):
        if (not rule.get("weekdays") or weekday in rule["weekdays"]) and (
            not rule.get("meal_types") or meal in rule["meal_types"]
        ):
            home[rule["member_name"]] = rule["present"]
    return [m for m in household["members"] if home[m["name"]]]


def pool_size(case: dict, arrangement: str, facts: dict[str, dict]) -> int:
    """How many catalog recipes this household may choose from: those no household-wide limit removes and, in
    the shared arrangement, that at least one usually-home member can eat."""
    request = _request(case, arrangement)
    household_limits = {
        "allergens": list(request.allergens),
        "excluded_ingredients": list(request.excluded_ingredients),
        "dietary_preferences": list(request.dietary_preferences),
    }
    members = [m for m in case["household"]["members"] if m.get("default_present", True)]
    count = 0
    for recipe in facts.values():
        if not _can_eat(household_limits, recipe):
            continue
        if arrangement == "shared" and not any(_can_eat(m, recipe) for m in members):
            continue
        count += 1
    return count


def check_week(week: dict, case: dict, arrangement: str, facts: dict[str, dict]) -> dict:
    """Every shared-dish rule of one planned week, recomputed from the response and the catalog."""
    household = case["household"]
    household_allergens = set(_request(case, arrangement).allergens)
    floors = {meal: share for meal, share in meal_structure.meal_structure()["energy_floor_share"].items()}
    meals: dict[tuple[int, str], list[dict]] = {}
    for dish in week["days"]:
        meals.setdefault((dish["day_index"], dish["meal_type"]), []).append(dish)
    failures: Counter = Counter()
    # Per member: the kcal they are served, and the kcal their own targets ask of the meals planned.
    served: dict[str, float] = {m["name"]: 0.0 for m in household["members"]}
    needed: dict[str, float] = dict.fromkeys(served, 0.0)
    uncovered: list[str] = []
    for (day, meal), dishes in sorted(meals.items(), key=lambda item: (item[0][0], MEAL_ORDER.index(item[0][1]))):
        when = date.fromisoformat(dishes[0]["planned_date"])
        present = _present(household, when, meal)
        limits = {m["name"]: (m if arrangement == "shared" else {}) for m in present}
        for dish in dishes:
            recipe = facts[dish["recipe"]["slug"]]
            eaters = [m for m in present if _can_eat(limits[m["name"]], recipe)]
            # A dish reaches the table only when someone at it can eat the dish.
            if not eaters:
                failures["every_dish_has_an_eater"] += 1
            # ... and is cooked for exactly those members' portions at its own share of the meal, which is what
            # one person who eats it has and never changes with who else can.
            expected = sum(m["servings"] for m in eaters) * dish["portion_share"]
            if dish["servings"] is None or abs(dish["servings"] - expected) > 0.002:
                failures["servings_follow_the_eaters"] += 1
                uncovered.append(
                    f"day {day} {meal} {dish['role_id']}: cooked for {dish['servings']}, its eaters "
                    f"{[m['name'] for m in eaters]} at share {dish['portion_share']} want {round(expected, 3)}"
                )
            # No dish on the table may hold an allergen the whole household avoids.
            if recipe["allergens"] & household_allergens:
                failures["no_household_allergen_on_the_table"] += 1
            for eater in eaters:
                served[eater["name"]] += dish["nutrition_per_person"]["calories_kcal"] * eater["servings"]
        if meal not in ("lunch", "dinner"):
            continue
        has_vegetable = any(_kind(dish["role_id"]) == "vegetable" for dish in dishes)
        for who in present:
            needed[who["name"]] += floors[meal] * who["daily_energy_kcal"]
            mine = [d for d in dishes if _can_eat(limits[who["name"]], facts[d["recipe"]["slug"]])]
            mains = [facts[d["recipe"]["slug"]] for d in mine if _kind(d["role_id"]) == "main"]
            staple = any(_kind(d["role_id"]) == "staple" for d in mine)
            core = any(r["carries_staple"] for r in mains) or (
                staple and any(r["meal_role"] == "protein_main" for r in mains)
            )
            if not core:
                failures["every_member_has_a_filling_core"] += 1
                uncovered.append(f"day {day} {meal}: {who['name']} has no core")
            if has_vegetable and not any(_kind(d["role_id"]) == "vegetable" for d in mine):
                failures["every_member_has_a_vegetable"] += 1
                uncovered.append(f"day {day} {meal}: {who['name']} has no vegetable dish")
            if sum(d["nutrition_per_person"]["calories_kcal"] for d in mine) * who["servings"] < (
                floors[meal] * who["daily_energy_kcal"] - 1e-6
            ):
                failures["every_member_meets_their_energy_floor"] += 1
    checks = {
        name: failures[name] == 0
        for name in (
            "every_dish_has_an_eater",
            "servings_follow_the_eaters",
            "no_household_allergen_on_the_table",
            "every_member_has_a_filling_core",
            "every_member_has_a_vegetable",
            "every_member_meets_their_energy_floor",
        )
    }
    titles = [d["recipe"]["slug"] for d in week["days"] if d["role_id"] != "staple"]
    attainment = {name: round(served[name] / needed[name], 3) if needed[name] else None for name in sorted(served)}
    return {
        "checks": checks,
        # Anything that puts a dish in front of a member who cannot eat it, or an allergen on the table.
        "safety_violations": sum(
            failures[name] for name in ("every_dish_has_an_eater", "no_household_allergen_on_the_table")
        )
        + failures["every_member_has_a_filling_core"]
        + failures["every_member_has_a_vegetable"],
        "failures": dict(sorted((k, v) for k, v in failures.items() if v)),
        "uncovered": uncovered[:12],
        "metrics": {
            "recipe_pool": pool_size(case, arrangement, facts),
            "dishes": len(week["days"]),
            "distinct_dishes_excluding_staples": len(set(titles)),
            "purchase_total_sgd": week["grocery_estimate"]["purchase_total_sgd"],
            "energy_attainment_by_member": attainment,
            "lowest_energy_attainment": min((v for v in attainment.values() if v is not None), default=None),
        },
    }


def _kind(role_id: str) -> str:
    """ "main-2" -> "main": the kind of dish a role id names."""
    return role_id.split("-")[0]


def _facts(session) -> dict[str, dict]:
    """Every recipe of the imported catalog, by slug: what the checks and the pool count read of it."""
    statement = select(Recipe).options(selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient))
    return {recipe.slug: _recipe_facts(recipe) for recipe in session.scalars(statement).unique()}


def run_case(plans, case: dict, arrangement: str, facts: dict[str, dict]) -> tuple[dict, float]:
    request = _request(case, arrangement)
    started = time.perf_counter()
    try:
        week = plans.generate(request).model_dump(mode="json")
    except (WeeklyPlanSelectionError, product_path.ProductPlanningError) as error:
        return {"arrangement": arrangement, "outcome": "refused", "reason": str(error)}, (time.perf_counter() - started)
    seconds = time.perf_counter() - started
    result = check_week(week, case, arrangement, facts)
    return {"arrangement": arrangement, "outcome": "planned", "passed": all(result["checks"].values()), **result}, (
        seconds
    )


def evaluate() -> tuple[dict, dict]:
    lines = (release_dir() / "recipes.jsonl").read_text("utf-8").splitlines()
    slugs = [json.loads(line)["recipe_id"] for line in lines]
    catalog = {"scenario": {"recipe_candidate_slugs": slugs}}
    seconds: dict[str, dict[str, float]] = {}
    results = []
    product_seconds = product_path.VARIETY_PASS_SECONDS
    with product_database(catalog) as factory, factory() as session:
        plans = build_meal_plan_service(session, HOUSEHOLD_ID)
        facts = _facts(session)
        for case in CASES:
            runs, timings = [], {}
            for arrangement in ("merged", "shared"):
                product_path.VARIETY_PASS_SECONDS = float("inf")  # plans independent of the machine
                try:
                    run, taken = run_case(plans, case, arrangement, facts)
                finally:
                    product_path.VARIETY_PASS_SECONDS = product_seconds
                runs.append(run)
                timings[arrangement] = round(taken, 2)
            seconds[case["case"]] = timings
            shared = next(run for run in runs if run["arrangement"] == "shared")
            results.append(
                {
                    "case": case["case"],
                    "about": case["about"],
                    # Only the shared arrangement is held to the model's rules; merged is the baseline it replaces.
                    "passed": shared["outcome"] == "planned" and shared["passed"],
                    "runs": {run["arrangement"]: run for run in runs},
                }
            )
    report = {
        "report": "shared-dish-v1",
        "decision": "ADR-0071 sections 1 and 2; operations/sprint2-plan/08-household.md section 1",
        "start_date": START,
        "day_count": DAYS,
        "energy_floor_share": {
            meal: share
            for meal, share in meal_structure.meal_structure()["energy_floor_share"].items()
            if meal != "note"
        },
        "passed": all(result["passed"] for result in results),
        "safety_violations": sum(
            run.get("safety_violations", 0) for result in results for run in [result["runs"]["shared"]]
        ),
        "cases": results,
    }
    return report, seconds


def _row(run: dict, key: str) -> str:
    if run["outcome"] != "planned":
        return "refused"
    value = run["metrics"][key]
    return "-" if value is None else f"{value}"


def markdown(report: dict) -> str:
    lines = [
        "# Shared dishes: each member's own limits against the merged union",
        "",
        "> Scope: ten fixed households planned twice on the whole release catalog, fixture prices, the product "
        "path; developer cases, no held-out data. `merged` is layer 08 PR-1's union, the behaviour this "
        "replaces; `shared` is the shared-dish model (ADR-0071 sections 1 and 2). Only `shared` is held to the "
        "model's rules. Every check is recomputed here from the plan and the catalog, never through the "
        "planner's helpers. It is a regression check, not a quality score, and PASS says nothing about speed: "
        "wall time is in `timing.md` beside this file.",
        "",
        "Generated by `python -m app.evaluation.shared_dish`.",
        "",
        f"**Overall result: {'PASS' if report['passed'] else 'FAIL'}** "
        f"(safety violations: {report['safety_violations']})",
        "",
        f"Each household plans {report['day_count']} days of breakfast, lunch and dinner from {report['start_date']}"
        " (a Sunday). Energy floor share: "
        + ", ".join(f"{meal} {share:.0%}" for meal, share in report["energy_floor_share"].items())
        + " of each member's own daily target.",
        "",
        "| Case | Recipe pool | Dishes | Different dishes | Purchase total (SGD) | Lowest attainment | Covered |",
        "|---|---|---|---|---|---|:---:|",
    ]
    for case in report["cases"]:
        merged, shared = case["runs"]["merged"], case["runs"]["shared"]
        covered = "PASS" if case["passed"] else "FAIL"
        lines.append(
            f"| `{case['case']}` | {_row(merged, 'recipe_pool')} → {_row(shared, 'recipe_pool')} "
            f"| {_row(merged, 'dishes')} → {_row(shared, 'dishes')} "
            f"| {_row(merged, 'distinct_dishes_excluding_staples')} → "
            f"{_row(shared, 'distinct_dishes_excluding_staples')} "
            f"| {_row(merged, 'purchase_total_sgd')} → {_row(shared, 'purchase_total_sgd')} "
            f"| {_row(merged, 'lowest_energy_attainment')} → {_row(shared, 'lowest_energy_attainment')} "
            f"| {covered} |"
        )
    lines += ["", "Each cell reads `merged → shared`.", ""]
    for case in report["cases"]:
        shared = case["runs"]["shared"]
        lines += [f"## {case['case']}", "", case["about"], ""]
        if shared["outcome"] != "planned":
            lines += [f"The shared arrangement was refused: {shared['reason']}", ""]
            continue
        lines += [
            "| Check | Result |",
            "|---|:---:|",
            *[f"| `{name}` | {'PASS' if ok else 'FAIL'} |" for name, ok in shared["checks"].items()],
            "",
            "| Member | Energy attainment |",
            "|---|---:|",
            *[
                f"| {name} | {value if value is not None else '-'} |"
                for name, value in shared["metrics"]["energy_attainment_by_member"].items()
            ],
            "",
        ]
        if shared["uncovered"]:
            lines += ["Uncovered members:", "", *[f"- {item}" for item in shared["uncovered"]], ""]
    return "\n".join(lines) + "\n"


def timing_markdown(seconds: dict[str, dict[str, float]]) -> str:
    target = 4.0
    rows = [
        f"| `{case}` | {taken['merged']} | {taken['shared']} | {'over' if taken['shared'] > target else 'within'} |"
        for case, taken in seconds.items()
    ]
    shared = [taken["shared"] for taken in seconds.values()]
    return "\n".join(
        [
            "# Shared dishes: wall time",
            "",
            "> Wall time on the machine that generated it, so it differs by machine and is kept out of "
            "`latest.*`. These runs let the variety pass finish instead of cutting it at its two seconds, so "
            "the plans do not depend on the machine; the product cuts it, and takes correspondingly less. The "
            "target is about 4 seconds for a common request (ADR-0075); a case over it is marked, and the "
            "`merged` column shows how much of that the shared-dish model added. Speed is the algorithm "
            "layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).",
            "",
            f"Median of the shared arrangement: {statistics.median(shared):.2f} s. Slowest: {max(shared):.2f} s.",
            "",
            "| Case | merged (s) | shared (s) | Against the 4 s target |",
            "|---|---:|---:|:---:|",
            *rows,
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-report", type=Path, default=Path("docs/evaluation/shared-dish/latest.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("docs/evaluation/shared-dish/latest.md"))
    parser.add_argument("--timing-report", type=Path, default=None)
    args = parser.parse_args()
    report, seconds = evaluate()
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    args.markdown_report.write_text(markdown(report), encoding="utf-8", newline="\n")
    if args.timing_report is not None:
        args.timing_report.parent.mkdir(parents=True, exist_ok=True)
        args.timing_report.write_text(timing_markdown(seconds), encoding="utf-8", newline="\n")
    print(f"Shared dish: {'PASS' if report['passed'] else 'FAIL'} (violations {report['safety_violations']})")
    for case in report["cases"]:
        shared = case["runs"]["shared"]
        taken = seconds[case["case"]]
        state = shared["outcome"] if shared["outcome"] != "planned" else ("passed" if case["passed"] else "FAILED")
        print(f"  {case['case']}: {state}; merged {taken['merged']} s, shared {taken['shared']} s")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
