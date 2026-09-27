"""Fixed-menu developer comparison; no runtime planner or API changes."""

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from fractions import Fraction
from hashlib import sha256
from time import perf_counter

from app.planning.input_audit import nonfinite_issues
from app.planning.meal_composition import dish_servings
from app.planning.mixed_shopping import (
    MixedShoppingLine,
    MixedShoppingResult,
    build_mixed_shopping,
    derive_mixed_demands,
    validate_mixed_shopping,
)
from app.planning.package_optimizer import PackageAllocation, PackageResult, optimize_packages
from app.planning.package_validator import validate_packages
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def _exact(value: Fraction) -> float:
    result = float(value)
    if Fraction(str(result)) != value:
        raise ValueError("quantity_not_representable")
    return result


def compare_purchasing(
    problem: FinalPlanningProblem,
    assignments: list[PlanningAssignment],
    *,
    max_combinations: int = 100000,
) -> dict:
    """Compare aggregate purchasing with separate checkouts without surplus carry.

    Pantry is consumed once in packet slot order. Both baskets are independently
    checked against the original complete assignment, including its hard budget.
    Enumeration limits apply per ingredient per checkout, not to the entire run.
    """
    started = perf_counter()
    payload = {"problem": problem.model_dump(mode="json"), "assignments": [a.model_dump() for a in assignments]}
    if nonfinite_issues(payload):
        return {"status": "unresolved", "issues": ["nonfinite_input"]}
    report = {
        "contract_version": "fixed-menu-purchasing-comparison-v1",
        "input_sha256": sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "baseline": "per-slot checkout; original pantry once; purchased surplus not carried",
        "solver": "exact bounded enumeration",
        "max_combinations_per_ingredient_checkout": max_combinations,
        "status": "unresolved",
    }
    demands, issues = derive_mixed_demands(problem, assignments)
    if issues:
        return dict(report, issues=list(issues))
    if problem.purchase_budget_sgd is not None and (Fraction(str(problem.purchase_budget_sgd)) * 100).denominator != 1:
        return dict(report, issues=["budget_not_whole_cents"])
    whole = build_mixed_shopping(problem, assignments, max_combinations=max_combinations)
    if whole.status not in {"feasible", "candidate_rejected"} or set(whole.issues) - {"purchase_budget"}:
        return dict(report, issues=list(whole.issues), whole_horizon=asdict(whole))
    recipes = {r.recipe_id: r for r in problem.recipes}
    servings = dish_servings(problem, assignments)
    by_slot = defaultdict(lambda: defaultdict(Fraction))
    for index, assignment in enumerate(assignments):
        recipe = recipes[assignment.recipe_id]
        for item in recipe.ingredients:
            by_slot[assignment.slot_id][item.ingredient_id, item.unit] += (
                Fraction(str(item.quantity)) * servings[index] / recipe.servings
            )
    pantry_left = {(d.ingredient_id, d.unit): Fraction(str(d.pantry_deduction)) for d in demands}
    counts = defaultdict(Counter)
    calls = 0
    try:
        for slot in problem.slots:
            for key, required in sorted(by_slot[slot.slot_id].items()):
                deduction = min(required, pantry_left[key])
                pantry_left[key] -= deduction
                remaining = _exact(required - deduction)
                purchase = optimize_packages(
                    key[0], remaining, key[1], problem.products, max_combinations=max_combinations
                )
                calls += 1
                if purchase.status != "optimal":
                    return dict(report, issues=[f"baseline_{purchase.status}"], baseline_solver_calls=calls)
                errors = validate_packages(key[0], remaining, key[1], purchase, problem.products)
                if errors:
                    return dict(report, issues=list(errors))
                for allocation in purchase.allocations:
                    counts[key][allocation.product_id] += allocation.packages
        lines = []
        total = Fraction(0)
        for demand in demands:
            allocations = tuple(
                PackageAllocation(p, n) for p, n in sorted(counts[demand.ingredient_id, demand.unit].items())
            )
            cost, supplied = Fraction(0), Fraction(0)
            for allocation in allocations:
                product = next(p for p in problem.products if p.product_id == allocation.product_id)
                cost += Fraction(str(product.price_sgd)) * allocation.packages
                supplied += Fraction(str(product.package_quantity)) * allocation.packages
            total += cost
            purchase = PackageResult(
                "optimal",
                allocations,
                _exact(cost),
                _exact(supplied),
                _exact(supplied - Fraction(str(demand.remaining_quantity))),
            )
            lines.append(
                MixedShoppingLine(
                    demand.ingredient_id,
                    demand.unit,
                    demand.required_quantity,
                    demand.pantry_deduction,
                    demand.remaining_quantity,
                    purchase,
                )
            )
        separate = MixedShoppingResult("feasible", tuple(lines), _exact(total))
    except (ValueError, OverflowError):
        return dict(report, issues=["quantity_not_representable"])
    baskets = {}
    for name, basket in (("whole_horizon", whole), ("per_slot", separate)):
        errors = validate_mixed_shopping(problem, assignments, basket)
        if set(errors) - {"purchase_budget"}:
            return dict(report, issues=list(errors))
        baskets[name] = dict(asdict(basket), status="over_budget" if errors else "feasible", issues=list(errors))
    saving = total - Fraction(str(whole.purchase_total_sgd))
    return dict(
        report,
        status="compared",
        **baskets,
        saving_sgd=_exact(saving),
        baseline_solver_calls=calls,
        whole_horizon_solver_calls=len(demands),
        elapsed_seconds=perf_counter() - started,
    )


def main():
    """Read a synthetic/developer packet containing problem and assignments."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--max-combinations", type=int, default=100000)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    result = compare_purchasing(
        FinalPlanningProblem.model_validate(data["problem"]),
        [PlanningAssignment.model_validate(a) for a in data["assignments"]],
        max_combinations=args.max_combinations,
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
