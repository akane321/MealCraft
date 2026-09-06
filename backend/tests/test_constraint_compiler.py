from pathlib import Path

import pytest

from app.planning.constraint_compiler import compile_constraints
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningNutritionBand

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"


def problem():
    return FinalPlanningProblem.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def pair(packet, slot_id, recipe_id):
    return next(row for row in compile_constraints(packet) if (row.slot_id, row.recipe_id) == (slot_id, recipe_id))


def test_complete_matrix_is_deterministic_and_does_not_mutate_input():
    packet = problem()
    before = packet.model_dump_json()
    first = compile_constraints(packet)
    shuffled = packet.model_copy(
        update={"slots": list(reversed(packet.slots)), "recipes": list(reversed(packet.recipes))}
    )
    assert first == compile_constraints(shuffled)
    assert len(first) == len(packet.slots) * len(packet.recipes)
    assert packet.model_dump_json() == before


@pytest.mark.parametrize(
    "rule", ["meal_type", "time_limit", "allergen", "excluded_ingredient", "dietary_requirement", "locked_slot"]
)
def test_each_hard_rejection_has_a_stable_reason(rule):
    packet = problem()
    slot = packet.slots[0].model_copy(update={"locked_recipe_id": None, "max_time_minutes": 10})
    recipe = packet.recipes[0].model_copy(update={"allowed_meal_types": [slot.meal_type], "total_time_minutes": 10})
    packet = packet.model_copy(update={"slots": [slot], "recipes": [recipe], "nutrition_bands": []})
    if rule == "meal_type":
        recipe.allowed_meal_types = ["snack"] if slot.meal_type != "snack" else ["dinner"]
    elif rule == "time_limit":
        recipe.total_time_minutes = 11
    elif rule == "allergen":
        recipe.allergens = ["test-allergen"]
        packet.allergens = ["test-allergen"]
    elif rule == "excluded_ingredient":
        packet.excluded_ingredients = [recipe.ingredients[0].ingredient_id]
    elif rule == "dietary_requirement":
        packet.dietary_requirements = ["unmatched-diet"]
    else:
        alternative = recipe.model_copy(update={"recipe_id": "other"})
        packet.recipes.append(alternative)
        slot.locked_recipe_id = "other"
    row = pair(packet, slot.slot_id, recipe.recipe_id)
    assert not row.eligible
    assert rule in row.rejection_codes


@pytest.mark.parametrize(
    "scope,hard,reject",
    [("per_slot", True, True), ("per_slot", False, False), ("per_day", True, False), ("horizon_average", True, False)],
)
def test_only_hard_per_slot_nutrition_filters_candidates(scope, hard, reject):
    packet = problem()
    slot = packet.slots[0].model_copy(update={"locked_recipe_id": None, "max_time_minutes": None, "servings": 24})
    recipe = packet.recipes[0].model_copy(update={"allowed_meal_types": [slot.meal_type]})
    band = PlanningNutritionBand(
        metric="protein_g", scope=scope, lower=recipe.nutrients_per_serving.protein_g + 1, hard=hard
    )
    packet = packet.model_copy(update={"slots": [slot], "recipes": [recipe], "nutrition_bands": [band]})
    assert pair(packet, slot.slot_id, recipe.recipe_id).eligible is not reject


def test_soft_health_and_equal_numeric_bound_do_not_reject():
    packet = problem()
    slot = packet.slots[0].model_copy(update={"locked_recipe_id": None, "max_time_minutes": None})
    recipe = packet.recipes[0].model_copy(update={"allowed_meal_types": [slot.meal_type]})
    band = PlanningNutritionBand(metric="sodium_mg", scope="per_slot", upper=recipe.nutrients_per_serving.sodium_mg)
    packet = packet.model_copy(
        update={"slots": [slot], "recipes": [recipe], "nutrition_bands": [band], "health_preferences": ["low-sodium"]}
    )
    assert pair(packet, slot.slot_id, recipe.recipe_id).eligible
    band.upper -= 1
    assert "nutrition_sodium_mg_upper" in pair(packet, slot.slot_id, recipe.recipe_id).rejection_codes


@pytest.mark.parametrize("delta,eligible", [(0.0, True), (0.0000005, True), (0.000002, False)])
def test_numeric_tolerance_matches_validator(delta, eligible):
    packet = problem()
    slot = packet.slots[0].model_copy(update={"locked_recipe_id": None, "max_time_minutes": None})
    recipe = packet.recipes[0].model_copy(update={"allowed_meal_types": [slot.meal_type]})
    band = PlanningNutritionBand(
        metric="protein_g", scope="per_slot", lower=recipe.nutrients_per_serving.protein_g + delta
    )
    packet = packet.model_copy(update={"slots": [slot], "recipes": [recipe], "nutrition_bands": [band]})
    assert pair(packet, slot.slot_id, recipe.recipe_id).eligible is eligible


def test_optional_locked_recipe_still_reports_all_safety_conflicts():
    packet = problem()
    recipe = packet.recipes[0].model_copy(update={"allergens": ["milk"], "total_time_minutes": 20})
    slot = packet.slots[0].model_copy(
        update={"required": False, "locked_recipe_id": recipe.recipe_id, "max_time_minutes": 10}
    )
    recipe.allowed_meal_types = [slot.meal_type]
    packet = packet.model_copy(
        update={"slots": [slot], "recipes": [recipe], "allergens": ["milk"], "nutrition_bands": []}
    )
    row = pair(packet, slot.slot_id, recipe.recipe_id)
    assert row.rejection_codes == ("allergen", "time_limit")
    assert not row.eligible


@pytest.mark.parametrize("required,locked,blocked", [(True, False, True), (False, False, False), (False, True, True)])
def test_empty_domains_only_block_required_or_locked_slots(required, locked, blocked):
    from app.planning.constraint_compiler import compile_search_domains

    packet = problem()
    recipe = packet.recipes[0].model_copy(update={"allergens": ["milk"]})
    slot = packet.slots[0].model_copy(
        update={"required": required, "locked_recipe_id": recipe.recipe_id if locked else None}
    )
    packet = packet.model_copy(update={"slots": [slot], "recipes": [recipe], "allergens": ["milk"]})
    compiled = compile_search_domains(packet)
    assert compiled.slots[0].eligible_recipe_ids == ()
    assert compiled.blocked_slot_ids == ((slot.slot_id,) if blocked else ())
    assert "allergen" in compiled.decisions[0].rejection_codes


def test_empty_reviewed_allergen_lists_and_new_catalog_values_use_same_logic():
    from app.planning.constraint_compiler import compile_search_domains

    packet = problem()
    slot = packet.slots[0].model_copy(update={"locked_recipe_id": None, "max_time_minutes": None})
    recipe = packet.recipes[0].model_copy(update={"allowed_meal_types": [slot.meal_type], "allergens": []})
    packet = packet.model_copy(
        update={"slots": [slot], "recipes": [recipe], "allergens": ["milk"], "nutrition_bands": []}
    )
    assert compile_search_domains(packet).slots[0].eligible_recipe_ids == (recipe.recipe_id,)
    packet = packet.model_copy(update={"recipes": [recipe.model_copy(update={"allergens": ["milk"]})]})
    assert compile_search_domains(packet).blocked_slot_ids == (slot.slot_id,)
    packet = packet.model_copy(update={"allergens": []})
    assert compile_search_domains(packet).slots[0].eligible_recipe_ids == (recipe.recipe_id,)


def test_nonempty_domains_do_not_claim_aggregate_budget_feasibility():
    from app.planning.constraint_compiler import compile_search_domains

    packet = problem().model_copy(update={"purchase_budget_sgd": 0.01})
    compiled = compile_search_domains(packet)
    assert compiled.blocked_slot_ids == ()
    assert not hasattr(compiled, "feasible")
    reversed_packet = packet.model_copy(
        update={"slots": list(reversed(packet.slots)), "recipes": list(reversed(packet.recipes))}
    )
    assert compiled == compile_search_domains(reversed_packet)
