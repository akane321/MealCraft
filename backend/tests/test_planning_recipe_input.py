from datetime import UTC, datetime

import pytest

from app.core.paths import repository_root
from app.planning.mixed_beam import solve_mixed_beam
from app.planning.product_input import product_input
from app.planning.recipe_input import recipe_input
from app.schemas.planning_v2 import FinalPlanningProblem
from app.schemas.product import ProductResponse
from app.schemas.recipe import RecipeDetailResponse


def recipe():
    return RecipeDetailResponse(
        id=12,
        slug="rice-dish",
        title="Rice",
        description="Synthetic",
        cuisine="test",
        meal_type="main",
        servings=2,
        total_time_minutes=20,
        dietary_tags=["vegan"],
        nutrition=dict(calories_kcal=100, protein_g=3, carbohydrate_g=20, fat_g=1, sodium_mg=0, sugar_g=0),
        ingredients=[
            dict(name="Rice", normalized_name="rice", quantity=100, unit="g", preparation=None, allergen=None)
        ],
        steps=[],
    )


def convert(source):
    return recipe_input(source, allowed_meal_types=("dinner",), nutrition_basis="per_serving")


def test_serving_basis_identity_and_zero_nutrition_are_preserved():
    source = recipe()
    result = convert(source)
    assert result.candidate.recipe_id == "rice-dish"
    assert result.source.id == 12
    assert result.candidate.servings == 2
    assert result.candidate.ingredients[0].quantity == 100
    assert result.candidate.nutrients_per_serving.calories_kcal == 100
    assert result.candidate.nutrients_per_serving.sodium_mg == 0
    assert result.candidate.allowed_meal_types == ["dinner"]
    source.ingredients[0].quantity = 999
    assert result.source.ingredients[0].quantity == 100


def test_unknown_quantity_and_source_allergens_are_preserved():
    source = recipe()
    source.ingredients[0].quantity = None
    source.ingredients[0].allergen = "soy"
    result = convert(source)
    assert result.candidate.ingredients[0].quantity is None
    assert result.candidate.allergens == ["soy"]


@pytest.mark.parametrize("case", ["no_unit", "blank_id", "negative_nutrition", "infinity", "too_many_servings"])
def test_invalid_source_never_becomes_a_candidate(case):
    source = recipe()
    if case == "no_unit":
        source.ingredients[0].unit = None
    elif case == "blank_id":
        source.ingredients[0].normalized_name = " "
    elif case == "negative_nutrition":
        source.nutrition.protein_g = -1
    elif case == "infinity":
        source.nutrition.protein_g = float("inf")
    else:
        source.servings = 25
    result = convert(source)
    assert result.candidate is None
    assert result.issues


@pytest.mark.parametrize("meals,basis", [((), "per_serving"), (("main",), "per_serving"), (("dinner",), "per_recipe")])
def test_legacy_semantics_are_never_guessed(meals, basis):
    with pytest.raises(ValueError):
        recipe_input(recipe(), allowed_meal_types=meals, nutrition_basis=basis)


def test_converted_recipe_and_products_reach_mixed_planner_without_double_scaling():
    path = repository_root() / "data/fixtures/planning-v2/mixed-package-developer.json"
    problem = FinalPlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
    converted = recipe_input(
        recipe(), allowed_meal_types=tuple(s.meal_type for s in problem.slots), nutrition_basis="per_serving"
    )
    problem.recipes = [converted.candidate]
    problem.products = [
        product_input(
            ProductResponse(
                external_id=product_id,
                name="Synthetic rice package",
                brand=None,
                category=None,
                package_size=quantity,
                package_unit="g",
                price_sgd=price,
                product_url="https://example.test/rice",
                image_url=None,
                in_stock=True,
                source="fixture",
                fetched_at=datetime(2026, 9, 14, tzinfo=UTC),
            ),
            ingredient_id="rice",
            required_unit="g",
        ).option
        for product_id, quantity, price in (("large", 150, 2), ("small", 100, 1.5))
    ]
    for slot in problem.slots:
        slot.locked_recipe_id = None
    result = solve_mixed_beam(problem)
    assert result.status == "feasible"
    assert result.shopping.lines[0].required_quantity == 300
    assert result.shopping.lines[0].pantry_deduction == 50
    assert result.shopping.purchase_total_sgd == 3.5
