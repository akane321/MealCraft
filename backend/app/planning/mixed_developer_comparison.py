"""Paired synthetic developer cases for mixed planning, isolated from held-out data."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from statistics import median
from time import perf_counter

from app.planning.beam_planner import BeamLimits
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.mixed_plan_oracle import exhaustive_mixed_plan
from app.planning.mixed_shopping import validate_mixed_shopping
from app.planning.whole_plan_scoring import WholePlanPolicy
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def developer_cases(base: FinalPlanningProblem):
    data = base.model_dump(mode="json")
    template = data["recipes"][0]
    data.update(
        recipes=[
            dict(
                template,
                recipe_id=f"r{i}",
                title=f"Synthetic recipe {i}",
                servings=1,
                allergens=[],
                total_time_minutes=5 + i * 10,
                ingredients=[
                    dict(ingredient_id="rice", quantity=50 + i * 50, unit="g"),
                    dict(ingredient_id="beans", quantity=50, unit="g"),
                ],
                nutrients_per_serving=dict(template["nutrients_per_serving"], protein_g=10 + i * 20),
            )
            for i in range(3)
        ],
        slots=[
            dict(
                data["slots"][0],
                slot_id=f"s{i}",
                planned_date=f"2026-09-{10 + i // 2}",
                servings=1,
                max_time_minutes=30,
                locked_recipe_id=None,
            )
            for i in range(4)
        ],
        products=[
            dict(
                ingredient_id=ingredient,
                product_id=f"{ingredient}-{quantity}",
                package_quantity=quantity,
                package_unit="g",
                price_sgd=price,
                available=True,
            )
            for ingredient in ("rice", "beans")
            for quantity, price in ((150, 2), (100, 1.5))
        ],
        pantry=[dict(ingredient_id="rice", quantity=50, unit="g", priority_use=True)],
        health_preferences=[],
        purchase_budget_sgd=50,
        nutrition_bands=[dict(metric="protein_g", scope="per_day", lower=60, hard=False)],
        catalog_version="synthetic-mixed-developer-v2",
        product_snapshot_version="fixture-mixed-developer-v2",
    )
    for name in (
        "multi-day",
        "household",
        "optional",
        "locked",
        "hard-nutrition",
        "budget-impossible",
        "missing-products",
        "unknown-pantry",
    ):
        case = json.loads(json.dumps(data))
        case["problem_id"] = name
        if name == "household":
            for i, slot in enumerate(case["slots"]):
                slot["servings"] = 1 + i % 3
        elif name == "optional":
            case["slots"][-1]["required"] = False
        elif name == "locked":
            case["slots"][0]["locked_recipe_id"] = "r2"
            case["slots"][-1].update(required=False, locked_recipe_id="r1")
        elif name == "hard-nutrition":
            case["nutrition_bands"][0]["hard"] = True
        elif name == "budget-impossible":
            case["purchase_budget_sgd"] = 1
        elif name == "missing-products":
            case["products"] = []
        elif name == "unknown-pantry":
            case["pantry"][0]["quantity"] = None
        yield FinalPlanningProblem.model_validate(case)


def compare_mixed(base, *, repeats=2, widths=(1, 4, 16), use_cp_sat=False):
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    policy = WholePlanPolicy()
    rows = []
    for problem in developer_cases(base):
        raw = json.dumps(problem.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        oracle = exhaustive_mixed_plan(problem, scoring_policy=policy, use_cp_sat=use_cp_sat)
        for width in widths:
            times, outputs = [], []
            for _ in range(repeats):
                start = perf_counter()
                result = solve_mixed_beam(problem, limits=BeamLimits(width), scoring_policy=policy)
                times.append((perf_counter() - start) * 1000)
                outputs.append(json.dumps(asdict(result), sort_keys=True, allow_nan=False))
            issues = None
            if result.status == "feasible":
                assignments = [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in result.choices]
                issues = validate_mixed_shopping(problem, assignments, result.shopping)
            certified = oracle.status == "optimal_for_frozen_packet"
            gap = result.loss - oracle.best_loss if certified and result.status == "feasible" and not issues else None
            rows.append(
                dict(
                    scenario=problem.problem_id,
                    input_sha256=digest,
                    width=width,
                    status=result.status,
                    validation_issues=issues,
                    loss=result.loss,
                    gap=gap,
                    oracle_status=oracle.status,
                    oracle_loss=oracle.best_loss,
                    oracle_combinations=oracle.total_combinations,
                    missed_feasible=certified and result.status != "feasible",
                    deterministic=len(set(outputs)) == 1,
                    median_ms=median(times),
                )
            )
    return dict(
        dataset="synthetic-mixed-developer-v2",
        scope="developer-only, not held-out or production evidence",
        scoring_policy=policy.version,
        package_solver="cp-sat" if use_cp_sat else "enumeration",
        repeats=repeats,
        rows=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--cp-sat", action="store_true")
    args = parser.parse_args()
    base = FinalPlanningProblem.model_validate_json(args.fixture.read_text(encoding="utf-8-sig"))
    print(json.dumps(compare_mixed(base, use_cp_sat=args.cp_sat), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
