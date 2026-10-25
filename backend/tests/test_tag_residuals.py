"""Owner-approved carrier, grey-share, filling and unknown-source regressions."""

from types import SimpleNamespace as NS

import pytest

from app.data.recipe_tags import Dish, Line, release_dishes, rule_tags, staple_share
from app.evaluation.full_default import check_week
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.planning_v2 import PlanningMealRole
from app.services.replanning import MealPlanReplanningService


def tagged(title, lines, *, course="main"):
    dish = Dish(
        key="RCP2_TASK6",
        title=title,
        course=course,
        cuisine="test",
        servings=4,
        kcal=500,
        fat_g=15,
        sugar_g=5,
        carbohydrate_g=40,
        lines=[Line(name, grams, None) for name, grams in lines],
        steps="Cook.",
    )
    return dish, rule_tags(dish).values


@pytest.mark.parametrize(
    "carrier", ["tortilla", "pita_bread", "hamburger_bun", "dinner_roll", "english_muffin", "bread", "taco_shell"]
)
def test_listed_wrap_and_sandwich_carriers_supply_staple(carrier):
    _, tags = tagged("Chicken Kebab Wrap", [("chicken_thigh", 800), (carrier, 100)])
    assert tags["meal_role"] == "one_bowl" and tags["contains_staple"] is True
    _, no_bread = tagged("Chicken Kebab Wrap", [("chicken_thigh", 800), ("onion", 100)])
    assert no_bread["meal_role"] == "protein_main" and no_bread["contains_staple"] is False


@pytest.mark.parametrize(
    "title,grain", [("Bulgogi Bowl", "rice"), ("Beef with rice", "rice"), ("Goulash with macaroni", "macaroni")]
)
def test_grey_share_needs_a_title_and_matching_listed_grain(title, grain):
    dish, tags = tagged(title, [("beef", 900), (grain, 30)])
    assert 0.05 <= staple_share(dish) < 0.15
    assert tags["meal_role"] == "one_bowl" and tags["contains_staple"] is True
    _, unnamed = tagged("Beef Stew", [("beef", 900), (grain, 30)])
    assert unnamed["meal_role"] == "protein_main" and unnamed["contains_staple"] is False
    _, absent = tagged(title, [("beef", 900), ("onion", 30)])
    assert absent["meal_role"] == "protein_main" and absent["contains_staple"] is False


def test_grain_title_does_not_prove_a_different_grain_or_a_binder():
    for title, grain, grams in [
        ("Beef with rice", "macaroni", 30),
        ("Beef pasta", "rice", 30),
        ("Beef rice bowl", "rice", 5),
    ]:
        _, tags = tagged(title, [("beef", 900), (grain, grams)])
        assert tags["meal_role"] == "protein_main" and tags["contains_staple"] is False


@pytest.mark.parametrize(
    "title,protein",
    [
        ("Taco Meat Filling", "beef"),
        ("Beef Taco Filling", "beef"),
        ("Taco Filling (Ground Beef)", "beef"),
        ("Carnitas Filling", "pork"),
        ("Fish Taco Filling", "fish_fillet"),
        ("Tofu Filling", "tofu"),
    ],
)
def test_listed_protein_led_filling_is_a_main(title, protein):
    _, tags = tagged(title, [(protein, 600), ("onion", 100)])
    assert tags["meal_role"] == "protein_main" and tags["protein_sources"]
    assert tags["contains_staple"] is False


@pytest.mark.parametrize(
    "title,lines",
    [
        ("Cheese And Prosciutto Manicotti Filling", [("ricotta", 600), ("prosciutto", 80)]),
        ("Herbed Ricotta Filling For Manicotti", [("ricotta", 600), ("egg", 100)]),
        ("Chicken Pizza Topping", [("chicken_thigh", 600), ("onion", 100)]),
        ("Taco Meat Filling", [("meat", 600), ("onion", 100)]),
        ("Taco Meat Filling", [("beef", 1), ("onion", 600)]),
    ],
)
def test_cheese_toppings_and_unproven_filling_sources_remain_components(title, lines):
    _, tags = tagged(title, lines)
    assert tags["meal_role"] == "sauce" and tags["protein_sources"] == []


def test_pizza_batter_is_a_component_not_a_complete_pizza():
    lines = [("flour", 125), ("milk", 163), ("egg", 100), ("italian_seasoning", 1)]
    _, batter = tagged("Quick Shake Pizza", lines)
    assert batter["meal_role"] == "sauce" and batter["contains_staple"] is False
    _, topped = tagged("Quick Shake Pizza", [*lines, ("mozzarella", 100), ("tomato", 100)])
    assert topped["meal_role"] != "sauce"


def test_a_tortilla_bowl_without_a_filling_remains_a_staple_not_a_main():
    _, tags = tagged("Taco Salad Tortilla Bowl", [("tortilla", 300), ("vegetable_oil", 10)])
    assert tags["meal_role"] == "staple" and tags["contains_staple"] is True


def test_named_release_examples_follow_evidence_not_a_blanket_promotion():
    chosen = {
        d.key: rule_tags(d).values
        for d in release_dishes()
        if d.key in {"RCP2_7EE413539148", "RCP2_5494F0593A79", "RCP2_5B0A4C475A30"}
    }
    assert chosen["RCP2_7EE413539148"]["contains_staple"] is True
    # Adobo contains a little rice but its title does not name a grain/bowl: the two-part rule leaves it a main.
    assert chosen["RCP2_5494F0593A79"]["contains_staple"] is False
    assert chosen["RCP2_5B0A4C475A30"]["meal_role"] == "sauce"


@pytest.mark.parametrize(
    "candidate_sources,other_sources,valid",
    [
        (None, ["chicken"], False),
        (["pork"], None, False),
        (["chicken"], ["chicken"], False),
        (["pork"], ["chicken"], True),
        ([], ["chicken"], True),
    ],
)
def test_swaps_never_treat_unknown_sources_as_known_empty(candidate_sources, other_sources, valid):
    candidate = NS(meal_role="protein_main", contains_staple=False, protein_sources=candidate_sources, nutrition=None)
    entry = NS(role_id="main-2", meal_type="dinner", recipe=NS(meal_role="protein_main", contains_staple=False))
    others = [NS(role_id="main", recipe=NS(protein_sources=other_sources))]
    roles = [PlanningMealRole(role_id="main", meal_roles=["protein_main"])]
    assert MealPlanReplanningService._real_meal_holds(entry, candidate, others, roles) is valid


def test_non_main_swap_cannot_validate_an_unknown_existing_main():
    entry = NS(role_id="vegetable", meal_type="dinner")
    candidate = NS(nutrition=None)
    others = [NS(role_id="main", recipe=NS(protein_sources=None))]
    assert not MealPlanReplanningService._real_meal_holds(entry, candidate, others, [])


@pytest.mark.parametrize("sources,valid", [(None, False), ([], True), (["chicken"], True)])
def test_full_default_report_does_not_certify_unknown_sources(sources, valid):
    recipe = NS(
        meal_role="one_bowl",
        contains_staple=True,
        protein_sources=sources,
        recipe_ingredients=[],
        equipment=[],
        cuisine="test",
        cooking_methods=[],
    )
    week = {
        "grocery_estimate": {"items": [], "purchase_total_sgd": 0},
        "days": [
            {
                "day_index": 1,
                "meal_type": "dinner",
                "planned_date": "2027-01-03",
                "role_id": "main",
                "recipe": {"slug": "robot", "title": "Robot"},
                "nutrition_per_person": {"calories_kcal": 1000},
            }
        ],
    }
    request = WeeklyMealPlanRequest(
        household_size=1, day_count=1, household={"members": [{"name": "Robot", "servings": 1}]}
    )
    report = check_week(week, request, {"robot": recipe})
    assert report["checks"]["protein_sources_distinct"] is valid
