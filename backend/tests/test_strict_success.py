import json

import pytest

from app.core.paths import repository_root
from app.evaluation.common_output import CommonEpisodeResponse, SchemaFailure, parse_response
from app.evaluation.strict_success import _UNIT_BASE as SCORER_UNITS
from app.evaluation.strict_success import (
    Catalogs,
    Tolerances,
    compatible,
    schema_failure_score,
    score_episode,
)
from app.planning.grocery_estimator import UNIT_BASE as PLANNER_UNITS

# --- fixtures ---------------------------------------------------------------
# Synthetic and tiny, so a change to the shipped catalog cannot quietly change
# what these tests assert.

RECIPES = [
    {
        "slug": "safe-bowl",
        "servings": 2,
        "meal_type": "main",
        "dietary_tags": ["vegetarian"],
        "prep_time_minutes": 10,
        "cook_time_minutes": 10,
        "ingredients": [{"ingredient": "brown_rice", "quantity": 200, "unit": "g"}],
    },
    {
        "slug": "sesame-bowl",
        "servings": 2,
        "meal_type": "main",
        "dietary_tags": ["vegetarian"],
        "prep_time_minutes": 10,
        "cook_time_minutes": 10,
        "ingredients": [{"ingredient": "sesame_oil", "quantity": 10, "unit": "ml"}],
    },
    {
        "slug": "slow-bowl",
        "servings": 2,
        "meal_type": "main",
        "dietary_tags": [],
        "prep_time_minutes": 60,
        "cook_time_minutes": 60,
        "ingredients": [{"ingredient": "brown_rice", "quantity": 200, "unit": "g"}],
    },
]
PRODUCTS = [
    {
        "external_id": "p-rice",
        "package_size": 500,
        "package_unit": "g",
        "price_sgd": 4.0,
        "ingredient_keys": ["brown_rice"],
    },
    {
        "external_id": "p-sesame",
        "package_size": 200,
        "package_unit": "ml",
        "price_sgd": 3.0,
        "ingredient_keys": ["sesame_oil"],
    },
]
INGREDIENTS = [
    {"normalized_name": "brown_rice", "allergen": None},
    {"normalized_name": "sesame_oil", "allergen": "sesame"},
]


@pytest.fixture
def catalogs():
    return Catalogs.build(RECIPES, PRODUCTS, INGREDIENTS)


def episode(**overrides):
    base = {
        "episode_id": "ho-standard-001",
        "category": "standard",
        "scenario": {
            "household_profile": {
                "household_size": 2,
                "allergens": ["sesame"],
                "excluded_ingredients": [],
            },
            "planning_horizon": {"slots": ["mon-dinner"]},
            "recipe_candidate_slugs": ["safe-bowl", "sesame-bowl", "slow-bowl"],
            "fairprice_product_ids": ["p-rice", "p-sesame"],
        },
        "gold": {
            "class": "feasible",
            "required_clarification_fields": [],
            "forbidden_clarification_fields": [],
            "applicable_hard_constraints": {
                "allergens_absent": ["sesame"],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": None,
                "nutrition_bands": [],
            },
            "pantry_ground_truth": {"deductible": [], "not_deductible_unknown_quantity": []},
            "conflict_reason": None,
            "allowed_relaxations": [],
        },
    }
    for path, value in overrides.items():
        target = base
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    return base


def response(**overrides):
    base = {
        "episode_id": "ho-standard-001",
        "system_id": "mealcraft",
        "status": "plan",
        "plan": {
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "required_quantity": 200,
                    "unit": "g",
                    "pantry_deduction": 0,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
        },
    }
    base.update(overrides)
    return CommonEpisodeResponse.model_validate(base)


def score(ep, resp, catalogs):
    return score_episode(ep, resp, catalogs)


# --- the guard against sharing a wrong implementation ------------------------


def test_scorer_unit_table_is_independent_but_agrees_with_the_planner():
    """RISKS.md R-26: if the scorer reused the planner's conversion, a bug there
    would mark MealCraft's own output correct. They are separate tables, so this
    asserts they agree on every pair the catalogs actually use."""
    root = repository_root()
    recipe_units = {
        item["unit"]
        for recipe in json.loads((root / "data/recipes/recipes.json").read_text(encoding="utf-8"))
        for item in recipe["ingredients"]
    }
    product_units = {
        product["package_unit"]
        for product in json.loads((root / "data/fixtures/fairprice-products.json").read_text(encoding="utf-8"))
    }
    assert recipe_units <= set(SCORER_UNITS), "a catalog unit the scorer cannot convert"

    for source in recipe_units:
        for target in product_units:
            mine = compatible(100.0, source, target)
            base_source, factor_source = PLANNER_UNITS.get(source, (None, None))
            base_target, factor_target = PLANNER_UNITS.get(target, (None, None))
            theirs = (
                100.0 * factor_source / factor_target
                if base_source is not None and base_source == base_target
                else None
            )
            assert mine == pytest.approx(theirs) if theirs is not None else mine is None, (
                f"scorer and planner disagree converting {source} -> {target}"
            )


# --- the happy path ----------------------------------------------------------


def test_a_correct_plan_is_a_strict_success(catalogs):
    result = score(episode(), response(), catalogs)
    assert result.strict_success, result.failed_codes + result.indeterminate_codes


# --- each way a feasible episode can fail ------------------------------------


def test_allergen_violation_fails(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "sesame-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "sesame_oil",
                    "unit": "ml",
                    "required_quantity": 10,
                    "product_id": "p-sesame",
                    "packages": 1,
                    "line_cost_sgd": 3.0,
                }
            ],
            "total_cost_sgd": 3.0,
        }
    )
    result = score(episode(), resp, catalogs)
    assert not result.strict_success
    assert "no_allergen_violation" in result.failed_codes


def test_unassigned_required_slot_fails(catalogs):
    ep = episode(**{"scenario.planning_horizon": {"slots": ["mon-dinner", "tue-dinner"]}})
    result = score(ep, response(), catalogs)
    assert "required_slots_assigned" in result.failed_codes


def test_recipe_outside_the_frozen_pool_fails(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "invented-bowl", "servings": 2}],
            "shopping": [],
            "total_cost_sgd": 0.0,
        }
    )
    assert "no_invented_recipe" in score(episode(), resp, catalogs).failed_codes


def test_cooking_time_limit_is_enforced(catalogs):
    ep = episode(
        **{
            "gold.applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": 30,
                "budget_sgd": None,
                "nutrition_bands": [],
            }
        }
    )
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "slow-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
        }
    )
    assert "cooking_time_respected" in score(ep, resp, catalogs).failed_codes


def test_missing_shopping_line_fails(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [],
            "total_cost_sgd": 0.0,
        }
    )
    assert "shopping_covers_plan" in score(episode(), resp, catalogs).failed_codes


def test_unknown_pantry_quantity_may_not_be_deducted(catalogs):
    ep = episode(**{"gold.pantry_ground_truth": {"deductible": [], "not_deductible_unknown_quantity": ["brown_rice"]}})
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "pantry_deduction": 200,
                    "product_id": "p-rice",
                    "packages": 0,
                    "line_cost_sgd": 0.0,
                }
            ],
            "total_cost_sgd": 0.0,
        }
    )
    assert "pantry_unknown_not_deducted" in score(ep, resp, catalogs).failed_codes


def test_packages_must_cover_the_remaining_demand(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 8}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 800,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
        }
    )
    assert "packages_cover_demand" in score(episode(), resp, catalogs).failed_codes


def test_line_cost_must_match_the_frozen_price(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 1.0,
                }
            ],
            "total_cost_sgd": 1.0,
        }
    )
    assert "line_cost_matches_snapshot" in score(episode(), resp, catalogs).failed_codes


def test_total_must_match_the_lines(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 99.0,
        }
    )
    assert "total_cost_matches_lines" in score(episode(), resp, catalogs).failed_codes


def test_a_false_budget_claim_fails_even_when_the_plan_is_valid(catalogs):
    ep = episode(
        **{
            "gold.applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": 1.0,
                "nutrition_bands": [],
            }
        }
    )
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
            "within_budget": True,
        }
    )
    result = score(ep, resp, catalogs)
    assert "budget_truthful" in result.failed_codes


def test_claiming_a_constraint_held_when_it_did_not_is_its_own_failure(catalogs):
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "sesame-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "sesame_oil",
                    "unit": "ml",
                    "required_quantity": 10,
                    "product_id": "p-sesame",
                    "packages": 1,
                    "line_cost_sgd": 3.0,
                }
            ],
            "total_cost_sgd": 3.0,
            "constraint_claims": [{"code": "no_allergen_violation", "satisfied": True}],
        }
    )
    result = score(episode(), resp, catalogs)
    assert "constraint_claims_truthful" in result.failed_codes
    assert "no_allergen_violation" in result.failed_codes


# --- clarification and infeasible --------------------------------------------


def test_clarification_episode_requires_the_question_and_no_plan(catalogs):
    ep = episode(**{"gold.class": "needs_clarification", "gold.required_clarification_fields": ["household_size"]})
    good = CommonEpisodeResponse.model_validate(
        {
            "episode_id": "ho-standard-001",
            "system_id": "s",
            "status": "clarification",
            "clarification": [{"field": "household_size", "question": "How many people?"}],
        }
    )
    assert score(ep, good, catalogs).strict_success

    silent = CommonEpisodeResponse.model_validate(
        {"episode_id": "ho-standard-001", "system_id": "s", "status": "clarification", "clarification": []}
    )
    assert "required_clarification_asked" in score(ep, silent, catalogs).failed_codes


def test_asking_about_information_already_given_fails(catalogs):
    ep = episode(
        **{
            "gold.class": "needs_clarification",
            "gold.required_clarification_fields": ["budget_sgd"],
            "gold.forbidden_clarification_fields": ["household_size"],
        }
    )
    resp = CommonEpisodeResponse.model_validate(
        {
            "episode_id": "ho-standard-001",
            "system_id": "s",
            "status": "clarification",
            "clarification": [
                {"field": "budget_sgd", "question": "What is your budget?"},
                {"field": "household_size", "question": "How many people?"},
            ],
        }
    )
    assert "no_unnecessary_clarification" in score(ep, resp, catalogs).failed_codes


def test_infeasible_requires_a_named_conflict_and_forbids_relaxing_safety(catalogs):
    ep = episode(**{"gold.class": "infeasible", "gold.conflict_reason": "budget below cheapest basket"})

    honest = CommonEpisodeResponse.model_validate(
        {
            "episode_id": "ho-standard-001",
            "system_id": "s",
            "status": "infeasible",
            "infeasible": {
                "conflict": "The budget is below the cheapest valid basket.",
                "allowed_relaxations": [{"description": "raise the budget", "field": "budget_sgd"}],
            },
        }
    )
    assert score(ep, honest, catalogs).strict_success

    unnamed = CommonEpisodeResponse.model_validate(
        {"episode_id": "ho-standard-001", "system_id": "s", "status": "infeasible", "infeasible": {"conflict": "   "}}
    )
    assert "conflict_named" in score(ep, unnamed, catalogs).failed_codes

    unsafe = CommonEpisodeResponse.model_validate(
        {
            "episode_id": "ho-standard-001",
            "system_id": "s",
            "status": "infeasible",
            "infeasible": {
                "conflict": "No plan fits.",
                "allowed_relaxations": [{"description": "drop the sesame restriction"}],
            },
        }
    )
    assert "relaxations_exclude_safety" in score(ep, unsafe, catalogs).failed_codes


def test_answering_with_the_wrong_class_fails(catalogs):
    ep = episode(**{"gold.class": "infeasible", "gold.conflict_reason": "no valid plan"})
    assert "status_matches_class" in score(ep, response(), catalogs).failed_codes


# --- schema failures ---------------------------------------------------------


def test_unreadable_output_is_a_schema_failure_and_not_a_success():
    with pytest.raises(SchemaFailure):
        parse_response("ho-standard-001", "Here is a lovely week of dinners!")

    result = schema_failure_score(episode(), "llm-only", "not JSON")
    assert result.schema_failure
    assert not result.strict_success


def test_an_unknown_output_field_is_rejected_rather_than_ignored():
    with pytest.raises(SchemaFailure):
        parse_response(
            "ho-standard-001",
            {"episode_id": "ho-standard-001", "system_id": "s", "status": "plan", "confidence": 0.9},
        )


# --- unverifiable is not the same as satisfied -------------------------------


def test_incomparable_units_are_indeterminate_and_block_success(catalogs):
    """A check that cannot be evaluated must not read as a pass."""
    odd_products = PRODUCTS + [
        {
            "external_id": "p-odd",
            "package_size": 1,
            "package_unit": "bushel",
            "price_sgd": 4.0,
            "ingredient_keys": ["brown_rice"],
        }
    ]
    cat = Catalogs.build(RECIPES, odd_products, INGREDIENTS)
    ep = episode(**{"scenario.fairprice_product_ids": ["p-rice", "p-sesame", "p-odd"]})
    resp = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 2}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 200,
                    "product_id": "p-odd",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
        }
    )
    result = score(ep, resp, cat)
    assert "packages_cover_demand" in result.indeterminate_codes
    assert not result.strict_success


def test_tolerances_come_from_the_frozen_manifest_not_from_defaults():
    """Scoring must use the declared tolerance, so that a later run cannot widen
    it. The defaults exist only so a caller that forgets is strict, not loose."""
    declared = Tolerances.from_manifest({"tolerances": {"cost_sgd_absolute": 0.5}})
    assert declared.cost_sgd_absolute == 0.5
    assert declared.quantity_relative == Tolerances().quantity_relative

    assert Tolerances.from_manifest({}) == Tolerances()
