"""Bounded counterfactual explanations for independently established infeasibility.

Safety remains fixed in every counterfactual. Suggestions are evidence, never
mutations or automatic consent. Proofs concern this frozen candidate packet only.
"""

from dataclasses import asdict
from itertools import combinations

from app.planning.exhaustive_oracle import exhaustive_assignments
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.product_path import per_meal_budget_checks
from app.planning.relaxation_search import RelaxationChange, propose_relaxations
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment


def _without(problem, fields):
    candidate = problem.model_copy(deep=True)
    if "time_limit" in fields:
        for slot in candidate.slots:
            slot.max_time_minutes = None
    if "purchase_budget" in fields:
        candidate.purchase_budget_sgd = None
    if "dietary_requirements" in fields:
        candidate.dietary_requirements = []
    return candidate


def _validate(problem, choices, per_meal_budget):
    assignments = [PlanningAssignment(slot_id=slot, recipe_id=recipe) for slot, recipe in choices]
    shopping = FinalScopeReferencePlanner()._build_shopping(problem.model_copy(deep=True), assignments)
    report = FinalPlanningValidator().validate(problem, assignments, shopping)
    if per_meal_budget is not None and any(
        check.status != "passed" for check in per_meal_budget_checks(problem, assignments, per_meal_budget)
    ):
        return None
    return report if report.status == "passed" else None


def explain_infeasibility(problem, *, evidence, per_meal_budget=None, max_combinations=256):
    """Find a cardinality-minimal conflict among time, budget and dietary groups.

    Allergens, ingredient exclusions, locks and nutrition bands are immutable
    background constraints. Dietary groups may be diagnosed, never relaxed in
    a suggestion. Unknown counterfactuals cannot establish minimality.
    """
    if isinstance(max_combinations, bool) or not isinstance(max_combinations, int) or max_combinations < 1:
        raise ValueError("max_combinations must be a positive integer")
    result = {
        "version": "planning-conflict-v1",
        "status": "not_applicable",
        "conflict": [],
        "minimality": None,
        "suggestions": [],
        "checked_counterfactuals": 0,
        "max_combinations": max_combinations,
        "max_options_per_proposal": 8,
        "max_suggestions": 3,
        "proof_scope": "frozen_candidate_packet",
        "preserved": ["allergens", "excluded_ingredients", "nutrition_bands", "locks", "per_meal_budget"],
    }
    if evidence not in {"exactly_infeasible", "exhaustively_infeasible"}:
        return result

    cache = {}

    def solve(candidate):
        key = candidate.model_dump_json()
        if key not in cache:
            oracle = exhaustive_assignments(candidate, max_combinations=max_combinations)
            result["checked_counterfactuals"] += 1
            if oracle.best_loss is not None:
                report = _validate(candidate, oracle.best_choices, per_meal_budget)
                cache[key] = ("feasible", oracle.best_choices, report) if report else ("unknown", (), None)
            elif oracle.status == "no_valid_assignment":
                cache[key] = ("infeasible", (), None)
            else:
                cache[key] = ("unknown", (), None)
        return cache[key]

    # Independently verify the caller's evidence before interpreting constraints.
    original, _, _ = solve(problem)
    if original != "infeasible":
        result["status"] = "incomplete_evidence" if original == "unknown" else "candidate_is_feasible"
        return result
    groups = []
    if any(slot.max_time_minutes is not None for slot in problem.slots):
        groups.append("time_limit")
    if problem.purchase_budget_sgd is not None:
        groups.append("purchase_budget")
    if problem.dietary_requirements:
        groups.append("dietary_requirements")
    unknown = False
    found = False
    for size in range(len(groups) + 1):
        for subset in combinations(groups, size):
            status, _, _ = solve(_without(problem, set(groups) - set(subset)))
            if status == "unknown":
                unknown = True
            if status == "infeasible":
                result["conflict"] = list(subset)
                result["minimality"] = "unproven" if unknown else "minimum_cardinality_among_declared_groups"
                found = True
                break
        if found:
            break
    if found and not result["conflict"]:
        result["status"] = "fixed_constraints_blocked"
        return result
    result["status"] = "conflict_found" if found else "incomplete_evidence"

    # Derive a small declared option set from independently validated witnesses.
    # Time and money use separate proposals; no invented exchange rate combines them.
    for released in ({"time_limit"}, {"purchase_budget"}, {"time_limit", "purchase_budget"}):
        candidate = _without(problem, released)
        if "time_limit" in released:
            # Try the first eight observed recipe-time breakpoints. An option
            # validated here need not rely on the best-score oracle's longer menu.
            # Capping this list limits work; it never proves a global minimum.
            thresholds = sorted({r.total_time_minutes for r in problem.recipes})[:8]
            for threshold in thresholds:
                timed = candidate.model_copy(deep=True)
                for source, slot in zip(problem.slots, timed.slots, strict=True):
                    slot.max_time_minutes = max(source.max_time_minutes, threshold) if source.max_time_minutes else None
                if solve(timed)[0] == "feasible":
                    candidate = timed
                    break
        status, choices, report = solve(candidate)
        if status != "feasible":
            continue
        recipes = {r.recipe_id: r for r in problem.recipes}
        slots = {s.slot_id: s for s in problem.slots}
        options = []
        if "time_limit" in released:
            for slot_id, recipe_id in choices:
                current = slots[slot_id].max_time_minutes
                duration = recipes[recipe_id].total_time_minutes
                if current is not None and duration > current:
                    options.append(RelaxationChange(f"time:{slot_id}:{duration}", "time_limit", duration, 1, slot_id))
        if (
            "purchase_budget" in released
            and problem.purchase_budget_sgd is not None
            and report.purchase_total_sgd > problem.purchase_budget_sgd
        ):
            options.append(RelaxationChange("budget", "purchase_budget", report.purchase_total_sgd, 1))
        if not options:
            continue
        proposal = propose_relaxations(problem, tuple(options), max_combinations=max_combinations)
        if not proposal.witness or not proposal.changes:
            continue
        changed = problem.model_dump()
        for change in proposal.changes:
            if change.field == "purchase_budget":
                changed["purchase_budget_sgd"] = change.value
            else:
                for slot in changed["slots"]:
                    if slot["slot_id"] == change.slot_id:
                        slot["max_time_minutes"] = int(change.value)
        verified = _validate(FinalPlanningProblem.model_validate(changed), proposal.witness, per_meal_budget)
        if verified is None:
            continue
        suggestion = {
            "changes": [asdict(c) for c in proposal.changes],
            "minimality": proposal.status,
            "declared_options": [asdict(c) for c in options],
            "evaluated_sets": proposal.evaluated_sets,
            "witness": list(proposal.witness),
            "purchase_total_sgd": verified.purchase_total_sgd,
            "requires_confirmation": True,
        }
        if not any(s["changes"] == suggestion["changes"] for s in result["suggestions"]):
            result["suggestions"].append(suggestion)
    return result


def product_explanation(explanation):
    """Render only actions expressible by the current weekly request schema."""
    suggestions = []
    for suggestion in explanation["suggestions"]:
        changes = suggestion["changes"]
        times = [int(c["value"]) for c in changes if c["field"] == "time_limit"]
        budgets = [c["value"] for c in changes if c["field"] == "purchase_budget"]
        if times and max(times) > 240 or budgets and max(budgets) > 7000:
            continue
        parts = []
        if times:
            parts.append(f"a {max(times)}-minute cooking limit")
        if budgets:
            parts.append(f"a S${max(budgets):.2f} weekly budget")
        suggestions.append(" and ".join(parts))
    labels = {
        "time_limit": "cooking time",
        "purchase_budget": "weekly budget",
        "dietary_requirements": "dietary requirements",
    }
    conflict = ", ".join(labels[c] for c in explanation["conflict"]) or "the current constraints"
    if not suggestions:
        if explanation["status"] == "fixed_constraints_blocked":
            return "These recipes cannot meet the required restrictions; add compatible recipes before trying again."
        if explanation["conflict"]:
            return (
                f"No plan in these candidates meets {conflict}; no verified adjustment is available, "
                "so try a different recipe selection."
            )
        return None
    return (
        f"No plan in these candidates meets {conflict}; a verified option uses "
        + "; or ".join(suggestions[:3])
        + ", which you can choose and submit as a new request."
    )
