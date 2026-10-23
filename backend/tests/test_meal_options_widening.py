"""A slot whose best few dishes make no meal that passes still gets a meal from lower-ranked ones (2026-10-12)."""

import json
import time

import pytest

from app.core.paths import repository_root
from app.planning import meal_beam, product_path
from app.planning.meal_beam import LAST_STEP_COMBINATIONS, MealBeamLimits, MealBeamPlanner, integer_root
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


def salty_roles(count: int):
    """`count` roles over the same 45 salty dishes, so every meal of them is over the meal's sodium limit."""
    packet = five_salty_roles()
    packet.slots[0].composition = [
        PlanningMealRole(role_id="main" if i == 0 else f"main-{i + 1}", courses=["main"]) for i in range(count)
    ]
    return packet


def role_sizes(monkeypatch, packet, limits, scales):
    """Each role's options at each widening step, and the combinations the first step checked."""
    sizes, checked = [], []
    real = meal_beam.core_combinations

    def counted(per_role, *args):
        sizes.append([len(options) for options in per_role])
        for combination in real(per_role, *args):
            checked.append(combination)
            yield combination

    monkeypatch.setattr(meal_beam, "core_combinations", counted)
    planner = MealBeamPlanner(limits, local_losses={r.recipe_id: 0.0 for r in packet.recipes})
    for scale in scales:
        assert planner._meal_options(packet, packet.slots[0], scale)[0] == []
        if scale == 1:
            first = len(checked)
    return sizes, first


def test_the_combination_cap_shapes_every_widening_step_but_the_last(monkeypatch):
    """Owner, 2026-10-22: the cap is restored as a search-breadth parameter (removing it planned no better and took
    up to hours). A five-role meal under 16,384 keeps 6 dishes a role (6^5 = 7,776), its wider steps two and four
    times that, and the last step every eligible dish, bounded by `LAST_STEP_COMBINATIONS` instead."""
    sizes, first = role_sizes(monkeypatch, salty_roles(5), MealBeamLimits(max_meal_combinations=16384), (1, 2, 4, None))
    assert sizes == [[6] * 5, [12] * 5, [24] * 5, [45] * 5]
    assert first == 6**5


def test_no_cap_keeps_every_role_its_usual_dishes(monkeypatch):
    sizes, first = role_sizes(monkeypatch, salty_roles(5), MealBeamLimits(), (1,))
    assert sizes == [[8] * 5]
    assert first == 8**5


def test_a_seven_role_meal_keeps_four_dishes_a_role_under_16384(monkeypatch):
    """`int(16384 ** (1 / 7))` is 3, since the float root is 3.9999...; 4^7 is exactly 16,384."""
    sizes, first = role_sizes(monkeypatch, salty_roles(7), MealBeamLimits(max_meal_combinations=16384), (1,))
    assert sizes == [[4] * 7]
    assert first == 4**7


@pytest.mark.parametrize("power", range(1, 9))
def test_integer_root_is_exact(power):
    for root in range(1, 13):
        assert integer_root(root**power, power) == root
        assert integer_root(root**power - 1, power) == root - 1
        assert integer_root((root + 1) ** power - 1, power) == root


def test_the_product_cap_is_the_calibrated_one():
    """The product's cap is the sweep's chosen value (docs/evaluation/combination-cap-sweep, developer data)."""
    sweep = repository_root() / "docs/evaluation/combination-cap-sweep/latest.json"
    assert json.loads(sweep.read_text(encoding="utf-8"))["chosen_cap"] == product_path.MEAL_COMBINATIONS


@pytest.mark.parametrize("scale", [2, 4, None])
def test_a_wider_step_gives_up_after_its_combination_budget(scale):
    """Review of task 14: the last step had no cap, and a five-role meal that no combination passes enumerated the
    whole product (about 2e10 combinations for a real dinner, hours) before the slot was refused. Review of task 15:
    the two- and four-times steps grow the same way with the number of roles. Every step after the first checks
    `LAST_STEP_COMBINATIONS` and stops."""
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
