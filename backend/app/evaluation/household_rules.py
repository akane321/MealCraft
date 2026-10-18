"""What the household block changes in a planned week (layer 08): one fixed household, planned with and without it.

The same request (lunch and dinner, fixture prices, the curated catalog) is planned twice through
`WeeklyMealPlanService.generate`: once as a bare household size, once with members, who is home, a weekday
dinner time rule and a daily sodium limit. The report counts what the rules change and checks each one held:
servings follow who is home, basics leave the list, the time rule and the sodium band hold. No model is called.

    python -m app.evaluation.household_rules
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.meal_plans import build_meal_plan_service
from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.household_reference import basic_seasonings, meal_shares
from app.db.base import Base
from app.repositories.recipe import clear_planning_pool
from app.schemas.meal_plan import WeeklyMealPlanRequest

ONE_MAIN = [{"role_id": "main", "courses": ["main"]}]
BASE = {
    "start_date": "2027-01-03",  # a Sunday
    "household_size": 3,
    "pricing_mode": "fixture",
    "plan_shape": {"meals": {"lunch": ONE_MAIN, "dinner": ONE_MAIN}},
}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
SODIUM_MG_PER_DAY = 2000
WEEKDAY_DINNER_MINUTES = 30


def _rule(text: str, **fields) -> dict:
    return {"source_text": text, "restatement": "-", **fields}


# Two adults and a child at the HPB defaults (adult male and female, child of either sex), and a grandparent who
# comes for weekend dinners.
HOUSEHOLD = {
    "members": [
        {"name": "Ann", "servings": 0.88},
        {"name": "Ben", "servings": 1.12},
        {"name": "Mei", "servings": 0.73},
        {"name": "Grandma", "servings": 0.81, "default_present": False},
    ],
    "presence_rules": [
        _rule("孩子工作日午饭在学校吃", member_name="Mei", present=False, weekdays=WEEKDAYS, meal_types=["lunch"]),
        _rule(
            "I work late on Wednesday evenings",
            member_name="Ann",
            present=False,
            weekdays=["wednesday"],
            meal_types=["dinner"],
        ),
        _rule(
            "Grandma joins us for dinner on weekends",
            member_name="Grandma",
            present=True,
            weekdays=["saturday", "sunday"],
            meal_types=["dinner"],
        ),
    ],
    "cooking_time_rules": [
        _rule(
            "weekday dinners within 30 minutes",
            weekdays=WEEKDAYS,
            meal_types=["dinner"],
            max_minutes=WEEKDAY_DINNER_MINUTES,
        ),
    ],
    "nutrition_limits": [{"nutrient": "sodium_mg", "max_value": SODIUM_MG_PER_DAY}],
}


def _week(session, request: dict) -> dict:
    plan = build_meal_plan_service(session, 1).generate(WeeklyMealPlanRequest.model_validate(request))
    return plan.model_dump(mode="json")


def _summary(week: dict, recipes: dict) -> dict:
    basics = set(basic_seasonings())
    used = {name for d in week["days"] for name in recipes[d["recipe"]["slug"]]["ingredients"]}
    listed = {item["ingredient_name"] for item in week["grocery_estimate"]["items"]}
    return {
        "meals_planned": len(week["days"]),
        "servings_by_meal": [
            {
                "day": date.fromisoformat(d["planned_date"]).strftime("%A").lower(),
                "meal": d["meal_type"],
                "recipe": d["recipe"]["slug"],
                "servings": d["servings"],
                "minutes": recipes[d["recipe"]["slug"]]["minutes"],
                "sodium_mg_per_person": d["nutrition_per_person"]["sodium_mg"],
            }
            for d in week["days"]
        ],
        "basics_used": sorted(used & basics),
        "basics_on_list": sorted(listed & basics),
        "grocery_lines": len(listed),
        "purchase_total_sgd": week["grocery_estimate"]["purchase_total_sgd"],
        "warnings": week["warnings"],
    }


def _checks(plain: dict, ruled: dict) -> dict[str, bool]:
    members = {m["name"]: m["servings"] for m in HOUSEHOLD["members"]}
    home = {"Ann", "Ben", "Mei"}

    def expected(day: str, meal: str) -> float:
        present = set(home)
        if meal == "lunch" and day in WEEKDAYS:
            present.discard("Mei")
        if meal == "dinner" and day == "wednesday":
            present.discard("Ann")
        if meal == "dinner" and day in ("saturday", "sunday"):
            present.add("Grandma")
        return round(sum(members[name] for name in present), 2)

    rows = ruled["servings_by_meal"]
    daily: dict[str, float] = {}
    for row in rows:
        daily[row["day"]] = daily.get(row["day"], 0) + row["sodium_mg_per_person"]
    share = sum(meal_shares()[meal] for meal in BASE["plan_shape"]["meals"])
    return {
        "without_the_block_servings_are_unset": all(row["servings"] is None for row in plain["servings_by_meal"]),
        "every_meal_cooks_for_the_members_home": all(
            row["servings"] == expected(row["day"], row["meal"]) for row in rows
        ),
        "weekday_dinners_keep_the_time_rule": all(
            row["minutes"] <= WEEKDAY_DINNER_MINUTES
            for row in rows
            if row["meal"] == "dinner" and row["day"] in WEEKDAYS
        ),
        "each_day_keeps_its_share_of_the_sodium_limit": all(
            value <= SODIUM_MG_PER_DAY * share + 1e-6 for value in daily.values()
        ),
        "basics_are_bought_without_the_block": set(plain["basics_used"]) <= set(plain["basics_on_list"]),
        "basics_leave_the_list_with_the_block": not ruled["basics_on_list"],
    }


def evaluate() -> dict:
    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    recipes = {
        r.slug: {
            "ingredients": [i.ingredient for i in r.ingredients],
            "minutes": r.prep_time_minutes + r.cook_time_minutes,
        }
        for r in catalog.recipes
    }
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    clear_planning_pool()
    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            import_catalog(session, catalog)
            plain = _summary(_week(session, BASE), recipes)
            ruled = _summary(_week(session, {**BASE, "household": HOUSEHOLD}), recipes)
    finally:
        clear_planning_pool()
        engine.dispose()
    checks = _checks(plain, ruled)
    return {
        "report": "household-rules-v1",
        "request": BASE,
        "household": HOUSEHOLD,
        "passed": all(checks.values()),
        "checks": checks,
        "without_household": plain,
        "with_household": ruled,
    }


def markdown(report: dict) -> str:
    plain, ruled = report["without_household"], report["with_household"]
    lines = [
        "# Household rules: one week with and without the household block",
        "",
        "> Scope: one fixed household on the curated catalog, fixture prices, the product path. It shows what "
        "layer 08's rules change; it is a regression check, not a quality score.",
        "",
        "Generated by `python -m app.evaluation.household_rules`.",
        "",
        f"**Overall result: {'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| Check | Result |",
        "|---|:---:|",
        *[f"| `{name}` | {'PASS' if ok else 'FAIL'} |" for name, ok in report["checks"].items()],
        "",
        "| | Without the block | With the block |",
        "|---|---:|---:|",
        f"| Meals planned | {plain['meals_planned']} | {ruled['meals_planned']} |",
        f"| Grocery lines | {plain['grocery_lines']} | {ruled['grocery_lines']} |",
        f"| Basics used | {len(plain['basics_used'])} | {len(ruled['basics_used'])} |",
        f"| Basics on the list | {len(plain['basics_on_list'])} | {len(ruled['basics_on_list'])} |",
        f"| Purchase total (SGD) | {plain['purchase_total_sgd']} | {ruled['purchase_total_sgd']} |",
        "",
        "## Meals with the block",
        "",
        "| Day | Meal | Recipe | Servings | Minutes | Sodium per person (mg) |",
        "|---|---|---|---:|---:|---:|",
        *[
            f"| {r['day']} | {r['meal']} | {r['recipe']} | {r['servings']} | {r['minutes']} | "
            f"{r['sodium_mg_per_person']} |"
            for r in ruled["servings_by_meal"]
        ],
        "",
        "## Warnings with the block",
        "",
        *[f"- {warning}" for warning in ruled["warnings"]],
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-report", type=Path, default=Path("docs/evaluation/household-rules/latest.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("docs/evaluation/household-rules/latest.md"))
    args = parser.parse_args()
    report = evaluate()
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    args.markdown_report.write_text(markdown(report), encoding="utf-8", newline="\n")
    print(f"Household rules: {'PASS' if report['passed'] else 'FAIL'}")
    for name, ok in report["checks"].items():
        print(f"  {name}: {ok}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
