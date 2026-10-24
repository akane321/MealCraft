"""Synthetic household horizon comparison; no held-out data or paid calls."""

import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from app.evaluation.algorithm_environment import environment
from app.planning.algorithm_lns import LargeNeighborhoodPlanner
from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from tests.test_algorithm_member_diversity import family, shared_family


def household_case(kind, days):
    problem, objective = shared_family() if kind == "shared" else family(6 if kind == "six" else 2)
    templates = problem.slots
    first = templates[0].planned_date
    problem.slots = [
        templates[i % len(templates)].model_copy(
            deep=True,
            update={"slot_id": f"d{i}", "planned_date": first + timedelta(days=i), "trip": 1 if i < 7 else 2},
        )
        for i in range(days)
    ]
    return problem, objective


def run():
    output = {
        "environment": environment(),
        "scope": "Synthetic three-recipe households, synthetic packages/prices, 7/14 dinners; "
        "couple with alternating attendance, six adults including a vegetarian, and two-dish couple dinners. "
        "One run per configuration; grouping is the algorithm near-duplicate policy, not product dish_kind. "
        "No held-out inputs; no product latency or real-price acceptance claim.",
        "rows": [],
    }
    target = Path("docs/evaluation/algorithm-dev/member-lns.json")
    for kind in ("couple", "six", "shared"):
        for days in (7, 14):
            problem, objective = household_case(kind, days)
            start = perf_counter()
            reference = NativeSharedScoreCpSat(objective).solve_exact(problem, time_limit=30)
            case = {
                "case": kind,
                "days": days,
                "reference": reference,
                "reference_ms": (perf_counter() - start) * 1000,
                "runs": [],
            }
            output["rows"].append(case)
            configurations = [
                (DiversityAwareGreedyPlanner, {}),
                (GraspPlanner, {}),
                (LocalSearchPlanner, {}),
                (SharedObjectiveBeamPlanner, {"width": 8}),
                (AnnealingPlanner, {"steps": 50, "seed": 0}),
            ] + [(LargeNeighborhoodPlanner, {"iterations": 4, "destroy_size": 4, "seed": seed}) for seed in (0, 1, 2)]
            for engine, parameters in configurations:
                planner = engine(objective, **parameters)
                start = perf_counter()
                solution = planner.solve(problem)
                elapsed = (perf_counter() - start) * 1000
                valid = solution.status == "feasible" and solution.validation.status == "passed"
                score = objective.score_validated(problem, solution.assignments, solution.validation) if valid else None
                case["runs"].append(
                    {
                        "algorithm": engine.__name__,
                        "parameters": parameters,
                        "status": solution.status,
                        "validation": solution.validation.status,
                        "score": score,
                        "diversity": objective.diversity(problem, solution.assignments),
                        "price_sgd": solution.validation.purchase_total_sgd,
                        "elapsed_ms": elapsed,
                        "matches_reference": score == reference.get("score")
                        if reference["status"] == "optimal_for_native_model"
                        else None,
                        "repairs": planner.repairs if isinstance(planner, LargeNeighborhoodPlanner) else [],
                    }
                )
                target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
                print(kind, days, engine.__name__, parameters, valid, round(elapsed), flush=True)
                if not valid:
                    raise RuntimeError("Household run failed validation; partial evidence saved")
    lines = [
        "# Household LNS developer comparison",
        "",
        output["scope"],
        "",
        "Times include seed construction. Native reference uses a 30-second diagnostic limit; "
        "LNS repairs have no wall-clock cutoff. Only proven references are compared. "
        "This small recipe pool tests household semantics, not catalog-scale performance.",
        "",
        "| Household | Dinners | Algorithm | Parameters | Member mean/min | Table kinds | S$ | ms | Full score match |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for case in output["rows"]:
        for row in case["runs"]:
            d = row["diversity"]
            lines.append(
                f"| {case['case']} | {case['days']} | {row['algorithm']} | {row['parameters']} | "
                f"{d['member_mean']}/{d['member_min']} | {d['table_kinds']} | {row['price_sgd']} | "
                f"{row['elapsed_ms']:.1f} | {row['matches_reference']} |"
            )
    lines += ["", "Machine, source, exact scores and repair outcomes: [JSON](member-lns.json).", ""]
    target.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()
