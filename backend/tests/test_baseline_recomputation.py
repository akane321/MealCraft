from app.evaluation.baseline_mapping import DishCoverage, IngredientMapping, PlanCoverage
from app.evaluation.baseline_recomputation import (
    IngredientEvaluationFacts,
    allergen_keywords,
    allergen_safety,
    dish_nutrition_per_serving,
    recompute_ingredient_baseline,
)
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption


def nutrients(**changes) -> PlanningNutrients:
    values = {"calories_kcal": 100, "protein_g": 10, "carbohydrate_g": 20, "fat_g": 5, "sodium_mg": 50, "sugar_g": 2}
    return PlanningNutrients(**(values | changes))


def mapping(name: str, grams: float, ingredient_id: str | None = "", **kwargs) -> IngredientMapping:
    ingredient_id = name if ingredient_id == "" else ingredient_id
    status = "matched" if ingredient_id else "unmatched"
    return IngredientMapping(name, grams, ingredient_id, status, **kwargs)


def plan(*mappings: IngredientMapping, servings: float = 2) -> PlanCoverage:
    return PlanCoverage((DishCoverage("mon-dinner", None, "dish", servings, 30, mappings),))


def product(ingredient: str, product_id: str, grams: float, price: float) -> PlanningProductOption:
    return PlanningProductOption(
        ingredient_id=ingredient, product_id=product_id, package_quantity=grams, package_unit="g", price_sgd=price
    )


FACTS = {
    "tofu": IngredientEvaluationFacts(("soy",), nutrients(protein_g=12)),
    "rice": IngredientEvaluationFacts((), nutrients(protein_g=3)),
    "mystery": IngredientEvaluationFacts(None, None),
}


def test_recomputes_from_grams_and_consolidates_package_demand():
    result = recompute_ingredient_baseline(
        plan(mapping("tofu", 100), mapping("rice", 200), mapping("tofu", 50)),
        ingredient_facts=FACTS,
        frozen_products=[product("tofu", "tofu-100", 100, 1.25), product("rice", "rice-500", 500, 2.0)],
    )
    assert result.nutrition_complete is True
    assert result.nutrition.calories_kcal == 350
    assert result.nutrition.protein_g == 24
    assert (result.allergens, result.allergens_complete) == (("soy",), True)
    assert (result.pricing_status, result.purchase_total_sgd) == ("complete", 4.5)
    tofu = next(item for item in result.price_results if item.ingredient_id == "tofu")
    assert (tofu.required_grams, tofu.allocations[0].packages) == (150, 2)


def test_unmapped_rows_are_carried_and_make_everything_incomplete():
    result = recompute_ingredient_baseline(
        plan(mapping("rice", 200), mapping("prawn paste", 20, None)),
        ingredient_facts=FACTS,
        frozen_products=[product("rice", "rice-500", 500, 2.0)],
    )
    assert result.unmapped_lines == ("prawn paste",)
    assert result.unmapped_grams == 20
    assert result.nutrition_complete is False
    assert result.allergens_complete is False
    assert result.allergens == ("shellfish",)  # the keyword scan reads the raw line
    assert (result.pricing_status, result.purchase_total_sgd) == ("needs_data", None)
    safe, reasons = allergen_safety(result, ["peanut"])
    assert safe is False and "unknown" in reasons[0]
    assert allergen_safety(result, [])[0] is True


def test_unknown_catalog_allergens_are_unsafe_and_unchecked_allergens_unverifiable():
    unknown = recompute_ingredient_baseline(plan(mapping("mystery", 100)), ingredient_facts=FACTS, frozen_products=[])
    assert unknown.allergens_complete is False
    assert unknown.allergen_unknown_lines == ("mystery",)
    assert unknown.nutrition_unknown_ingredients == ("mystery",)
    clean = recompute_ingredient_baseline(plan(mapping("rice", 100)), ingredient_facts=FACTS, frozen_products=[])
    safe, reasons = allergen_safety(clean, ["mustard"], checked=["peanut", "soy"])
    assert safe is False and "mustard" in reasons[0]
    assert allergen_safety(clean, ["peanut"], checked=["peanut", "soy"]) == (True, [])


def test_flagged_mapping_adds_keyword_allergens():
    flagged = mapping("peanut sauce", 30, "rice", needs_review=True)
    result = recompute_ingredient_baseline(plan(flagged), ingredient_facts=FACTS, frozen_products=[])
    assert result.allergens == ("peanut",)


def test_keyword_scan_skips_known_look_alikes():
    assert allergen_keywords("coconut milk") == frozenset()
    # A look-alike drops only its misleading word: the plant it is made of is still scanned.
    assert allergen_keywords("soy milk") == {"soy"}
    assert allergen_keywords("almond milk") == {"tree_nut"}
    assert allergen_keywords("unsweetened soymilk") == {"soy"}
    assert allergen_keywords("almondmilk") == {"tree_nut"}
    assert allergen_keywords("peanut butter") == {"peanut"}
    assert allergen_keywords("oyster mushrooms") == frozenset()
    assert allergen_keywords("egg noodles") == {"egg", "gluten"}
    assert allergen_keywords("虾仁") == {"shellfish"}


def test_dish_nutrition_per_serving_never_sums_a_partial_dish():
    assert dish_nutrition_per_serving(plan(mapping("rice", 200)).dishes[0], FACTS)["calories_kcal"] == 100
    assert dish_nutrition_per_serving(plan(mapping("rice", 200), mapping("x", 5, None)).dishes[0], FACTS) is None


def test_basics_cost_nothing_and_package_limit_is_not_a_price():
    bought = recompute_ingredient_baseline(
        plan(mapping("rice", 700), mapping("water", 50)),
        ingredient_facts=FACTS | {"water": IngredientEvaluationFacts((), nutrients())},
        frozen_products=[product("rice", "rice-400", 400, 2.0), product("rice", "rice-700", 700, 4.0)],
        not_purchased=frozenset({"water"}),
    )
    assert (bought.pricing_status, bought.purchase_total_sgd) == ("complete", 4.0)
    limited = recompute_ingredient_baseline(
        plan(mapping("rice", 100)),
        ingredient_facts=FACTS,
        frozen_products=[product("rice", "rice-a", 10, 0.1), product("rice", "rice-b", 11, 0.1)],
        max_package_combinations=1,
    )
    assert (limited.pricing_status, limited.purchase_total_sgd) == ("limit_exceeded", None)
