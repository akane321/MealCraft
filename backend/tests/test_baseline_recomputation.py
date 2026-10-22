from app.evaluation.baseline_mapping import CoverageResult, IngredientMapping
from app.evaluation.baseline_recomputation import (
    IngredientEvaluationFacts,
    recompute_ingredient_baseline,
)
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption


def nutrients(**changes) -> PlanningNutrients:
    values = {
        "calories_kcal": 100,
        "protein_g": 10,
        "carbohydrate_g": 20,
        "fat_g": 5,
        "sodium_mg": 50,
        "sugar_g": 2,
    }
    return PlanningNutrients(**(values | changes))


def mapping(name: str, grams: float) -> IngredientMapping:
    return IngredientMapping(name, grams, name, "matched")


def product(ingredient: str, product_id: str, grams: float, price: float) -> PlanningProductOption:
    return PlanningProductOption(
        ingredient_id=ingredient,
        product_id=product_id,
        package_quantity=grams,
        package_unit="g",
        price_sgd=price,
        available=True,
    )


def test_recomputes_from_ingredient_grams_and_consolidates_package_demand():
    coverage = CoverageResult(
        total_grams=350,
        matched_grams=350,
        coverage=1,
        mappings=(mapping("tofu", 100), mapping("rice", 200), mapping("tofu", 50)),
    )

    result = recompute_ingredient_baseline(
        coverage,
        ingredient_facts={
            "tofu": IngredientEvaluationFacts(("soy",), nutrients(protein_g=12)),
            "rice": IngredientEvaluationFacts((), nutrients(protein_g=3)),
        },
        frozen_products=[
            product("tofu", "tofu-100", 100, 1.25),
            product("rice", "rice-500", 500, 2.0),
        ],
    )

    assert result.nutrition_complete is True
    assert result.nutrition.calories_kcal == 350
    assert result.nutrition.protein_g == 24
    assert result.allergens == ("soy",)
    assert result.allergens_complete is True
    assert result.pricing_status == "complete"
    assert result.purchase_total_sgd == 4.5
    tofu = next(item for item in result.price_results if item.ingredient_id == "tofu")
    assert tofu.required_grams == 150
    assert tofu.allocations[0].packages == 2


def test_unknown_facts_and_unmatched_rows_remain_explicitly_indeterminate():
    coverage = CoverageResult(
        total_grams=130,
        matched_grams=100,
        coverage=100 / 130,
        mappings=(
            mapping("mystery", 100),
            IngredientMapping("unmapped leaf", 30, None, "unmatched"),
        ),
    )

    result = recompute_ingredient_baseline(
        coverage,
        ingredient_facts={"mystery": IngredientEvaluationFacts(None, None)},
        frozen_products=[],
    )

    assert result.nutrition_complete is False
    assert result.nutrition_unknown_ingredients == ("mystery",)
    assert result.allergens_complete is False
    assert result.allergen_unknown_ingredients == ("mystery",)
    assert result.allergens == ()
    assert result.pricing_status == "needs_data"
    assert result.purchase_total_sgd is None
    assert {item.ingredient_id for item in result.price_results} == {"mystery"}


def test_exact_optimizer_can_mix_frozen_package_sizes_and_not_purchased_is_zero_cost():
    coverage = CoverageResult(
        total_grams=750,
        matched_grams=750,
        coverage=1,
        mappings=(mapping("rice", 700), mapping("water", 50)),
    )

    result = recompute_ingredient_baseline(
        coverage,
        ingredient_facts={
            "rice": IngredientEvaluationFacts((), nutrients()),
            "water": IngredientEvaluationFacts((), nutrients(calories_kcal=0, protein_g=0, carbohydrate_g=0, fat_g=0)),
        },
        frozen_products=[
            product("rice", "rice-400", 400, 2.0),
            product("rice", "rice-700", 700, 4.0),
        ],
        not_purchased=frozenset({"water"}),
    )

    assert result.pricing_status == "complete"
    assert result.purchase_total_sgd == 4.0
    water = next(item for item in result.price_results if item.ingredient_id == "water")
    assert water.purchase_cost_sgd == 0
    assert water.allocations == ()


def test_package_search_limit_is_not_reported_as_a_price():
    coverage = CoverageResult(100, 100, 1, (mapping("rice", 100),))

    result = recompute_ingredient_baseline(
        coverage,
        ingredient_facts={"rice": IngredientEvaluationFacts((), nutrients())},
        frozen_products=[
            product("rice", "rice-a", 10, 0.1),
            product("rice", "rice-b", 11, 0.1),
        ],
        max_package_combinations=1,
    )

    assert result.pricing_status == "limit_exceeded"
    assert result.purchase_total_sgd is None
