"""Sweep synthetic meal-day-week households through the product path and report their variety.

Every run is a developer episode (mdw-dev-008) given one plan shape, household size and set of
safety limits, its pool drawn as the v3 runner's episodes are, at a budget a fixed multiple of the
label's own witness week (the cheapest week the label search found unbudgeted), and labelled by the
label search's own proof under that budget. The
week is planned by `meal_day_week_runner.evaluate`, and its variety counted twice: by recipe id,
and by dish kind, the planner's measure of sameness (`dish_kind`). Fixture prices, no model calls,
synthetic and developer episodes only.

    python -m app.evaluation.variety_sweep \\
        --json-report docs/evaluation/v3-meal-day-week/variety-sweep/latest.json \\
        --markdown-report docs/evaluation/v3-meal-day-week/variety-sweep/latest.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from app.core.paths import repository_root
from app.evaluation.meal_day_week_runner import code_revision, evaluate
from app.evaluation.multidish_labels import check, week_evidence
from app.evaluation.multidish_pool import draw

DEV_EPISODES = Path("data/evaluation/dev/v3-meal-day-week/episodes")
BASE_EPISODE = DEV_EPISODES / "mdw-dev-008.json"

BREAKFAST = [{"role_id": "main", "courses": ["breakfast", "baked_good"], "required": True}]
LUNCH = [{"role_id": "main", "courses": ["main", "salad", "soup"], "required": True}]
DINNER = [
    {"role_id": "main", "courses": ["main"], "required": True},
    {"role_id": "vegetable", "courses": ["side", "salad"], "required": False},
]
DINNER_WITH_SOUP = [
    {"role_id": "main", "courses": ["main"], "required": True},
    {"role_id": "vegetable", "courses": ["side", "salad"], "required": True},
    {"role_id": "soup", "courses": ["soup"], "required": True},
]

SHAPES = {
    "dinner": {"dinner": DINNER},
    "dinner with soup": {"dinner": DINNER_WITH_SOUP},
    "lunch + dinner": {"lunch": LUNCH, "dinner": DINNER},
    "composed lunch + dinner": {"lunch": DINNER, "dinner": DINNER},
    "three meals": {"breakfast": BREAKFAST, "lunch": LUNCH, "dinner": DINNER},
    "three meals, dinner with soup": {"breakfast": BREAKFAST, "lunch": LUNCH, "dinner": DINNER_WITH_SOUP},
}
SIZES = (2, 4)
# The demo household's limits (Sprint 1 demo skeleton): a peanut allergy and no pork.
SAFETY = {"none": ((), ()), "peanut, no pork": (("peanut",), ("pork",))}
# Tight, roomy and loose: a multiple of the label's witness week, which proves each budget feasible.
BUDGET_FACTORS = (1.15, 1.5, 3.0)
LABELS = {"feasible_proven": "feasible", "infeasible_proven": "infeasible"}
PARAMETERS = {
    "base_episode": "mdw-dev-008 (developer set)",
    "shapes": ", ".join(SHAPES),
    "household_sizes": ", ".join(map(str, SIZES)),
    "safety": ", ".join(SAFETY),
    "budget": "the label's witness week times " + ", ".join(map(str, BUDGET_FACTORS)),
    "pricing_mode": "fixture",
    "dish_kind": "app.planning.recipe_quality.dish_kind, the planner's measure of sameness",
    "seconds": "wall time of one run on the machine that generated the report; not a demo timing",
}


def synthetic(
    episode_id: str, meals: dict, *, budget=None, bands=(), size=None, allergens=(), excluded=(), proven=True
) -> dict:
    """A developer episode of this shape and limit, its pool drawn and (unless `proven` is off) its label proven."""
    episode = json.loads((repository_root() / BASE_EPISODE).read_text(encoding="utf-8"))
    episode["episode_id"] = episode_id
    profile = episode["scenario"]["household_profile"]
    if size is not None:
        profile["household_size"] = size
    profile["plan_shape"] = {"meals": meals}
    profile["allergens"], profile["excluded_ingredients"] = list(allergens), list(excluded)
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    order = ("breakfast", "lunch", "dinner")
    episode["scenario"]["planning_horizon"]["slots"] = [f"{d}-{m}" for d in days for m in order if m in meals]
    hard = episode["gold"]["applicable_hard_constraints"]
    hard["budget_sgd"], hard["nutrition_bands"] = budget, list(bands)
    hard["allergens_absent"], hard["excluded_ingredients_absent"] = list(allergens), list(excluded)
    episode["scenario"]["recipe_candidate_slugs"], episode["scenario"]["fairprice_product_ids"] = draw(episode)
    if proven:
        assert check(episode) is None, check(episode)
    return episode


def cases() -> list[dict]:
    """Every shape, size and set of limits, each at every budget factor of its own witness week."""
    found = []
    for shape, meals in SHAPES.items():
        for size in SIZES:
            for safety, (allergens, excluded) in SAFETY.items():
                free = synthetic("unbudgeted", meals, size=size, allergens=allergens, excluded=excluded)
                witness = week_evidence(free)["witness_cost_sgd"]
                for factor in BUDGET_FACTORS:
                    found.append(
                        {
                            "run_id": f"sweep-{len(found) + 1:03d}",
                            "shape": shape,
                            "household_size": size,
                            "safety": safety,
                            "witness_sgd": witness,
                            "budget_factor": factor,
                            "budget_sgd": round(witness * factor, 2),
                        }
                    )
    return found


def run(case: dict) -> dict:
    """One case planned and scored under the label its own proof gives it.

    The pool is drawn under the case's budget, so the witness week of the unbudgeted pool may not be in it:
    a case the label search proves neither way is reported as unproven and not planned."""
    allergens, excluded = SAFETY[case["safety"]]
    episode = synthetic(
        case["run_id"],
        SHAPES[case["shape"]],
        budget=case["budget_sgd"],
        size=case["household_size"],
        allergens=allergens,
        excluded=excluded,
        proven=False,
    )
    label = LABELS.get(week_evidence(episode)["verdict"])
    if label is None:
        return {**case, "label": "unproven", "answered": "-", "strict_success": False, "failed": [], "seconds": 0.0}
    episode["gold"]["class"] = label
    start = time.perf_counter()
    row = evaluate([episode])["episodes"][0]
    seconds = round(time.perf_counter() - start, 2)
    keep = (
        "answered",
        "strict_success",
        "failed",
        "dishes",
        "distinct_recipes",
        "distinct_dish_kinds",
        "most_uses_of_a_recipe",
        "most_uses_of_a_kind",
        "total_cost_sgd",
    )
    return {**case, "label": label, **{key: row[key] for key in keep if key in row}, "seconds": seconds}


def summary(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["answered"] == "plan"]
    return {
        "runs": len(rows),
        "label_unproven": sum(r["label"] == "unproven" for r in rows),
        "label_infeasible": sum(r["label"] == "infeasible" for r in rows),
        "planned": len(planned),
        "refused": sum(r["answered"] == "infeasible" for r in rows),
        "strict_successes": sum(r["strict_success"] for r in rows),
        "over_budget": sum(r["total_cost_sgd"] > r["budget_sgd"] for r in planned),
        "dishes": sum(r["dishes"] for r in planned),
        "distinct_recipes": sum(r["distinct_recipes"] for r in planned),
        "distinct_dish_kinds": sum(r["distinct_dish_kinds"] for r in planned),
        "runs_with_fewer_kinds_than_recipes": sum(r["distinct_dish_kinds"] < r["distinct_recipes"] for r in planned),
        "slowest_seconds": max((r["seconds"] for r in rows), default=0.0),
    }


def markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Variety sweep: synthetic meal-day-week households",
        "",
        "> Scope: synthetic households built on a developer episode; diagnostic only, not held-out evidence.",
        "",
        "Generated by `python -m app.evaluation.variety_sweep`: the product path, fixture prices, no model calls. "
        "Variety is counted by recipe id and by dish kind (`dish_kind`, the planner's measure of sameness): "
        "differently named fried rices are different recipes but one kind. `seconds` is one run's wall time on "
        "the machine that generated the report, not a demo timing.",
        "",
        "The code revision it ran at is `code_revision` in `latest.json` beside this file.",
        "",
        "| Runs | Label unproven | Label infeasible | Planned | Refused | Strict success | Over budget | Dishes "
        "| Distinct recipes | Distinct dish kinds | Runs with fewer kinds than recipes | Slowest run (s) |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {s['runs']} | {s['label_unproven']} | {s['label_infeasible']} | {s['planned']} | {s['refused']} "
        f"| {s['strict_successes']} | {s['over_budget']} "
        f"| {s['dishes']} | {s['distinct_recipes']} | {s['distinct_dish_kinds']} "
        f"| {s['runs_with_fewer_kinds_than_recipes']} | {s['slowest_seconds']} |",
        "",
        "| Run | Shape | Size | Safety | Budget (x witness) | Label | Answered | Success | Failed checks | Dishes "
        "| Distinct recipes | Distinct dish kinds | Most uses of a recipe | Most uses of a kind | Cost | Seconds |",
        "| --- | --- | ---: | --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in report["runs"]:
        lines.append(
            f"| {r['run_id']} | {r['shape']} | {r['household_size']} | {r['safety']} "
            f"| {r['budget_sgd']} ({r['budget_factor']}) | {r['label']} | {r['answered']} "
            f"| {'yes' if r['strict_success'] else 'no'} "
            f"| {', '.join(r['failed']) or '-'} | {r.get('dishes', '-')} | {r.get('distinct_recipes', '-')} "
            f"| {r.get('distinct_dish_kinds', '-')} | {r.get('most_uses_of_a_recipe', '-')} "
            f"| {r.get('most_uses_of_a_kind', '-')} | {r.get('total_cost_sgd', '-')} | {r['seconds']} |"
        )
    lines += ["", "## Parameters", ""]
    lines += [f"- {key}: {value}" for key, value in report["parameters"].items()]
    lines += ["", "Counts only, no rates (ADR-0028).", "", "## Inputs", ""]
    lines += [f"- `{path}`: `{digest}`" for path, digest in sorted(report["inputs"].items())]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--markdown-report", type=Path, required=True)
    args = parser.parse_args()
    root = repository_root()
    rows = []
    for case in cases():
        rows.append(run(case))
        print(f"{case['run_id']} {case['shape']} x{case['household_size']} {case['safety']}: {rows[-1]['answered']}")
    report = {
        "parameters": PARAMETERS,
        "summary": summary(rows),
        "runs": rows,
        "code_revision": code_revision(),
        "inputs": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in (
                BASE_EPISODE.as_posix(),
                "data-engineering/data/release/v2.2/recipes.jsonl",
                "data-engineering/data/release/v2.2/ingredients.jsonl",
                "data/products/fairprice-v2-snapshot.json",
                "data/fixtures/fairprice-products.json",
            )
        },
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    args.markdown_report.write_text(markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
