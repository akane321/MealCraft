"""One liquid measured in grams by one dish and millilitres by another is one shopping line (walkthrough P19).

The 2026-10-04 walkthrough bought milk twice: 211 g of it as a carton of Meiji milk for one dish and 90 ml as
a carton of Low Fat Fresh Milk for another.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from app.core.paths import data_root
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning.grocery_estimator import GroceryEstimator
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.schemas.recommendation import AvailableIngredientInput, RecipeRecommendationRequest
from tests.test_planning_product_path import database
from tests.test_recipes import recipe_client as recipe_client

MILK_ML = 244 / 236.6  # grams of milk in a millilitre: 244 g a 236.6 ml cup


def test_densities_are_the_release_catalog_cup_weights() -> None:
    from app.data.units import CUP_ML, GRAMS_PER_CUP

    assert CUP_ML == 236.6
    release = data_root().parent / "data-engineering/data/release/v2.1/ingredients.jsonl"
    cups = {}
    for line in release.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for form in record["forms"].values():
            for weight in form.get("unit_grams") or []:
                if weight["unit"] == "cup":
                    cups.setdefault(record["ingredient_id"][4:].lower(), weight["grams"])
    assert {name: cups.get(name) for name in GRAMS_PER_CUP} == GRAMS_PER_CUP


def _dish(ingredient: Ingredient, quantity: float, unit: str) -> Recipe:
    return Recipe(
        servings=2,
        recipe_ingredients=[RecipeIngredient(ingredient=ingredient, quantity=quantity, unit=unit, sort_order=1)],
    )


def _lines(*dishes: Recipe, by_weight=()):
    request = RecipeRecommendationRequest(household_size=2)
    hint = {"by_weight": by_weight} if by_weight else {}
    lines = WeeklyGroceryAggregator._aggregate_ingredients(list(dishes), request, **hint)
    return [(line.name, line.unit, round(line.required_quantity, 3)) for line in lines]


def test_grams_and_millilitres_of_milk_are_one_line_in_grams() -> None:
    milk = Ingredient(normalized_name="milk", display_name="Milk", allergens=["milk"])
    assert _lines(_dish(milk, 211.467, "g"), _dish(milk, 90, "ml")) == [("milk", "g", round(211.467 + 90 * MILK_ML, 3))]
    # A tablespoon is 15 ml before it is weighed.
    assert _lines(_dish(milk, 100, "g"), _dish(milk, 2, "tbsp")) == [("milk", "g", round(100 + 30 * MILK_ML, 3))]


def test_a_liquid_in_one_unit_and_an_ingredient_with_no_density_keep_their_lines() -> None:
    milk = Ingredient(normalized_name="milk", display_name="Milk", allergens=["milk"])
    honey = Ingredient(normalized_name="honey", display_name="Honey", allergens=[])
    assert _lines(_dish(milk, 150, "ml"), _dish(milk, 100, "ml")) == [("milk", "ml", 250.0)]
    assert _lines(_dish(honey, 20, "g"), _dish(honey, 1, "tbsp")) == [("honey", "g", 20.0), ("honey", "ml", 15.0)]


def test_a_list_that_buys_milk_by_weight_keeps_buying_it_by_weight() -> None:
    milk = Ingredient(normalized_name="milk", display_name="Milk", allergens=["milk"])
    assert _lines(_dish(milk, 150, "ml"), by_weight={"milk", "honey"}) == [("milk", "g", round(150 * MILK_ML, 3))]


def test_a_litre_of_milk_at_home_covers_grams_of_it() -> None:
    pantry = AvailableIngredientInput(normalized_name="milk", quantity=1, unit="l")
    assert GroceryEstimator.pantry_deduction(pantry, 500.0, "g") == 500.0
    assert round(GroceryEstimator.pantry_deduction(pantry, 2000.0, "g"), 3) == round(1000 * MILK_ML, 3)
    honey = AvailableIngredientInput(normalized_name="honey", quantity=1, unit="l")
    assert GroceryEstimator.pantry_deduction(honey, 500.0, "g") == 0.0


def _recipe(slug: str, lines: list[tuple[Ingredient, str, str]]) -> Recipe:
    return Recipe(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description="A test dinner.",
        cuisine="Test",
        meal_type="main",
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=10,
        dietary_tags=[],
        nutrition=RecipeNutrition(
            calories_kcal=Decimal("450"),
            protein_g=Decimal("30"),
            carbohydrate_g=Decimal("40"),
            fat_g=Decimal("15"),
            sodium_mg=Decimal("400"),
            sugar_g=Decimal("6"),
        ),
        recipe_ingredients=[
            RecipeIngredient(ingredient=ingredient, quantity=Decimal(quantity), unit=unit, sort_order=index)
            for index, (ingredient, quantity, unit) in enumerate(lines, start=1)
        ],
        steps=[RecipeStep(step_number=1, instruction="Cook it.")],
    )


def test_a_planned_week_and_its_swap_buy_milk_once_by_weight(recipe_client) -> None:
    """The product path, its validator and the saved list; then a swap's list and its change to the list."""
    with database() as session:
        names = ("milk", "rolled_oats", "carrot", "broccoli", "egg", "zucchini")
        found = {i.normalized_name: i for i in session.query(Ingredient).filter(Ingredient.normalized_name.in_(names))}
        milk, oats, carrot, broccoli, egg, zucchini = (
            found.get(name) or Ingredient(normalized_name=name, display_name=name.replace("_", " ").capitalize())
            for name in names
        )
        session.add_all(
            [
                _recipe("milk-oats", [(milk, "150", "ml"), (oats, "100", "g")]),
                _recipe("milk-custard", [(milk, "200", "g"), (egg, "2", "whole")]),
                _recipe("carrot-bake", [(carrot, "300", "g")]),
                _recipe("broccoli-bake", [(broccoli, "300", "g")]),
                _recipe("zucchini-bake", [(zucchini, "300", "g")]),
            ]
        )
        session.commit()
    start = date.today() + timedelta(days=1)
    request = {"start_date": start.isoformat(), "household_size": 2, "pricing_mode": "fixture"}
    response = recipe_client.post("/api/plans/generate", json={**request, "max_uses_per_recipe": 1})
    assert response.status_code == 201, response.text
    plan = response.json()
    assert {day["recipe"]["slug"] for day in plan["days"]} >= {"milk-oats", "milk-custard"}
    milk_lines = [line for line in plan["grocery_estimate"]["items"] if line["ingredient_name"] == "milk"]
    assert [(line["unit"], line["required_quantity"]) for line in milk_lines] == [("g", round(200 + 150 * MILK_ML, 3))]
    assert milk_lines[0]["product"]["package_unit"] == "g" and milk_lines[0]["packages_required"] == 1

    # Swapping the dish that measures milk in grams leaves milk in millilitres only; the list keeps buying it
    # by weight, so the change shows milk at its new amount, not as one line taken off and another added.
    with database() as session:
        session.add(_recipe("egg-bake", [(egg, "4", "whole")]))
        session.commit()
    custard = next(day for day in plan["days"] if day["recipe"]["slug"] == "milk-custard")
    preview = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview", json={"event_type": "REPLACE_MEAL", "entry_id": custard["entry_id"]}
    )
    assert preview.status_code == 201, preview.text
    milk_rows = [
        (row["change"], row["unit"], row["after_required_quantity"] and round(row["after_required_quantity"], 3))
        for row in preview.json()["grocery_delta"]
        if row["ingredient_name"] == "milk"
    ]
    assert milk_rows == [("updated", "g", round(150 * MILK_ML, 3))]
