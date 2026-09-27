"""Planning-owned mixed basket handoff prototype; not a public API or DB row."""

import json
from dataclasses import asdict
from fractions import Fraction
from hashlib import sha256

from app.planning.input_audit import nonfinite_issues
from app.planning.mixed_shopping import MixedShoppingResult, validate_mixed_shopping
from app.planning.product_input import product_input
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment
from app.schemas.product import PriceEvidence, ProductResponse


def prepare_mixed_purchase(
    problem: FinalPlanningProblem,
    assignments: list[PlanningAssignment],
    shopping: MixedShoppingResult,
    observations: dict[str, ProductResponse],
    evidence: dict[str, PriceEvidence],
) -> dict:
    """Recheck a complete basket and bind each allocation to its frozen observation.

    Mapping keys are planner product IDs, including the existing @ingredient
    alias when one external product is bought separately for two ingredients.
    Observations must already use the planner's normalized units. No retrieval,
    persistence, implicit unit conversion or single-product flattening occurs.
    """
    rejected = {"status": "not_ready", "contract_version": "mixed-purchase-handoff-prototype-v1"}
    if nonfinite_issues({"problem": problem.model_dump(), "shopping": asdict(shopping)}):
        return dict(rejected, issues=["nonfinite_input"])
    if problem.purchase_budget_sgd is not None and (Fraction(str(problem.purchase_budget_sgd)) * 100).denominator != 1:
        return dict(rejected, issues=["budget_not_whole_cents"])
    if shopping.status != "feasible":
        return dict(rejected, issues=["basket_not_feasible"])
    errors = validate_mixed_shopping(problem, assignments, shopping)
    if errors:
        return dict(rejected, issues=list(errors))
    options = {p.product_id: p for p in problem.products}
    items, facts = [], {}
    for line in shopping.lines:
        allocations = []
        for allocation in line.purchase.allocations:
            product_id = allocation.product_id
            source, fact = observations.get(product_id), evidence.get(product_id)
            if source is None or fact is None:
                return dict(rejected, issues=["allocation_observation_or_evidence_missing"])
            projected = product_input(source, ingredient_id=line.ingredient_id, required_unit=line.unit)
            option = options[product_id]
            allowed_ids = {source.external_id, f"{source.external_id}@{line.ingredient_id}"}
            if (
                projected.option is None
                or product_id not in allowed_ids
                or projected.option.model_copy(update={"product_id": product_id}) != option
            ):
                return dict(rejected, issues=["allocation_observation_mismatch"])
            source_mode = (
                fact.source == "release_snapshot"
                and fact.mode == "snapshot"
                or fact.source == source.source == "fixture"
                and fact.mode == "fixture"
                or fact.source == source.source == "fairprice"
                and fact.mode in {"live", "cache"}
            )
            if (
                fact.fetched_at.utcoffset() is None
                or fact.fetched_at != source.fetched_at
                or fact.fact_id != f"{source.external_id}@{source.fetched_at.isoformat()}"
                or not source_mode
            ):
                return dict(rejected, issues=["allocation_evidence_mismatch"])
            product_json = projected.observation.model_dump(mode="json")
            if fact.fact_id in facts and facts[fact.fact_id] != product_json:
                return dict(rejected, issues=["conflicting_price_fact"])
            facts[fact.fact_id] = product_json
            allocations.append(
                {
                    "planning_product_id": product_id,
                    "packages": allocation.packages,
                    "purchase_cost_cents": int(Fraction(str(option.price_sgd)) * 100) * allocation.packages,
                    "product": product_json,
                    "evidence": fact.model_dump(mode="json"),
                }
            )
        items.append(
            {
                "ingredient_id": line.ingredient_id,
                "unit": line.unit,
                "required_quantity": line.required_quantity,
                "pantry_deduction": line.pantry_deduction,
                "remaining_quantity": line.remaining_quantity,
                "supplied_quantity": line.purchase.supplied_quantity,
                "surplus_quantity": line.purchase.surplus_quantity,
                "purchase_cost_cents": sum(a["purchase_cost_cents"] for a in allocations),
                "allocations": allocations,
            }
        )
    payload = {
        "status": "ready_for_contract_review",
        "contract_version": rejected["contract_version"],
        "catalog_version": problem.catalog_version,
        "product_snapshot_version": problem.product_snapshot_version,
        "policy_version": problem.policy_version,
        "planning_input_sha256": sha256(
            json.dumps(
                {"problem": problem.model_dump(mode="json"), "assignments": [a.model_dump() for a in assignments]},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        "purchase_total_cents": sum(item["purchase_cost_cents"] for item in items),
        "items": items,
    }
    payload["content_sha256"] = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return payload
