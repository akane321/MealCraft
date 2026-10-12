"""A slot whose best few dishes make no meal that passes still gets a meal from lower-ranked ones (2026-10-12)."""

from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner
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
