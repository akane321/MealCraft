"""Native CP-SAT scale checks; real recipes, synthetic products, no API calls."""

import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.schemas.planning_v2 import PlanningNutritionBand, PlanningRepetitionRules
from tests.test_algorithm_cp_sat import household_week
from tests.test_diversity_greedy import real_recipe_problem


def run():
    cases = [("composed-week", *household_week())]
    soft_problem, soft_objective = household_week()
    soft_problem.nutrition_bands.append(
        PlanningNutritionBand(metric="calories_kcal", scope="horizon_average", lower=500, upper=650, hard=False)
    )
    soft_objective.scales["nutrition_calories_kcal_horizon_average"] = 500
    soft_problem.repetition_rules = PlanningRepetitionRules(
        max_uses_per_recipe=7,
        recipe_counts=[{"recipe_id": "chicken", "min_uses": 7, "max_uses": 7}],
        ingredient_meals=[{"ingredient_id": "spinach", "min_meals": 7}],
    )
    cases.append(("composed-week-soft-nutrition-repeat-rules", soft_problem, soft_objective))
    for count, days in ((8, 7), (16, 7), (16, 14)):
        problem, objective = real_recipe_problem(count)
        first = problem.slots[0]
        problem.slots = [
            first.model_copy(
                update={
                    "slot_id": f"d{i}",
                    "planned_date": first.planned_date + timedelta(days=i),
                    "trip": 1 if i < 7 else 2,
                }
            )
            for i in range(days)
        ]
        cases.append((f"recipes-{count}-days-{days}", problem, objective))
    rows = []
    for name, problem, objective in cases:
        candidates = MealBeamPlanner(
            MealBeamLimits(candidates_per_role=len(problem.recipes), meal_options_per_slot=64),
            local_losses=objective.ranking,
        )
        started = perf_counter()
        native = NativeSharedScoreCpSat(objective, candidates).solve_exact(problem, time_limit=20)
        native_wall = (perf_counter() - started) * 1000
        started = perf_counter()
        greedy = DiversityAwareGreedyPlanner(objective, candidates).solve(problem)
        greedy_ms = (perf_counter() - started) * 1000
        score = (
            objective.score_validated(problem, greedy.assignments, greedy.validation)
            if greedy.status == "feasible"
            else None
        )
        row = {
            "case": name,
            "recipes": len(problem.recipes),
            "slots": len(problem.slots),
            "native": native,
            "native_wall_ms": native_wall,
            "greedy_status": greedy.status,
            "greedy_score": score,
            "greedy_ms": greedy_ms,
            "matches_native_optimum": score == native.get("score")
            if native["status"] == "optimal_for_native_model"
            else None,
        }
        rows.append(row)
        print(name, native["status"], round(native_wall, 2), "ms", flush=True)
    Path("docs/evaluation/algorithm-dev/native-scale.json").write_text(
        json.dumps(
            {"scope": "Single local timing; synthetic prices; generated candidates; not product latency", "rows": rows},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
