"""Compare single-product and mixed-package costs on developer-household demand.

The five public ``full_default`` developer households supply the menus and
shopping quantities.  Both purchasing policies then receive the same demand
and the same in-stock options from the frozen observed FairPrice snapshot.
This is a package-policy diagnostic, not a whole-plan or catalog optimum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.routes.meal_plans import build_meal_plan_service  # noqa: E402
from app.data.release_v2 import release_dir  # noqa: E402
from app.evaluation import full_default  # noqa: E402
from app.evaluation.meal_day_week_runner import HOUSEHOLD as HOUSEHOLD_ID  # noqa: E402
from app.evaluation.meal_day_week_runner import product_database  # noqa: E402
from app.planning.final_scope_reference import FinalScopeReferencePlanner  # noqa: E402
from app.planning.grocery_estimator import convert_quantity  # noqa: E402
from app.planning.package_optimizer import optimize_packages  # noqa: E402
from app.schemas.planning_v2 import PlanningProductOption, PlanningShoppingSelection  # noqa: E402

SNAPSHOT = ROOT / "data/products/fairprice-v2-snapshot.json"


def _options(ingredient: str, snapshot: dict) -> list[PlanningProductOption]:
    entry = snapshot["ingredients"].get(ingredient)
    if entry is None or entry.get("status") != "mapped":
        return []
    return [
        PlanningProductOption(
            ingredient_id=ingredient,
            product_id=item["external_id"],
            package_quantity=item["package_grams"],
            package_unit="g",
            price_sgd=round(item["price_sgd"], 2),
            available=item["in_stock"],
        )
        for item in entry["products"]
    ]


def _single_product(required: float, options: list[PlanningProductOption]) -> dict:
    ranked = []
    for option in options:
        if not option.available:
            continue
        packages = math.ceil(required / option.package_quantity)
        supplied = packages * option.package_quantity
        ranked.append(
            (
                round(packages * option.price_sgd, 2),
                supplied - required,
                option.product_id,
                packages,
                supplied,
            )
        )
    if not ranked:
        return {"status": "needs_data"}
    cost, surplus, product_id, packages, supplied = min(ranked)
    return {
        "status": "optimal",
        "cost_sgd": cost,
        "supplied_g": round(supplied, 3),
        "surplus_g": round(surplus, 3),
        "allocations": [{"product_id": product_id, "packages": packages}],
    }


def legacy_product_selection(
    *,
    ingredient_id: str,
    required: float | None,
    unit: str | None,
    deduction: float,
    remaining: float | None,
    products: list[PlanningProductOption],
) -> PlanningShoppingSelection:
    """The pre-mixed product rule, used only to freeze matched plan demand."""
    if remaining == 0:
        return PlanningShoppingSelection(
            ingredient_id=ingredient_id,
            required_quantity=required,
            unit=unit,
            pantry_deduction=round(deduction, 3),
            remaining_quantity=0,
            selected_product_id=None,
            packages=0,
            purchase_cost_sgd=0,
            surplus_quantity=0,
            note="Known compatible pantry quantity covers demand.",
        )
    compatible = [item for item in products if item.package_unit == unit]
    if remaining is None or not compatible:
        return PlanningShoppingSelection(
            ingredient_id=ingredient_id,
            required_quantity=required,
            unit=unit,
            pantry_deduction=round(deduction, 3),
            remaining_quantity=remaining,
            selected_product_id=None,
            packages=0,
            purchase_cost_sgd=0,
            surplus_quantity=None,
            note="No compatible product or normalized quantity is available.",
        )
    ranked = []
    for product in compatible:
        packages = math.ceil(remaining / product.package_quantity)
        cost = round(packages * product.price_sgd, 2)
        surplus = packages * product.package_quantity - remaining
        ranked.append((cost, surplus, product.product_id, product, packages))
    cost, surplus, _, selected, packages = min(ranked)
    return PlanningShoppingSelection(
        ingredient_id=ingredient_id,
        required_quantity=round(required, 3) if required is not None else None,
        unit=unit,
        pantry_deduction=round(deduction, 3),
        remaining_quantity=round(remaining, 3),
        selected_product_id=selected.product_id,
        packages=packages,
        purchase_cost_sgd=cost,
        surplus_quantity=round(surplus, 3),
    )


def compare_line(line: dict, snapshot: dict) -> dict:
    ingredient = line["ingredient_name"]
    remaining = line.get("remaining_quantity")
    grams = convert_quantity(remaining, line.get("unit"), "g", ingredient) if remaining is not None else None
    options = _options(ingredient, snapshot)
    base = {
        "ingredient": ingredient,
        "trip": line.get("shopping_trip"),
        "remaining_quantity": remaining,
        "remaining_unit": line.get("unit"),
        "observed_option_count": len(options),
    }
    if grams is None:
        return {**base, "status": "unresolved", "reason": "demand_not_convertible_to_grams"}
    available = [option for option in options if option.available]
    if not available:
        return {**base, "status": "unresolved", "reason": "no_in_stock_observed_option"}
    single = _single_product(grams, available)
    mixed_result = optimize_packages(ingredient, grams, "g", available)
    if single["status"] != "optimal" or mixed_result.status != "optimal":
        return {
            **base,
            "status": "unresolved",
            "reason": f"single={single['status']}; mixed={mixed_result.status}",
        }
    mixed = {
        "status": mixed_result.status,
        "cost_sgd": round(mixed_result.purchase_cost_sgd, 2),
        "supplied_g": round(mixed_result.supplied_quantity, 3),
        "surplus_g": round(mixed_result.surplus_quantity, 3),
        "allocations": [
            {"product_id": item.product_id, "packages": item.packages} for item in mixed_result.allocations
        ],
    }
    return {
        **base,
        "status": "compared",
        "remaining_g": round(grams, 3),
        "single_product": single,
        "mixed_package": mixed,
        "saving_sgd": round(single["cost_sgd"] - mixed["cost_sgd"], 2),
    }


def summarize(case: str, lines: list[dict]) -> dict:
    compared = [line for line in lines if line["status"] == "compared"]
    single = round(sum(line["single_product"]["cost_sgd"] for line in compared), 2)
    mixed = round(sum(line["mixed_package"]["cost_sgd"] for line in compared), 2)
    return {
        "case": case,
        "shopping_lines": len(lines),
        "compared_lines": len(compared),
        "unresolved_lines": len(lines) - len(compared),
        "single_product_cost_sgd": single,
        "mixed_package_cost_sgd": mixed,
        "saving_sgd": round(single - mixed, 2),
        "strictly_cheaper_lines": sum(line["saving_sgd"] > 0 for line in compared),
    }


def build_artifact(snapshot: dict, raw: bytes) -> dict:
    catalog = {
        "scenario": {
            "recipe_candidate_slugs": [
                json.loads(line)["recipe_id"]
                for line in (release_dir() / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
            ]
        }
    }
    cases = []
    with product_database(catalog) as factory, factory() as session:
        plans = build_meal_plan_service(session, HOUSEHOLD_ID)
        for case in full_default.CASES:
            with patch.object(FinalScopeReferencePlanner, "_choose_product", staticmethod(legacy_product_selection)):
                week = plans.generate(full_default.request_for(case)).model_dump(mode="json")
            checked = full_default.check_week(
                week,
                full_default.request_for(case),
                full_default._recipes(session, {dish["recipe"]["slug"] for dish in week["days"]}),
            )
            lines = [compare_line(line, snapshot) for line in week["grocery_estimate"]["items"]]
            cases.append(
                {
                    **summarize(case["case"], lines),
                    "household_checks_pass": all(checked["checks"].values()),
                    "lines": lines,
                }
            )
    totals = {
        "shopping_lines": sum(case["shopping_lines"] for case in cases),
        "compared_lines": sum(case["compared_lines"] for case in cases),
        "unresolved_lines": sum(case["unresolved_lines"] for case in cases),
        "single_product_cost_sgd": round(sum(case["single_product_cost_sgd"] for case in cases), 2),
        "mixed_package_cost_sgd": round(sum(case["mixed_package_cost_sgd"] for case in cases), 2),
        "saving_sgd": round(sum(case["saving_sgd"] for case in cases), 2),
        "strictly_cheaper_lines": sum(case["strictly_cheaper_lines"] for case in cases),
    }
    return {
        "schema_version": "household-observed-package-policy-v1",
        "generator": "scripts/compare_household_observed_packaging.py",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_dirty": subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "."], cwd=ROOT) != 0,
        "snapshot_version": snapshot.get("snapshot_version"),
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "comparison": "same legacy-policy developer-household plan demand and same observed FairPrice options",
        "scope": (
            "five public full-default developer households; menus frozen under the former single-product rule; "
            "observed-snapshot mapped lines only; "
            "no held-out data, live lookup, whole-plan optimum, catalog minimum or five-percent claim"
        ),
        "totals": totals,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = SNAPSHOT.read_bytes()
    artifact = build_artifact(json.loads(raw), raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact["totals"], indent=2))


if __name__ == "__main__":
    main()
