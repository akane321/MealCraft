"""Small synthetic regression comparison, not a production performance benchmark."""

import json
import platform
from datetime import timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from tests.test_algorithm_cp_sat import household_week
from tests.test_diversity_greedy import real_recipe_problem, setup_problem


def run():
    rows = []
    week, week_objective = real_recipe_problem(8)
    first = week.slots[0]
    week.slots = [
        first.model_copy(update={"slot_id": f"day-{i}", "planned_date": first.planned_date + timedelta(days=i)})
        for i in range(7)
    ]
    short = week.model_copy(deep=True)
    short.slots = short.slots[:3]
    for name, (problem, objective) in (
        ("synthetic-feasible", setup_problem(2)),
        ("synthetic-budget-rejection", setup_problem(1.99)),
        ("real-recipes-synthetic-prices", real_recipe_problem()),
        ("seven-dinners-real-recipes-synthetic-prices", (week, week_objective)),
        ("three-dinners-eight-recipes-synthetic-prices", (short, week_objective)),
        ("composed-week-nutrition-two-trips-synthetic", household_week()),
    ):
        reference_start = perf_counter()
        reference = EnumeratedReference(objective).solve_reference(problem, max_combinations=1000)
        reference["milliseconds"] = (perf_counter() - reference_start) * 1000
        cp_reference = SharedScoreCpSat(objective).solve_exact(problem)
        for planner in (
            DiversityAwareGreedyPlanner,
            GraspPlanner,
            LocalSearchPlanner,
            SharedObjectiveBeamPlanner,
            AnnealingPlanner,
        ):
            times = []
            for _ in range(3):
                start = perf_counter()
                result = planner(objective).solve(problem)
                times.append((perf_counter() - start) * 1000)
            rows.append(
                {
                    "case": name,
                    "budget": problem.purchase_budget_sgd,
                    "algorithm": result.trace.algorithm,
                    "status": result.status,
                    "score": objective.score_validated(problem, result.assignments, result.validation)
                    if result.status == "feasible"
                    else None,
                    "checkout": result.validation.purchase_total_sgd if result.status == "feasible" else None,
                    "milliseconds": times,
                    "median_ms": median(times),
                    "optimality_gap": None,
                    "reference": reference,
                    "matches_reference": (
                        objective.score_validated(problem, result.assignments, result.validation) == reference["score"]
                        if result.status == "feasible" and reference["status"] == "optimal_for_generated_options"
                        else None
                    ),
                    "candidate_count": len(problem.recipes),
                    "cp_sat_reference": cp_reference,
                    "matches_cp_sat_count_table": (
                        objective.score_validated(problem, result.assignments, result.validation)
                        == cp_reference["score"]
                        if result.status == "feasible"
                        and cp_reference["status"] in ("optimal_for_count_table", "optimal_for_generated_options")
                        else None
                    ),
                }
            )
    output = {
        "scope": "Two- and seven-dinner developer fixtures, including real recipes with synthetic prices; "
        "3 repeats; cold caches not controlled; no optimality or production latency claim",
        "python": platform.python_version(),
        "rows": rows,
    }
    path = Path("docs/evaluation/algorithm-dev/search-smoke.json")
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    run()
