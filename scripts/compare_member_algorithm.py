"""Synthetic member-level regression evidence, not a product performance study."""

import json
from pathlib import Path
from time import perf_counter

from app.evaluation.algorithm_environment import environment
from app.planning.algorithm_cp_sat import SharedScoreCpSat
from app.planning.algorithm_reference import AnnealingPlanner, EnumeratedReference
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from tests.test_algorithm_member_diversity import family, shared_family


def run():
    metadata = environment()
    rows = []
    for name, (problem, objective) in (
        ("couple-different-diets-and-attendance", family(2)),
        ("six-adults", family(6)),
        ("couple-shared-dishes", shared_family()),
    ):
        for engine in (
            EnumeratedReference,
            SharedScoreCpSat,
            NativeSharedScoreCpSat,
            DiversityAwareGreedyPlanner,
            GraspPlanner,
            LocalSearchPlanner,
            SharedObjectiveBeamPlanner,
            AnnealingPlanner,
        ):
            planner = engine(objective)
            start = perf_counter()
            if engine is EnumeratedReference:
                result = planner.solve_reference(problem)
            elif engine in (SharedScoreCpSat, NativeSharedScoreCpSat):
                result = planner.solve_exact(problem)
            else:
                solution = planner.solve(problem)
                result = {
                    "status": solution.status,
                    "validation": solution.validation.status,
                    "score": objective.score_validated(problem, solution.assignments, solution.validation)
                    if solution.status == "feasible"
                    else None,
                    "diversity": objective.diversity(problem, solution.assignments),
                }
            rows.append(
                {
                    "case": name,
                    "algorithm": engine.__name__,
                    "elapsed_ms": (perf_counter() - start) * 1000,
                    "result": result,
                }
            )
            if not (result["status"].startswith("optimal_for_") or result["status"] == "feasible"):
                raise RuntimeError(f"{name}: {engine.__name__} rejected the fixture")
    output = {
        "scope": (
            "Three synthetic two-dinner household fixtures; synthetic prices; one run per arm; "
            "whole-table and present-member counts; not held-out or product latency evidence"
        ),
        "environment": metadata,
        "rows": rows,
    }
    Path("docs/evaluation/algorithm-dev/member-smoke.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(rows)} successful case/algorithm runs")


if __name__ == "__main__":
    run()
