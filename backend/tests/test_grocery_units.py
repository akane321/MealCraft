"""One liquid measured in grams by one dish and millilitres by another is one shopping line (walkthrough P19).

The 2026-10-04 walkthrough bought milk twice: 211 g of it as a carton of Meiji milk for one dish and 90 ml as
a carton of Low Fat Fresh Milk for another.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

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


def _milk_dishes(*units: str) -> list[Recipe]:
    """Seven synthetic mains, one a milk dish per unit in `units` (400 g, or 300 ml), sharing one milk."""
    from tests.test_planning_capability import _dish

    others = [("salmon-bake", "salmon_fillet"), ("chicken-roast", "chicken_breast"), ("tofu-bowl", "firm_tofu")]
    others += [("bean-chili", "black_bean"), ("mushroom-rice", "mushroom"), ("lentil-stew", "red_lentil")]
    milk = [_dish(f"milk-dish-{unit}", "main", "milk", 400 if unit == "g" else 300, calories=400) for unit in units]
    for dish, unit in zip(milk, units, strict=True):
        dish.recipe_ingredients[0].unit = unit
        dish.recipe_ingredients[0].ingredient = milk[0].recipe_ingredients[0].ingredient
    return milk + [_dish(slug, "main", name, 300, calories=450) for slug, name in others[: 7 - len(milk)]]


def _week(client, **request) -> dict:
    start = (date.today() + timedelta(days=1)).isoformat()
    payload = {"start_date": start, "household_size": 4, "pricing_mode": "fixture", "max_uses_per_recipe": 1}
    response = client.post("/api/plans/generate", json={**payload, **request})
    assert response.status_code == 201, response.text
    return response.json()


def test_milk_at_home_in_litres_covers_the_grams_the_planned_week_needs(monkeypatch) -> None:
    """The planner deducts the pantry as the weekly list does, so a change elsewhere leaves milk alone."""
    from tests.test_planning_capability import dish_client

    with dish_client(monkeypatch, _milk_dishes("g")) as client:
        plan = _week(client, available_ingredients=[{"normalized_name": "milk", "quantity": 1, "unit": "l"}])
        milk = [line for line in plan["grocery_estimate"]["items"] if line["ingredient_name"] == "milk"]
        assert [(line["unit"], line["pantry_deduction"], line["remaining_quantity"]) for line in milk] == [
            ("g", 400.0, 0.0)
        ]
        other = next(day for day in plan["days"] if day["recipe"]["slug"] != "milk-dish-g")
        skipped = client.post(
            f"/api/plans/{plan['id']}/replan/preview", json={"entry_id": other["entry_id"], "event_type": "CANCEL_MEAL"}
        )
        assert skipped.status_code == 201, skipped.text
        assert "milk" not in {row["ingredient_name"] for row in skipped.json()["grocery_delta"]}


def test_a_change_prices_the_rest_of_the_week_as_its_list_buys_it(monkeypatch) -> None:
    """The budget a new meal is planned with is what the week's list (milk by weight) leaves of it."""
    from tests.test_planning_capability import dish_client

    calls = []
    estimate = WeeklyGroceryAggregator.estimate

    def recorded(self, recipes, constraints, **options):
        calls.append(set(options.get("by_weight", ())))
        return estimate(self, recipes, constraints, **options)

    with dish_client(monkeypatch, _milk_dishes("g", "ml")) as client:
        dinner = {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}}
        plan = _week(client, plan_shape=dinner, weekly_budget_sgd=500, max_uses_per_recipe=None)
        assert {"milk-dish-g", "milk-dish-ml"} <= {day["recipe"]["slug"] for day in plan["days"]}
        assert [line["unit"] for line in plan["grocery_estimate"]["items"] if line["ingredient_name"] == "milk"] == [
            "g"
        ]
        monkeypatch.setattr(WeeklyGroceryAggregator, "estimate", recorded)
        lunch = client.post(
            f"/api/plans/{plan['id']}/shape/preview",
            json={"meal_type": "lunch", "roles": [{"role_id": "main", "courses": ["main"]}], "day_indexes": [7]},
        )
        assert lunch.status_code == 201, lunch.text
    assert len(calls) >= 2 and all("milk" in weighed for weighed in calls)


def test_the_floor_prices_a_liquid_by_the_gram_however_it_is_sold() -> None:
    """A week whose dishes measure milk both ways buys it by weight, so the floor must stay under that.

    One dish measures 100 ml of milk and its estimate prices a S$4.00 litre bottle; another weighs milk and
    prices 100 g packs at S$0.20. Seven of the first bought by weight cost 8 packs, S$1.60; priced by the
    bottle the floor said S$2.80 and refused a budget a week meets.
    """
    from types import SimpleNamespace

    from app.planning.week_floor import week_floor
    from app.schemas.meal_plan import MEAL_PRESETS, WeeklyMealPlanRequest

    def dish(recipe_id: int, quantity: float, unit: str, size: float, package_unit: str, price: float):
        product = SimpleNamespace(package_size=size, package_unit=package_unit, price_sgd=price)
        line = SimpleNamespace(ingredient_name="milk", unit=unit, required_quantity=quantity, product=product)
        recipe = SimpleNamespace(
            id=recipe_id, course="main", total_time_minutes=20, nutrition=SimpleNamespace(sodium_mg=1)
        )
        return SimpleNamespace(recipe=recipe, grocery_estimate=SimpleNamespace(items=[line], consumed_total_sgd=price))

    mains = [dish(1, 100, "ml", 1, "l", 4.0), dish(2, 500, "g", 100, "g", 0.2)]
    request = WeeklyMealPlanRequest(
        household_size=4, plan_shape={"meals": {"dinner": MEAL_PRESETS["dinner"]["one main"]}}
    )
    found = week_floor(request, mains, [item.recipe for item in mains])
    assert found.total_sgd == pytest.approx(7 * 100 * MILK_ML * 0.2 / 100)
    assert found.total_sgd <= 1.60

    # With only the litre bottle, both its package specification and the recipe's millilitres must be
    # converted to the same gram basis. Converting only the line leaves no matching unit price and a zero floor.
    volume_only = week_floor(request, mains[:1], [mains[0].recipe])
    assert volume_only.total_sgd == pytest.approx(7 * 4.0 * 100 / 1000)


def test_swap_budget_preview_keeps_the_saved_weight_price_for_liquids(monkeypatch) -> None:
    """A replacement that fits the gram-priced basket must not be rejected as a bottle purchase."""
    from types import SimpleNamespace

    from app.services.replanning import MealPlanReplanningService

    weighed_names = set()

    class BoundaryAggregator:
        def estimate(self, recipes, constraints, *, shares, by_weight=()):
            weighed_names.update(by_weight)
            # The same 100 ml of milk costs S$1.60 by the saved 100 g packs, or S$2.80 by the litre bottle.
            total = 1.60 if "milk" in by_weight else 2.80
            return SimpleNamespace(purchase_total_sgd=total)

    service = object.__new__(MealPlanReplanningService)
    service.grocery_aggregator = BoundaryAggregator()
    service._current_grocery = lambda plan: SimpleNamespace(items=[SimpleNamespace(ingredient_name="milk", unit="g")])
    current = SimpleNamespace(id=1, recipe_id=10, day_index=1, meal_type="dinner", status="planned", portion_share=1)
    plan = SimpleNamespace(entries=[current], purchase_total_sgd=1.60, pricing_mode="fixture")
    replacement = SimpleNamespace(recipe=SimpleNamespace(id=20))
    chosen, overage = service._fitting(
        plan,
        SimpleNamespace(weekly_budget_sgd=1.60),
        {10: SimpleNamespace(), 20: SimpleNamespace()},
        {},
        current,
        [replacement],
    )

    assert chosen is replacement
    assert overage is None
    assert "milk" in weighed_names
