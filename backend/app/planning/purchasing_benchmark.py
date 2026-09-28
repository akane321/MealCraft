"""Synthetic package-solver scaling evidence, separate from held-out evaluation."""

import argparse
import json
import platform
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import median
from time import perf_counter

from app.planning.package_cp_sat import solve_packages_cp_sat
from app.planning.package_optimizer import optimize_packages
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import PlanningProductOption


def synthetic_cases():
    """Versioned deterministic cases; demand is already aggregated and pantry-net."""
    cases = []
    for name, ingredients, options in (("small", 1, 3), ("medium", 8, 4), ("enumeration-cap", 24, 8)):
        demands, products = [], []
        for index in range(ingredients):
            ingredient = f"synthetic-{index}"
            demands.append({"ingredient_id": ingredient, "required": 725 + 25 * (index % 4), "unit": "g"})
            for option in range(options):
                products.append(
                    PlanningProductOption(
                        ingredient_id=ingredient,
                        product_id=f"{ingredient}-pack-{option}",
                        package_quantity=100 + 50 * option,
                        package_unit="g",
                        price_sgd=(110 + 37 * option) / 100,
                    )
                )
        cases.append((name, demands, products))
    return cases


def benchmark_case(name, demands, products, *, repeats=3, max_combinations=100000, deterministic_limit=1.0):
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 20:
        raise ValueError("repeats must be between 1 and 20")
    payload = {"demands": demands, "products": [p.model_dump(mode="json") for p in products]}
    result = {
        "case": name,
        "input_sha256": sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "input": payload,
        "ingredient_count": len(demands),
        "product_count": len(products),
        "repeats": repeats,
        "max_combinations_per_ingredient": max_combinations,
        "cp_sat_deterministic_limit_per_ingredient": deterministic_limit,
        "solvers": {},
    }
    for solver in ("enumeration", "cp_sat"):
        samples, runs = [], []
        for _ in range(repeats):
            rows = []
            started = perf_counter()
            for demand in demands:
                args = (demand["ingredient_id"], demand["required"], demand["unit"], products)
                detail = ""
                if solver == "enumeration":
                    purchase = optimize_packages(*args, max_combinations=max_combinations)
                    status = purchase.status
                else:
                    try:
                        oracle = solve_packages_cp_sat(*args, deterministic_limit=deterministic_limit)
                        purchase, status, detail = oracle.result, oracle.status, oracle.detail
                    except ImportError:
                        purchase, status, detail = None, "unavailable", "Optional OR-Tools dependency unavailable"
                errors = validate_packages(*args[:3], purchase, products) if status == "optimal" else ()
                rows.append(
                    {
                        "ingredient_id": demand["ingredient_id"],
                        "status": "invalid_result" if errors else status,
                        "validation_errors": list(errors),
                        "detail": detail,
                        "purchase": asdict(purchase) if purchase is not None else None,
                    }
                )
            samples.append(perf_counter() - started)
            runs.append(rows)
        result["solvers"][solver] = {
            "wall_seconds_samples": samples,
            "median_wall_seconds": median(samples),
            "stable_results": all(rows == runs[0] for rows in runs),
            "runs": runs,
        }
    solvers = result["solvers"]
    complete = all(
        record["stable_results"] and all(row["status"] == "optimal" for row in record["runs"][0])
        for record in solvers.values()
    )
    if complete:

        def objectives(row):
            return row["purchase"]["purchase_cost_sgd"], row["purchase"]["surplus_quantity"]

        same = all(
            objectives(left) == objectives(right)
            for left, right in zip(solvers["enumeration"]["runs"][0], solvers["cp_sat"]["runs"][0], strict=True)
        )
        result["comparison"] = "equal_cost_and_surplus" if same else "objective_mismatch"
    else:
        result["comparison"] = "unresolved"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    try:
        solver_version = version("ortools")
    except PackageNotFoundError:
        solver_version = None
    report = {
        "fixture_version": "synthetic-package-scale-v1",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "ortools_version": solver_version,
        "timing_scope": "all ingredients plus independent validation; no warm-up; first import included",
        "claim_scope": "fixed normalized demands only; no recipe search or runtime latency claim",
        "cases": [benchmark_case(*case, repeats=args.repeats) for case in synthetic_cases()],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
