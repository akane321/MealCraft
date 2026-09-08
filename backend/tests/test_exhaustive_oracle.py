from pathlib import Path

import pytest

from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.exhaustive_oracle import exhaustive_assignments
from app.schemas.planning_v2 import FinalPlanningProblem


def small_packet():
    path = Path(__file__).resolve().parents[2] / "data/fixtures/planning-v2/final-scope-multislot.json"
    data = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8")).model_dump()
    recipe = data["recipes"][0]
    data["recipes"] = [
        dict(
            recipe,
            recipe_id=name,
            servings=1,
            total_time_minutes=time,
            ingredients=[{"ingredient_id": "rice", "quantity": quantity, "unit": "g"}],
        )
        for name, time, quantity in [("a", 5, 1000), ("b", 10, 10)]
    ]
    slot = data["slots"][0]
    data.update(
        slots=[dict(slot, slot_id=str(i), servings=1, locked_recipe_id=None, max_time_minutes=20) for i in range(2)],
        nutrition_bands=[],
        health_preferences=[],
        pantry=[],
        purchase_budget_sgd=1,
        products=[
            {"ingredient_id": "rice", "product_id": "bag", "package_quantity": 100, "package_unit": "g", "price_sgd": 1}
        ],
    )
    return FinalPlanningProblem.model_validate(data)


def test_oracle_enumerates_all_four_combinations_and_finds_only_budget_valid_pair():
    result = exhaustive_assignments(small_packet())
    assert result.status == "optimal_for_fixed_shopping_policy"
    assert result.checked_combinations == result.total_combinations == 4
    assert result.feasible_combinations == 1
    assert result.best_choices == (("0", "b"), ("1", "b"))
    assert result.best_loss == pytest.approx(1.45)


def test_oracle_identifies_a_narrow_beam_miss():
    packet = small_packet()
    assert BeamPlanner(BeamLimits(width=1)).solve(packet).status == "candidate_rejected"
    oracle = exhaustive_assignments(packet)
    wide = BeamPlanner(BeamLimits(width=4)).solve(packet)
    assert wide.status == "feasible"
    assert tuple((a.slot_id, a.recipe_id) for a in wide.assignments) == oracle.best_choices


def test_search_limit_is_not_an_infeasibility_result():
    result = exhaustive_assignments(small_packet(), max_combinations=3)
    assert result.status == "limit_exceeded"
    assert result.checked_combinations == 0
    assert result.best_loss is None


def test_missing_product_evidence_prevents_optimality_claim():
    packet = small_packet().model_copy(update={"products": []})
    result = exhaustive_assignments(packet)
    assert result.status == "needs_data"
    assert result.unknown_combinations == 4


def test_oracle_validates_raw_candidates_instead_of_trusting_compiler_filters():
    packet = small_packet()
    packet = packet.model_copy(update={"allergens": packet.recipes[0].allergens})
    result = exhaustive_assignments(packet)
    assert result.status == "no_valid_assignment"
    assert result.checked_combinations == 4


def test_optional_slots_add_skip_choices_and_input_order_is_stable():
    packet = small_packet()
    packet = packet.model_copy(update={"slots": [s.model_copy(update={"required": False}) for s in packet.slots]})
    result = exhaustive_assignments(packet)
    assert result.total_combinations == 9
    assert result.best_choices == ()
    reordered = packet.model_copy(
        update={"slots": list(reversed(packet.slots)), "recipes": list(reversed(packet.recipes))}
    )
    assert exhaustive_assignments(reordered) == result


def test_zero_resource_limit_is_rejected():
    with pytest.raises(ValueError):
        exhaustive_assignments(small_packet(), max_combinations=0)
