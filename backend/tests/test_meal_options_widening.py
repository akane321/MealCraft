"""A slot whose best few dishes make no meal that passes still gets a meal from lower-ranked ones (2026-10-12)."""

import time

import pytest

from app.planning import meal_beam
from app.planning.meal_beam import LAST_STEP_COMBINATIONS, MealBeamLimits, MealBeamPlanner
from app.schemas.planning_v2 import PlanningMealRole
from tests.test_planning_meal_composition import problem, recipe


def salty_first():
    salty = recipe("salty-main", "main", 10, 20, calories=500)
    salty["nutrients_per_serving"]["sodium_mg"] = 2400
    plain = recipe("plain-main", "main", 10, 20, calories=500)
    plain["nutrients_per_serving"]["sodium_mg"] = 300
    greens = recipe("greens", "side", 10, 10, calories=100, ingredient="spinach")
    packet = problem(
        recipes=[salty, plain, greens],
        products=[],
        nutrition_bands=[{"metric": "sodium_mg", "scope": "per_slot", "upper": 1500}],
    )
    packet.slots[0].composition = packet.slots[0].composition[:2]  # a main and a vegetable
    return packet


def test_a_slot_tries_lower_ranked_dishes_before_it_has_no_meal():
    packet = salty_first()
    # One main a role, and the salty one ranks first: every meal of it is over the meal's sodium limit.
    planner = MealBeamPlanner(
        MealBeamLimits(candidates_per_role=1), local_losses={"salty-main": 0.0, "plain-main": 5.0, "greens": 0.0}
    )
    meals = planner.meal_options(packet, packet.slots[0])
    assert meals, "the slot had no meal although plain-main and greens fit"
    assert {dict(meal.dishes)["main"] for meal in meals} == {"plain-main"}


def test_a_slot_with_no_meal_at_any_width_stays_empty():
    packet = salty_first()
    packet.recipes = [r for r in packet.recipes if r.recipe_id != "plain-main"]
    planner = MealBeamPlanner(MealBeamLimits(candidates_per_role=1), local_losses={"salty-main": 0.0, "greens": 0.0})
    assert planner.meal_options(packet, packet.slots[0]) == []


def test_a_meal_whose_first_32_mains_all_fail_still_gets_the_33rd():
    """Task 14 item 1. The widening stopped at four times a role's usual dishes (8 x 4 = 32) and returned no meal
    although an eligible main was left, and one meal with none refused the whole week (`mixed-diets`, layer 08 PR-4
    review round 3). The last step keeps every eligible dish."""
    packet = salty_first()
    salty = next(r for r in packet.recipes if r.recipe_id == "salty-main")
    many = [salty.model_copy(update={"recipe_id": f"salty-{i:02d}", "title": f"salty-{i:02d}"}) for i in range(32)]
    packet.recipes = [r for r in packet.recipes if r.recipe_id != "salty-main"] + many
    losses = {r.recipe_id: 0.0 for r in packet.recipes} | {"plain-main": 5.0}
    planner = MealBeamPlanner(MealBeamLimits(), local_losses=losses)
    assert planner.limits.candidates_per_role * 4 == len(many)
    meals = planner.meal_options(packet, packet.slots[0])
    assert {dict(meal.dishes)["main"] for meal in meals} == {"plain-main"}


def five_salty_roles():
    """Five roles of 45 dishes each, every meal of them over the meal's sodium limit."""
    packet = salty_first()
    salty = next(r for r in packet.recipes if r.recipe_id == "salty-main")
    packet.recipes = [
        salty.model_copy(update={"recipe_id": f"salty-{i:02d}", "title": f"salty-{i:02d}"}) for i in range(45)
    ]
    packet.slots[0].composition = [
        PlanningMealRole(role_id=role, courses=["main"]) for role in ("main", "main-2", "main-3", "main-4", "main-5")
    ]
    return packet


def test_each_role_of_a_five_role_meal_keeps_its_usual_dishes_and_every_combination_is_checked(monkeypatch):
    """Task 15 item 2: a cap of 16,384 combinations a meal shrank each role of a five-role meal from 8 dishes to 6,
    to save time only (owner, 2026-10-22). The first step keeps `candidates_per_role` a role and checks all 8^5."""
    packet = five_salty_roles()
    sizes, checked = [], []
    real = meal_beam.core_combinations

    def counted(per_role, *args):
        sizes.append([len(options) for options in per_role])
        for combination in real(per_role, *args):
            checked.append(combination)
            yield combination

    monkeypatch.setattr(meal_beam, "core_combinations", counted)
    planner = MealBeamPlanner(MealBeamLimits(), local_losses={r.recipe_id: 0.0 for r in packet.recipes})
    assert planner._meal_options(packet, packet.slots[0], 1) == ([], True)
    assert sizes == [[8] * 5]
    assert len(checked) == 8**5


@pytest.mark.parametrize("scale", [2, 4, None])
def test_a_wider_step_gives_up_after_its_combination_budget(scale):
    """Review of task 14: the last step had no cap, and a five-role meal that no combination passes enumerated the
    whole product (about 2e10 combinations for a real dinner, hours) before the slot was refused. Review of task 15:
    with no cap on a meal's combinations the two- and four-times steps grew the same way (about 3e10 for a
    seven-role dinner at four times). Every step after the first checks `LAST_STEP_COMBINATIONS` and stops."""
    packet = five_salty_roles()
    planner = MealBeamPlanner(MealBeamLimits(), local_losses={r.recipe_id: 0.0 for r in packet.recipes})
    started = time.perf_counter()
    # 16^5 (1e6), 32^5 (3e7) and 45^5 (1.8e8) combinations, of which each checks its budget (about a second).
    assert planner._meal_options(packet, packet.slots[0], scale) == ([], scale is not None)
    assert planner.last_step_tried == LAST_STEP_COMBINATIONS
    assert time.perf_counter() - started < 30


def test_a_slot_the_last_step_gave_up_on_is_recorded_with_its_count():
    """Every widening step, not the last alone: the slot is refused in seconds, not hours (task 15 review)."""
    packet = five_salty_roles()
    planner = MealBeamPlanner(MealBeamLimits(), local_losses={r.recipe_id: 0.0 for r in packet.recipes})
    result = planner.search_candidates(packet)
    assert result.empty_slot_ids == ("d1",)
    assert result.capped_slots == (("d1", LAST_STEP_COMBINATIONS),)
