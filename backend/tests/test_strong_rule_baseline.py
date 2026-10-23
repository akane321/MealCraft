from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.pure_llm_baseline import BaselineResources
from app.evaluation.strong_rule_baseline import SYSTEM_ID, generate, run_episode
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

EPISODE = {
    "episode_id": "dev-rule-1",
    "scenario": {
        "user_request": "Plan two dinners for two people under $20.",
        "household_profile": {
            "household_size": 2,
            "allergens": [],
            "excluded_ingredients": [],
            "dietary_preferences": [],
            "meal_composition": [{"role_id": "main", "courses": ["main"], "required": True}],
        },
        "pantry": [],
        "planning_horizon": {"start_date": "2026-10-26", "slots": ["mon-dinner", "tue-dinner"]},
        "recipe_candidate_slugs": ["tofu-rice", "bean-rice"],
        "fairprice_product_ids": ["tofu-200", "beans-200", "rice-500"],
    },
}


def catalog():
    from app.evaluation.release_catalog import ReleaseCatalog

    def recipe(slug, title, ingredient):
        return {
            "slug": slug,
            "title": title,
            "course": "main",
            "meal_types": ["dinner"],
            "cuisine": "Asian",
            "servings": 2,
            "prep_time_minutes": 5,
            "cook_time_minutes": 15,
            "dietary_tags": ["vegetarian"],
            "ingredients": [
                {"ingredient": ingredient, "quantity": 200.0, "unit": "g"},
                {"ingredient": "rice", "quantity": 300.0, "unit": "g"},
            ],
            "nutrition": None,
            "nutrients": {},
        }

    return ReleaseCatalog(
        recipes=[recipe("tofu-rice", "Tofu rice", "tofu"), recipe("bean-rice", "Bean rice", "beans")],
        products=[
            {
                "external_id": "tofu-200",
                "ingredient_id": "tofu",
                "name": "Tofu",
                "package_size": 200.0,
                "package_unit": "g",
                "price_sgd": 2.0,
                "in_stock": True,
            },
            {
                "external_id": "beans-200",
                "ingredient_id": "beans",
                "name": "Beans",
                "package_size": 200.0,
                "package_unit": "g",
                "price_sgd": 2.5,
                "in_stock": True,
            },
            {
                "external_id": "rice-500",
                "ingredient_id": "rice",
                "name": "Rice",
                "package_size": 500.0,
                "package_unit": "g",
                "price_sgd": 3.0,
                "in_stock": True,
            },
        ],
        ingredients=[
            {"normalized_name": "tofu", "display_name": "Tofu", "allergens": ["soy"]},
            {"normalized_name": "beans", "display_name": "Beans", "allergens": []},
            {"normalized_name": "rice", "display_name": "Rice", "allergens": []},
        ],
    )


def resources():
    nutrients = PlanningNutrients(
        calories_kcal=100,
        protein_g=10,
        carbohydrate_g=20,
        fat_g=5,
        sodium_mg=50,
        sugar_g=2,
    )
    names = {"tofu": "Tofu", "beans": "Beans", "rice": "Rice"}
    return BaselineResources(
        names=names,
        aliases={},
        matcher=IngredientMatcher(names, mode="spelling"),
        ingredient_facts={
            "tofu": IngredientEvaluationFacts(("soy",), nutrients),
            "beans": IngredientEvaluationFacts((), nutrients),
            "rice": IngredientEvaluationFacts((), nutrients),
        },
        frozen_products=[
            PlanningProductOption(
                ingredient_id=row["ingredient_id"],
                product_id=row["external_id"],
                package_quantity=row["package_size"],
                package_unit="g",
                price_sgd=row["price_sgd"],
                available=True,
            )
            for row in catalog().products
        ],
        not_purchased=frozenset(),
    )


def test_rules_are_deterministic_and_report_zero_model_usage(monkeypatch):
    monkeypatch.setattr("app.evaluation.multidish_runner.load_release_catalog", catalog)

    first = generate(EPISODE)
    second = generate(EPISODE)

    assert first.response == second.response
    assert first.response is not None and first.response.system_id == SYSTEM_ID
    assert first.response.status == "plan"
    assert first.usage.total_tokens == 0
    assert first.usage.cost_usd == 0
    assert first.attempts == 1


def test_selected_catalog_recipes_become_baseline_response_grams(monkeypatch):
    monkeypatch.setattr("app.evaluation.multidish_runner.load_release_catalog", catalog)

    response = generate(EPISODE).response

    assert response is not None and response.plan is not None
    assert [meal.slot_id for meal in response.plan.meals] == ["mon-dinner", "tue-dinner"]
    assert {meal.dishes[0].name for meal in response.plan.meals} == {"Tofu rice", "Bean rice"}
    assert [ingredient.quantity_g for ingredient in response.plan.meals[0].dishes[0].ingredients] == [200, 300]


def test_output_uses_shared_mapping_verification_and_recomputation(monkeypatch):
    monkeypatch.setattr("app.evaluation.multidish_runner.load_release_catalog", catalog)

    result = run_episode(EPISODE, resources=resources())

    assert result.valid_output is True
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.allergens == ("soy",)
    assert result.recomputation.purchase_total_sgd == 10.5


def test_missing_household_size_returns_clarification_without_planning(monkeypatch):
    episode = {
        **EPISODE,
        "scenario": {
            **EPISODE["scenario"],
            "user_request": "Plan two dinners.",
            "household_profile": {**EPISODE["scenario"]["household_profile"], "household_size": None},
        },
    }
    monkeypatch.setattr(
        "app.evaluation.strong_rule_baseline.strong_rule_selector",
        lambda problem: (_ for _ in ()).throw(AssertionError("planner must not run")),
    )

    response = generate(episode).response

    assert response is not None
    assert response.status == "clarification"
    assert response.plan is None
