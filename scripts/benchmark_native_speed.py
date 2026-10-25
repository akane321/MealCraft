"""Alternating before/after timings on an identical developer packet."""

import json
from datetime import timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

from app.evaluation.algorithm_environment import environment
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from tests.test_diversity_greedy import real_recipe_problem


def run():
    problem, objective = real_recipe_problem(16)
    first = problem.slots[0]
    problem.slots = [
        first.model_copy(
            update={
                "slot_id": f"d{i}",
                "planned_date": first.planned_date + timedelta(days=i),
                "trip": 1 if i < 7 else 2,
            }
        )
        for i in range(14)
    ]
    candidates = MealBeamPlanner(
        MealBeamLimits(candidates_per_role=16, meal_options_per_slot=64),
        local_losses=objective.ranking,
    )
    rows = []
    for repeat in range(3):
        for optimize in (False, True) if repeat % 2 == 0 else (True, False):
            start = perf_counter()
            result = NativeSharedScoreCpSat(objective, candidates).solve_exact(
                problem,
                time_limit=20,
                optimize=optimize,
            )
            row = {
                "repeat": repeat,
                "optimized": optimize,
                "wall_ms": (perf_counter() - start) * 1000,
                **{k: result.get(k) for k in ("status", "score", "build_ms", "stage_ms", "symmetry_pairs", "workers")},
            }
            rows.append(row)
            print(optimize, result["status"], round(row["wall_ms"], 2), flush=True)
    summaries = {str(flag): median(r["wall_ms"] for r in rows if r["optimized"] == flag) for flag in (False, True)}
    Path("docs/evaluation/algorithm-dev/native-speed.json").write_text(
        json.dumps(
            {
                "scope": (
                    "16 developer recipes; 14 single-dish dinners; synthetic prices; "
                    "no slot members; three alternating repeats"
                ),
                "environment": environment(),
                "median_ms": summaries,
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
