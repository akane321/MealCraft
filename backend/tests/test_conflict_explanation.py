import pytest

from app.planning.conflict_explanation import explain_infeasibility, product_explanation
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment
from tests.test_relaxation_search import packet


def joint_packet():
    data = packet().model_dump()
    prototype = data["recipes"][0]
    data["recipes"] = []
    for name, minutes in (("fast", 10), ("cheap", 30)):
        data["recipes"].append(
            {
                **prototype,
                "recipe_id": name,
                "total_time_minutes": minutes,
                "servings": 1,
                "allergens": [],
                "dietary_tags": [],
                "ingredients": [{"ingredient_id": name, "quantity": 1, "unit": "g"}],
            }
        )
    data["slots"][0].update(locked_recipe_id=None, servings=1, max_time_minutes=20)
    data.update(
        pantry=[],
        purchase_budget_sgd=10,
        dietary_requirements=[],
        allergens=[],
        products=[
            {
                "product_id": name,
                "ingredient_id": name,
                "package_quantity": 1,
                "package_unit": "g",
                "price_sgd": cost,
                "available": True,
            }
            for name, cost in (("fast", 20), ("cheap", 1))
        ],
    )
    return FinalPlanningProblem.model_validate(data)


def apply(problem, suggestion):
    candidate = problem.model_copy(deep=True)
    for change in suggestion["changes"]:
        if change["field"] == "purchase_budget":
            candidate.purchase_budget_sgd = change["value"]
        else:
            for slot in candidate.slots:
                if slot.slot_id == change["slot_id"]:
                    slot.max_time_minutes = int(change["value"])
    return candidate


def test_joint_conflict_is_minimal_and_each_numeric_proposal_has_a_valid_witness():
    problem = joint_packet()
    before = problem.model_dump_json()
    result = explain_infeasibility(problem, evidence="exhaustively_infeasible")
    assert set(result["conflict"]) == {"time_limit", "purchase_budget"}
    assert result["minimality"] == "minimum_cardinality_among_declared_groups"
    assert len(result["suggestions"]) == 2
    message = product_explanation(result)
    assert "30-minute" in message and "S$20.00" in message
    for suggestion in result["suggestions"]:
        adjusted = apply(problem, suggestion)
        assignments = [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in suggestion["witness"]]
        shopping = FinalScopeReferencePlanner()._build_shopping(adjusted, assignments)
        assert FinalPlanningValidator().validate(adjusted, assignments, shopping).status == "passed"
        assert suggestion["requires_confirmation"]
        assert suggestion["minimality"] == "minimal_in_declared_options"
    assert problem.model_dump_json() == before


@pytest.mark.parametrize("safety", ["allergens", "nutrition", "excluded_ingredients"])
def test_safety_only_obstruction_never_becomes_a_proposal(safety):
    problem = joint_packet()
    if safety == "allergens":
        problem.allergens = ["soy"]
        problem.allergen_vocabulary = ["soy"]
        for recipe in problem.recipes:
            recipe.allergens = ["soy"]
    elif safety == "nutrition":
        from app.schemas.planning_v2 import PlanningNutritionBand

        problem.nutrition_bands = [PlanningNutritionBand(metric="sodium_mg", scope="per_slot", upper=0)]
    else:
        problem.excluded_ingredients = ["fast", "cheap"]
    before = problem.model_dump_json()
    result = explain_infeasibility(problem, evidence="exactly_infeasible")
    assert result["status"] == "fixed_constraints_blocked"
    assert result["suggestions"] == []
    assert result["conflict"] == []
    assert problem.model_dump_json() == before


@pytest.mark.parametrize("evidence", ["bounded_search_exhausted", "needs_data", "validated"])
def test_unproven_infeasibility_does_not_start_a_relaxation_search(evidence, monkeypatch):
    from app.planning import conflict_explanation

    def forbidden(*args, **kwargs):
        pytest.fail("No counterfactual search is allowed for this evidence")

    monkeypatch.setattr(conflict_explanation, "exhaustive_assignments", forbidden)
    result = explain_infeasibility(joint_packet(), evidence=evidence)
    assert result["suggestions"] == []
    assert result["checked_counterfactuals"] == 0


def test_limit_does_not_claim_a_conflict_or_minimum():
    result = explain_infeasibility(joint_packet(), evidence="exactly_infeasible", max_combinations=1)
    assert result["status"] == "incomplete_evidence"
    assert result["conflict"] == []
    assert result["suggestions"] == []
    assert result["minimality"] is None


def test_false_caller_proof_is_rechecked():
    problem = joint_packet()
    problem.purchase_budget_sgd = 50
    result = explain_infeasibility(problem, evidence="exactly_infeasible")
    assert result["status"] == "candidate_is_feasible"
    assert result["suggestions"] == []


def test_missing_data_and_per_meal_ceiling_are_not_relaxed():
    problem = joint_packet()
    result = explain_infeasibility(problem, evidence="exhaustively_infeasible", per_meal_budget=0.01)
    assert result["suggestions"] == []
    problem.products = []
    result = explain_infeasibility(problem, evidence="exhaustively_infeasible")
    assert result["suggestions"] == []


def test_explanation_is_deterministic():
    assert explain_infeasibility(joint_packet(), evidence="exactly_infeasible") == explain_infeasibility(
        joint_packet(), evidence="exactly_infeasible"
    )
