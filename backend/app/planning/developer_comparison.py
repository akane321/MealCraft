"""Small paired developer comparison; no held-out or live data is used."""

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.whole_plan_scoring import WholePlanPolicy, score_plan
from app.schemas.planning_v2 import FinalPlanningProblem


def developer_packets(base):
    for target in (30, 60, 100, 150):
        for nutrition_weight in (0.5, 1.0):
            data = base.model_dump()
            recipe = data["recipes"][0]
            recipes = []
            for i in range(3):
                row = dict(recipe, recipe_id=str(i), total_time_minutes=5 + 10 * i)
                row["nutrients_per_serving"] = dict(recipe["nutrients_per_serving"], protein_g=10 + 20 * i)
                recipes.append(row)
            slot = data["slots"][0]
            data.update(
                problem_id=f"dev-target-{target}-weight-{nutrition_weight}",
                recipes=recipes,
                slots=[dict(slot, slot_id=str(i), locked_recipe_id=None, max_time_minutes=60) for i in range(3)],
                nutrition_bands=[{"metric": "protein_g", "scope": "per_day", "lower": target, "hard": False}],
                preference_weights={
                    "nutrition": nutrition_weight,
                    "time": 1 - nutrition_weight,
                    "variety": 0,
                    "pantry": 0,
                    "health": 0,
                },
                health_preferences=[],
                purchase_budget_sgd=None,
            )
            yield FinalPlanningProblem.model_validate(data)


def compare(base, repeats=3):
    policy = WholePlanPolicy()
    rows = []
    for problem in developer_packets(base):
        oracle = exhaustive_assignments(problem, scoring_policy=policy)
        digest = hashlib.sha256(problem.model_dump_json().encode()).hexdigest()
        methods = [("greedy", FinalScopeReferencePlanner())]
        for width in (1, 4, 16, 32):
            methods.extend(
                [
                    (f"reference-beam-{width}", BeamPlanner(BeamLimits(width))),
                    (f"whole-beam-{width}", BeamPlanner(BeamLimits(width), policy)),
                ]
            )
        for name, engine in methods:
            times, outputs = [], []
            for _ in range(repeats):
                start = perf_counter()
                result = engine.solve(problem)
                times.append((perf_counter() - start) * 1000)
                outputs.append(result.model_dump_json())
            loss = score_plan(problem, result.assignments, policy).total_loss if result.status == "feasible" else None
            gap = (
                loss - oracle.best_loss
                if loss is not None and oracle.status == "optimal_for_fixed_shopping_policy"
                else None
            )
            rows.append(
                {
                    "scenario": problem.problem_id,
                    "input_sha256": digest,
                    "method": name,
                    "status": result.status,
                    "whole_plan_loss": loss,
                    "oracle_loss": oracle.best_loss,
                    "gap": gap,
                    "median_ms": median(times),
                    "deterministic": len(set(outputs)) == 1,
                }
            )
    return {
        "scope": "eight synthetic developer packets, fixed shopping policy, not held-out evidence",
        "policy": policy.version,
        "repeats": repeats,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    base = FinalPlanningProblem.model_validate_json(args.fixture.read_text(encoding="utf-8-sig"))
    print(json.dumps(compare(base), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
