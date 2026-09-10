from pathlib import Path

import pytest

from app.planning.relaxation_search import RelaxationChange, propose_relaxations
from app.schemas.planning_v2 import FinalPlanningProblem


def packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"
    data = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8")).model_dump()
    recipe = data["recipes"][0]
    recipe["total_time_minutes"] = 30
    slot = data["slots"][0]
    slot.update(max_time_minutes=10, locked_recipe_id=recipe["recipe_id"])
    data.update(recipes=[recipe], slots=[slot], nutrition_bands=[], purchase_budget_sgd=1000)
    return FinalPlanningProblem.model_validate(data)


def test_cheapest_declared_relaxation_has_a_valid_witness_without_mutating_request():
    problem = packet()
    before = problem.model_dump_json()
    slot = problem.slots[0].slot_id
    choices = (
        RelaxationChange("time-40", "time_limit", 40, 2, slot),
        RelaxationChange("time-30", "time_limit", 30, 1, slot),
    )
    result = propose_relaxations(problem, choices)
    assert result.status == "minimal_in_declared_options"
    assert result.changes[0].change_id == "time-30"
    assert result.total_cost == 1
    assert result.witness == ((slot, problem.recipes[0].recipe_id),)
    assert problem.model_dump_json() == before


def test_allergen_conflict_is_never_relaxed():
    problem = packet()
    problem = problem.model_copy(update={"allergens": problem.recipes[0].allergens})
    result = propose_relaxations(problem, (RelaxationChange("time", "time_limit", 30, 1, problem.slots[0].slot_id),))
    assert result.status == "no_solution_in_declared_options"
    assert result.witness == ()


def test_unsupported_safety_change_is_rejected():
    with pytest.raises(ValueError):
        propose_relaxations(packet(), (RelaxationChange("bad", "allergens", 1, 0),))


def test_missing_product_data_cannot_prove_minimality():
    problem = packet().model_copy(update={"products": []})
    result = propose_relaxations(problem, (RelaxationChange("time", "time_limit", 30, 1, problem.slots[0].slot_id),))
    assert result.status == "incomplete_evidence"


def mixed_packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/mixed-package-developer.json"
    return FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))


def test_mixed_purchase_avoids_unnecessary_budget_relaxation():
    problem = mixed_packet()
    options = (RelaxationChange("budget", "purchase_budget", 4, 1),)
    assert propose_relaxations(problem, options).changes == options
    result = propose_relaxations(problem, options, mixed_packages=True)
    assert result.status == "minimal_in_declared_options"
    assert result.changes == ()
    assert result.total_cost == 0
    assert result.shopping_policy == "offline-mixed-shopping-v1"


def test_mixed_policy_finds_only_required_budget_increase_without_applying_it():
    problem = mixed_packet().model_copy(update={"purchase_budget_sgd": 3})
    before = problem.model_dump_json()
    options = (RelaxationChange("small", "purchase_budget", 3.5, 1), RelaxationChange("large", "purchase_budget", 4, 2))
    result = propose_relaxations(problem, options, mixed_packages=True)
    assert result.changes == (options[0],)
    assert result.status == "minimal_in_declared_options"
    assert problem.model_dump_json() == before


def test_package_limit_does_not_prove_relaxation_minimality():
    result = propose_relaxations(mixed_packet(), (), mixed_packages=True, max_package_combinations=1)
    assert result.status == "incomplete_evidence"
    assert result.witness == ()


def test_missing_mixed_products_remains_data_problem():
    problem = mixed_packet().model_copy(update={"products": []})
    result = propose_relaxations(problem, (RelaxationChange("budget", "purchase_budget", 10, 1),), mixed_packages=True)
    assert result.status == "incomplete_evidence"


def test_mixed_relaxation_does_not_remove_allergen_conflicts():
    problem = mixed_packet()
    problem = problem.model_copy(update={"allergens": problem.recipes[0].allergens})
    result = propose_relaxations(problem, (RelaxationChange("budget", "purchase_budget", 10, 1),), mixed_packages=True)
    assert result.status == "no_solution_in_declared_options"
