"""Time the product's week planning (ADR-0046 section 3: a plan answers within 10 s).

Plans each shape through `WeeklyMealPlanService.generate` with fixture prices, once to warm the
candidate cache and then REPEATS times, and prints the median and slowest wall time with the time
spent in meal-beam searches. Shapes run on the whole release catalog; episode files run on their
drawn pool, as the v3 runner plans them. Developer and synthetic episodes only.

    python -m app.evaluation.plan_timing [--repeats 5] [EPISODE.json ...]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from app.api.routes.meal_plans import build_meal_plan_service
from app.data.release_v2 import release_dir
from app.evaluation.meal_day_week_runner import HOUSEHOLD, plan_request, product_database
from app.planning import meal_beam
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.schemas.meal_plan import MEAL_PRESETS, WeeklyMealPlanRequest

LUNCH, DINNER = MEAL_PRESETS["lunch"]["one dish"], MEAL_PRESETS["dinner"]
SHAPES = {
    "lunch + dinner": {"lunch": LUNCH, "dinner": DINNER["main and vegetable"]},
    "three meals": {
        "breakfast": MEAL_PRESETS["breakfast"]["one dish"],
        "lunch": LUNCH,
        "dinner": DINNER["main and vegetable"],
    },
    "dinner with soup": {"dinner": DINNER["main, vegetable and soup"]},
}
BUDGETS = {"lunch + dinner": (None, 100.0, 200.0), "three meals": (None, 180.0), "dinner with soup": (None, 110.0)}
# The 2026-10-02 walkthrough household (`tests/test_varied_weeks.py`): dinner with soup for S$100, a peanut
# allergy, no pork and the profile's hour to cook.
WALKTHROUGH = {"allergens": ["peanut"], "excluded_ingredients": ["pork"], "max_cooking_time_minutes": 60}


def timed(plans, request: WeeklyMealPlanRequest, repeats: int) -> str:
    searches: list[float] = []
    original = meal_beam.MealBeamPlanner.search_candidates

    def spy(self, problem):
        start = time.perf_counter()
        try:
            return original(self, problem)
        finally:
            searches.append(time.perf_counter() - start)

    meal_beam.MealBeamPlanner.search_candidates = spy
    walls, outcome = [], ""
    try:
        for run in range(repeats + 1):  # the first run warms the candidate cache
            searches.clear()
            start = time.perf_counter()
            try:
                plan = plans.generate(request)
                titles = [dish.recipe.title for dish in plan.days]
                outcome = f"{len(set(titles))} of {len(titles)} distinct, S${plan.grocery_estimate.purchase_total_sgd}"
            except WeeklyPlanSelectionError:
                outcome = "refused"
            if run:
                walls.append(time.perf_counter() - start)
    finally:
        meal_beam.MealBeamPlanner.search_candidates = original
    return (
        f"median {statistics.median(walls):5.2f} s  max {max(walls):5.2f} s  "
        f"({len(searches)} searches, {sum(searches):.2f} s)  {outcome}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("episodes", type=Path, nargs="*")
    args = parser.parse_args()
    if not args.episodes:
        lines = (release_dir() / "recipes.jsonl").read_text("utf-8").splitlines()
        catalog = {"scenario": {"recipe_candidate_slugs": [json.loads(line)["recipe_id"] for line in lines]}}
        with product_database(catalog) as factory, factory() as session:
            plans = build_meal_plan_service(session, HOUSEHOLD)
            cases = [(name, meals, budget, {}) for name, meals in SHAPES.items() for budget in BUDGETS[name]]
            cases.append(("walkthrough 2026-10-02", SHAPES["dinner with soup"], 100.0, WALKTHROUGH))
            for name, meals, budget, household in cases:
                request = WeeklyMealPlanRequest.model_validate(
                    {
                        "start_date": "2026-09-28",
                        "household_size": 2,
                        "max_cooking_time_minutes": 240,
                        "weekly_budget_sgd": budget,
                        "plan_shape": {"meals": meals},
                        "pricing_mode": "fixture",
                        **household,
                    }
                )
                label = f"{name}, {'no budget' if budget is None else f'S${budget:.0f}'}"
                print(f"{label:34} {timed(plans, request, args.repeats)}", flush=True)
    for path in args.episodes:
        episode = json.loads(path.read_text(encoding="utf-8"))
        with product_database(episode) as factory, factory() as session:
            plans = build_meal_plan_service(session, HOUSEHOLD)
            print(f"{episode['episode_id']:28} {timed(plans, plan_request(episode), args.repeats)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
