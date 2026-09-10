"""Read-only diagnostics for normalized Planning V2 packets; not a feasibility test."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction
from math import isfinite
from pathlib import Path
from typing import Literal

from app.schemas.planning_v2 import FinalPlanningProblem


@dataclass(frozen=True, order=True)
class InputIssue:
    path: str
    code: str
    severity: Literal["invalid", "missing", "policy"]
    detail: str


def nonfinite_issues(value) -> tuple[InputIssue, ...]:
    """Locate nonfinite floats without embedding invalid values in the report."""
    issues = []

    def walk(item, path):
        if isinstance(item, float) and not isfinite(item):
            issues.append(InputIssue(path, "nonfinite_number", "invalid", "Numeric input must be finite."))
        elif isinstance(item, dict):
            for key, child in item.items():
                walk(child, f"{path}.{key}" if path else key)
        elif isinstance(item, (list, tuple)):
            for i, child in enumerate(item):
                walk(child, f"{path}[{i}]")

    walk(value, "")
    return tuple(sorted(issues))


class NonfinitePlanningInput(ValueError):
    """Invalid numeric packet, distinct from search failure or missing facts."""

    def __init__(self, issues: tuple[InputIssue, ...]):
        self.issues = issues
        super().__init__("Nonfinite planning input at: " + ", ".join(issue.path for issue in issues))


def require_finite_problem(problem: FinalPlanningProblem) -> None:
    issues = nonfinite_issues(problem.model_dump())
    if issues:
        raise NonfinitePlanningInput(issues)


def audit_problem(problem: FinalPlanningProblem) -> tuple[InputIssue, ...]:
    """Report input facts without changing data, filtering recipes or inferring safety.

    Missing data on an unused candidate need not prevent another feasible plan.
    An empty report only means none of these diagnostics fired.
    """
    issues = list(nonfinite_issues(problem.model_dump()))

    def add(path, code, severity, detail):
        issues.append(InputIssue(path, code, severity, detail))

    for field in ("catalog_version", "product_snapshot_version", "policy_version"):
        if not getattr(problem, field).strip():
            add(field, "missing_version", "missing", "A nonempty version is needed for replay.")
    for name, rows, key in (("products", problem.products, "product_id"), ("pantry", problem.pantry, "ingredient_id")):
        duplicates = {value for value, count in Counter(getattr(r, key) for r in rows).items() if count > 1}
        for i, row in enumerate(rows):
            if getattr(row, key) in duplicates:
                add(
                    f"{name}[{i}].{key}",
                    "ambiguous_identity",
                    "policy",
                    "Repeated IDs need an explicit resolution policy.",
                )
    for i, recipe in enumerate(problem.recipes):
        for j, item in enumerate(recipe.ingredients):
            prefix = f"recipes[{i}].ingredients[{j}]"
            if item.quantity is None:
                add(
                    prefix + ".quantity",
                    "unknown_recipe_quantity",
                    "missing",
                    "Demand is unknown if this recipe is selected.",
                )
            if item.unit is None:
                add(
                    prefix + ".unit",
                    "unknown_recipe_unit",
                    "missing",
                    "A canonical unit is needed to match product coverage.",
                )
    for i, item in enumerate(problem.pantry):
        if item.quantity is None:
            add(
                f"pantry[{i}].quantity",
                "unknown_pantry_quantity",
                "policy",
                "May influence preference but cannot be deducted.",
            )
    for i, product in enumerate(problem.products):
        if isfinite(product.price_sgd) and (Fraction(str(product.price_sgd)) * 100).denominator != 1:
            add(
                f"products[{i}].price_sgd",
                "fractional_cent_price",
                "policy",
                "Mixed shopping requires whole-cent prices.",
            )
    return tuple(sorted(issues))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    problem = FinalPlanningProblem.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
    print(
        json.dumps(
            {
                "diagnostic_version": "planning-input-audit-v1",
                "issues": [asdict(issue) for issue in audit_problem(problem)],
                "scope": "Diagnostics only; no completeness, allergen-safety or feasibility certification.",
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
