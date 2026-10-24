"""Developer-only LNS sweep: catalog recipes, synthetic prices, no model calls."""

import argparse
import json
from datetime import timedelta
from itertools import product
from pathlib import Path
from time import perf_counter

from app.evaluation.algorithm_environment import environment
from app.planning.algorithm_lns import LargeNeighborhoodPlanner
from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.algorithm_search import SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.schemas.planning_v2 import PlanningSlotMember
from tests.test_diversity_greedy import real_recipe_problem


def write_summary(output, stem="lns-sweep"):
    lines = [
        "# LNS developer sweep",
        "",
        output["scope"],
        "",
        "LNS times include its greedy seed. Each configuration is measured once per seed. "
        "This is a small developer sweep, not repeated latency or product acceptance evidence.",
        "",
        "| Recipes/dinners/members | Algorithm | Parameters | Member mean/min | Table kinds | "
        "Checkout S$ | Total ms | Matches full reference score |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in output["rows"]:
        for row in case["runs"]:
            d = row["diversity"]
            label = f"{case['recipes']}/{case['days']}/{case['members']}"
            lines.append(
                f"| {label} | {row['algorithm']} | {json.dumps(row['parameters'], sort_keys=True)} | "
                f"{d['member_mean']}/{d['member_min']} | {d['table_kinds']} | {row['price_sgd']:.2f} | "
                f"{row['total_with_seed_ms']:.1f} | {row['matches_reference']} |"
            )
    lines += [
        "",
        "Reference status, full score, environment and repair timings: [JSON](lns-sweep.json). "
        "The reference optimizes variety first; its price is not a global minimum-price claim. "
        "No production default is selected from these three cases.",
        "",
    ]
    text = "\n".join(lines).replace("(lns-sweep.json)", f"({stem}.json)")
    Path(f"docs/evaluation/algorithm-dev/{stem}.md").write_text(text, encoding="utf-8")


def run(extended=False):
    output = {
        "environment": environment(),
        "scope": "Developer catalog recipes; synthetic products/prices; single-dish dinners; no held-out data. "
        "LNS starts from the same greedy seed. Native reference has a 30-second diagnostic limit; "
        "LNS repairs have no wall-clock cutoff. Member grouping uses existing unreviewed similarity policy.",
        "rows": [],
    }
    stem = "lns-extended" if extended else "lns-sweep"
    target = Path(f"docs/evaluation/algorithm-dev/{stem}.json")
    cases = ((16, 14, 2),) if extended else ((8, 7, 2), (16, 7, 6), (16, 14, 2))
    for count, days, size in cases:
        problem, objective = real_recipe_problem(count)
        first = problem.slots[0]
        members = [PlanningSlotMember(name=f"adult-{i}", servings=1) for i in range(size)]
        problem.slots = [
            first.model_copy(
                update={
                    "slot_id": f"d{i}",
                    "planned_date": first.planned_date + timedelta(days=i),
                    "trip": 1 if i < 7 else 2,
                    "members": members,
                    "servings": size,
                }
            )
            for i in range(days)
        ]
        candidates = MealBeamPlanner(
            MealBeamLimits(candidates_per_role=count, meal_options_per_slot=64), local_losses=objective.ranking
        )
        start = perf_counter()
        seed = DiversityAwareGreedyPlanner(objective, candidates).solve(problem)
        seed_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        exact = NativeSharedScoreCpSat(objective, candidates).solve_exact(problem, time_limit=30)
        reference_ms = (perf_counter() - start) * 1000
        case = {
            "recipes": count,
            "days": days,
            "members": size,
            "seed_ms": seed_ms,
            "reference_ms": reference_ms,
            "reference": exact,
            "runs": [],
        }
        output["rows"].append(case)
        configurations = [
            ("greedy", {}, None),
            ("beam", {"width": 8}, SharedObjectiveBeamPlanner),
            ("annealing", {"steps": 50, "seed": 0}, AnnealingPlanner),
        ]
        grid = product((4, 7), (8, 16), (0, 1, 2)) if extended else product((2, 4), (2, 4), (0, 1))
        configurations += [
            ("lns", {"destroy_size": d, "iterations": n, "seed": s}, LargeNeighborhoodPlanner)
            for d, n, s in grid
        ]
        for name, params, engine in configurations:
            start = perf_counter()
            planner = engine(objective, candidates, **params) if engine else None
            result = (
                planner.solve(problem, initial=seed) if name == "lns" else planner.solve(problem) if planner else seed
            )
            elapsed = seed_ms if name == "greedy" else (perf_counter() - start) * 1000
            valid = result.status == "feasible" and result.validation.status == "passed"
            score = objective.score_validated(problem, result.assignments, result.validation) if valid else None
            proven = exact["status"] == "optimal_for_native_model"
            case["runs"].append(
                {
                    "algorithm": name,
                    "parameters": params,
                    "status": result.status,
                    "validation": result.validation.status,
                    "score": score,
                    "diversity": objective.diversity(problem, result.assignments),
                    "price_sgd": result.validation.purchase_total_sgd,
                    "solve_ms": elapsed,
                    "total_with_seed_ms": elapsed + seed_ms if name == "lns" else elapsed,
                    "matches_reference": score == exact.get("score") if proven else None,
                    "repairs": planner.repairs if name == "lns" else [],
                }
            )
            target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
            print(count, days, size, name, params, result.status, round(elapsed), flush=True)
            if not valid:
                raise RuntimeError("Scenario failed validation; partial evidence saved")
    write_summary(output, stem)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extended", action="store_true", help="Expand the 14-dinner developer sweep")
    run(parser.parse_args().extended)
