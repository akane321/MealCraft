"""Reprice a confirmed fixed menu against a complete new offline product snapshot."""

from dataclasses import asdict
from fractions import Fraction

from app.planning.input_audit import nonfinite_issues
from app.planning.mixed_shopping import MixedShoppingResult, build_mixed_shopping, validate_mixed_shopping
from app.planning.snapshot_repair import ProductSnapshot, validate_product_snapshot
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def refresh_fixed_menu(
    problem: FinalPlanningProblem,
    assignments: list[PlanningAssignment],
    before: MixedShoppingResult,
    snapshot: ProductSnapshot,
    *,
    max_combinations: int = 100000,
) -> dict:
    """Keep every assignment and user constraint; replace products, never merge them.

    An over-budget basket may be shown as a rejected preview with an exact delta.
    Missing data or an unfinished solve returns no proposed basket or cost delta.
    This does not retrieve, persist or automatically substitute any recipe.
    """
    result = {
        "contract_version": "offline-fixed-menu-refresh-v1",
        "status": "needs_data",
        "previous_snapshot_version": problem.product_snapshot_version,
        "new_snapshot_version": snapshot.version,
        "recipe_changes": [],
    }
    numeric = {
        "problem": problem.model_dump(),
        "before": asdict(before),
        "products": [p.model_dump() for p in snapshot.products],
    }
    if nonfinite_issues(numeric):
        return dict(result, issues=["nonfinite_input"])
    if problem.purchase_budget_sgd is not None and (Fraction(str(problem.purchase_budget_sgd)) * 100).denominator != 1:
        return dict(result, issues=["budget_not_whole_cents"])
    if before.status != "feasible":
        return dict(result, issues=["previous_basket_not_feasible"])
    errors = validate_mixed_shopping(problem, assignments, before)
    if errors:
        return dict(result, issues=[f"previous:{error}" for error in errors])
    if not snapshot.version.strip() or snapshot.version == problem.product_snapshot_version:
        return dict(result, issues=["snapshot_not_new"])
    if snapshot.trace.status != "success":
        return dict(result, issues=["provider_degraded"])
    try:
        validate_product_snapshot(snapshot)
    except ValueError:
        return dict(result, issues=["invalid_snapshot_evidence"])
    current = problem.model_copy(
        deep=True,
        update={
            "products": [p.model_copy(deep=True) for p in snapshot.products],
            "product_snapshot_version": snapshot.version,
        },
    )
    selected = [a.model_copy(deep=True) for a in assignments]
    after = build_mixed_shopping(current, selected, max_combinations=max_combinations)
    if after.status not in {"feasible", "candidate_rejected"}:
        return dict(result, status=after.status, issues=list(after.issues))
    errors = validate_mixed_shopping(current, selected, after)
    if set(errors) - {"purchase_budget"}:
        return dict(result, issues=list(errors))
    old_lines = {(line.ingredient_id, line.unit): line for line in before.lines}
    deltas = []
    for line in after.lines:
        old = old_lines[line.ingredient_id, line.unit]
        delta = (Fraction(str(line.purchase.purchase_cost_sgd)) - Fraction(str(old.purchase.purchase_cost_sgd))) * 100
        if delta.denominator != 1:
            return dict(result, issues=["cost_not_whole_cents"])
        old_purchase, new_purchase = asdict(old.purchase), asdict(line.purchase)
        # Solver enumeration counts are diagnostics, not changes to a purchase.
        old_purchase.pop("combinations")
        new_purchase.pop("combinations")
        if old_purchase != new_purchase:
            deltas.append(
                {
                    "ingredient_id": line.ingredient_id,
                    "unit": line.unit,
                    "before": old_purchase,
                    "after": new_purchase,
                    "purchase_cost_delta_cents": int(delta),
                }
            )
    return dict(
        result,
        status="candidate_rejected" if errors else "feasible",
        issues=list(errors),
        assignments=[a.model_dump() for a in selected],
        shopping=asdict(after),
        shopping_delta=deltas,
        purchase_total_delta_cents=sum(d["purchase_cost_delta_cents"] for d in deltas),
        retrieval=snapshot.trace.model_dump(mode="json"),
    )
