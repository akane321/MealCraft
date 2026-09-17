import json

import pytest

from app.core.paths import repository_root
from app.evaluation.common_output import CommonEpisodeResponse, SchemaFailure, parse_response
from app.evaluation.strict_success import _UNIT_BASE as SCORER_UNITS
from app.evaluation.strict_success import (
    Catalogs,
    Tolerances,
    compatible,
    load_tag_implications,
    satisfied_tags,
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
    return Catalogs.build(RECIPES, PRODUCTS, INGREDIENTS, tag_implications={})


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


def test_a_meal_must_feed_the_whole_household(catalogs):
    """Cooking for one in a household of two halves the shopping and must not pass."""
    one_serving = response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 1}],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": 100,
                    "product_id": "p-rice",
                    "packages": 1,
                    "line_cost_sgd": 4.0,
                }
            ],
            "total_cost_sgd": 4.0,
        }
    )
    result = score(episode(), one_serving, catalogs)
    assert "servings_feed_household" in result.failed_codes
    assert not result.strict_success


def test_a_feasible_episode_without_a_household_size_cannot_be_scored(catalogs):
    ep = episode(**{"scenario.household_profile.household_size": None})
    assert "servings_feed_household" in score(ep, response(), catalogs).indeterminate_codes


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


# --- dietary tags entailed by definition ------------------------------------
# The scorer compared raw tags, so a vegan dish served to a vegetarian household
# was scored as a violation. Twelve committed recipes are tagged vegan without
# also being tagged vegetarian.

IMPLICATIONS_FILE = "data/recipes/dietary-tag-implications.json"
VEGAN_BOWL = dict(RECIPES[0], slug="vegan-bowl", dietary_tags=["vegan"])


def vegetarian_episode():
    return episode(
        **{
            "scenario.recipe_candidate_slugs": ["vegan-bowl"],
            "gold.applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": ["vegetarian"],
                "max_cooking_time_minutes": None,
                "budget_sgd": None,
                "nutrition_bands": [],
            },
        }
    )


def vegan_plan():
    return response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "vegan-bowl", "servings": 2}],
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


def test_a_vegan_dish_satisfies_a_vegetarian_requirement():
    implications = load_tag_implications(repository_root() / IMPLICATIONS_FILE)
    catalogs = Catalogs.build(RECIPES + [VEGAN_BOWL], PRODUCTS, INGREDIENTS, tag_implications=implications)
    result = score(vegetarian_episode(), vegan_plan(), catalogs)
    assert result.strict_success, result.failed_codes + result.indeterminate_codes


def test_entailment_only_runs_one_way():
    # vegetarian does not entail vegan: a vegetarian dish is no answer to a vegan household.
    implications = load_tag_implications(repository_root() / IMPLICATIONS_FILE)
    assert "vegan" not in satisfied_tags(["vegetarian"], implications)
    assert {"vegetarian", "dairy-free"} <= satisfied_tags(["vegan"], implications)


def test_without_the_table_the_same_dish_is_a_violation():
    """Guards the reason the table is a required argument rather than a default."""
    catalogs = Catalogs.build(RECIPES + [VEGAN_BOWL], PRODUCTS, INGREDIENTS, tag_implications={})
    assert "dietary_tags_respected" in score(vegetarian_episode(), vegan_plan(), catalogs).failed_codes


def test_scorer_and_planner_close_tags_identically_on_the_committed_catalog():
    """Independent implementations of one definition; divergence must surface here."""
    from app.planning.dietary_tags import expand_tags, load_implications

    ours = load_tag_implications(repository_root() / IMPLICATIONS_FILE)
    recipes = json.loads((repository_root() / "data/recipes/recipes.json").read_text(encoding="utf-8"))
    for recipe in recipes:
        theirs = {tag.lower() for tag in expand_tags(recipe["dietary_tags"], load_implications())}
        assert satisfied_tags(recipe["dietary_tags"], ours) == theirs, recipe["slug"]


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


# --- one ingredient, several package sizes (ADR-0021) --------------------------
# Lines used to be keyed by ingredient, so the last line for an ingredient
# silently replaced the others and a correct mixed purchase was scored as short.

SMALL_RICE = {
    "external_id": "p-rice-small",
    "package_size": 300,
    "package_unit": "g",
    "price_sgd": 2.5,
    "ingredient_keys": ["brown_rice"],
}


@pytest.fixture
def mixed_catalogs():
    return Catalogs.build(RECIPES, PRODUCTS + [SMALL_RICE], INGREDIENTS, tag_implications={})


def mixed_episode(**overrides):
    return episode(**{"scenario.fairprice_product_ids": ["p-rice", "p-sesame", "p-rice-small"], **overrides})


def rice_lines(*lines):
    """800 g of rice needed; each entry is (product, packages, price, pantry_deduction)."""
    shopping = [
        {
            "ingredient_id": "brown_rice",
            "unit": "g",
            "required_quantity": 800,
            "pantry_deduction": deduction,
            "product_id": product,
            "packages": packages,
            "line_cost_sgd": price * packages,
        }
        for product, packages, price, deduction in lines
    ]
    return response(
        plan={
            "assignments": [{"slot_id": "mon-dinner", "recipe_id": "safe-bowl", "servings": 8}],
            "shopping": shopping,
            "total_cost_sgd": sum(line["line_cost_sgd"] for line in shopping),
        }
    )


def test_a_mixed_package_purchase_that_covers_demand_passes(mixed_catalogs):
    # 500 g + 300 g = 800 g, exactly the demand. Only the last line, 300 g, was counted before.
    resp = rice_lines(("p-rice", 1, 4.0, 0), ("p-rice-small", 1, 2.5, 0))
    result = score(mixed_episode(), resp, mixed_catalogs)
    assert result.strict_success, result.failed_codes + result.indeterminate_codes


def test_a_mixed_package_purchase_that_falls_short_still_fails(mixed_catalogs):
    resp = rice_lines(("p-rice", 1, 4.0, 0), ("p-rice-small", 0, 2.5, 0))
    assert "packages_cover_demand" in score(mixed_episode(), resp, mixed_catalogs).failed_codes


def test_pantry_deduction_is_summed_across_an_ingredients_lines(mixed_catalogs):
    ep = mixed_episode(
        **{
            "gold.pantry_ground_truth": {
                "deductible": [{"ingredient_id": "brown_rice", "quantity": 300, "unit": "g"}],
                "not_deductible_unknown_quantity": [],
            }
        }
    )
    # 300 g in the pantry, stated once; 500 g bought covers the remaining 500 g.
    once = rice_lines(("p-rice", 1, 4.0, 300), ("p-rice-small", 0, 2.5, 0))
    assert score(ep, once, mixed_catalogs).strict_success

    # Repeating the deduction on every line claims 600 g that the pantry does not hold.
    repeated = rice_lines(("p-rice", 1, 4.0, 300), ("p-rice-small", 0, 2.5, 300))
    assert "pantry_known_deduction_correct" in score(ep, repeated, mixed_catalogs).failed_codes


def test_only_what_the_plan_uses_is_deducted_from_a_larger_pantry(mixed_catalogs):
    """800 g needed, 1000 g in stock: deduct 800 and buy nothing."""
    ep = mixed_episode(
        **{
            "gold.pantry_ground_truth": {
                "deductible": [{"ingredient_id": "brown_rice", "quantity": 1000, "unit": "g"}],
                "not_deductible_unknown_quantity": [],
            }
        }
    )
    used = rice_lines(("p-rice", 0, 4.0, 800))
    result = score(ep, used, mixed_catalogs)
    assert result.strict_success, result.failed_codes + result.indeterminate_codes

    # Claiming the whole pantry was used overstates consumption by 200 g.
    claimed_all = rice_lines(("p-rice", 0, 4.0, 1000))
    assert "pantry_known_deduction_correct" in score(ep, claimed_all, mixed_catalogs).failed_codes


def test_an_unknown_quantity_deducted_on_any_line_fails(mixed_catalogs):
    ep = mixed_episode(
        **{
            "gold.pantry_ground_truth": {
                "deductible": [],
                "not_deductible_unknown_quantity": ["brown_rice"],
            }
        }
    )
    # The deducting line comes first: a scorer that keeps only the last line misses it.
    resp = rice_lines(("p-rice-small", 1, 2.5, 50), ("p-rice", 1, 4.0, 0))
    assert "pantry_unknown_not_deducted" in score(ep, resp, mixed_catalogs).failed_codes


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


def budget_episode(budget):
    return episode(
        **{
            "gold.applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": budget,
                "nutrition_bands": [],
            }
        }
    )


def four_dollar_plan(within_budget):
    return response(
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
            "within_budget": within_budget,
        }
    )


def test_exceeding_a_hard_budget_fails_even_when_the_system_admits_it(catalogs):
    """Truthfulness alone used to be scored, so an honest over-budget plan succeeded."""
    result = score(budget_episode(1.0), four_dollar_plan(within_budget=False), catalogs)
    assert "budget_respected" in result.failed_codes
    assert "budget_truthful" not in result.failed_codes
    assert not result.strict_success


def test_budget_is_compared_in_whole_cents_without_tolerance(catalogs):
    exact = score(budget_episode(4.0), four_dollar_plan(within_budget=True), catalogs)
    assert exact.strict_success, exact.failed_codes + exact.indeterminate_codes

    # One cent over fails, although the cost tolerance is also one cent, and a
    # system that says so is being truthful rather than contradicting the total.
    over = score(budget_episode(3.99), four_dollar_plan(within_budget=False), catalogs)
    assert "budget_respected" in over.failed_codes
    assert "budget_truthful" not in over.failed_codes


def test_a_false_budget_claim_is_a_failure_of_its_own(catalogs):
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


# --- nutrition targets ---------------------------------------------------------
# The gold field existed from the start, but nothing read it: a system that
# ignored a calorie or protein target passed exactly as one that met it.

LEAN = dict(RECIPES[0], slug="lean-bowl", nutrition={"protein_g": 20, "calories_kcal": 400})
RICH = dict(RECIPES[0], slug="rich-bowl", nutrition={"protein_g": 40, "calories_kcal": 600})
BARE = dict(RECIPES[0], slug="bare-bowl")  # no nutrition recorded at all


@pytest.fixture
def nutrition_catalogs():
    return Catalogs.build(RECIPES + [LEAN, RICH, BARE], PRODUCTS, INGREDIENTS, tag_implications={})


def nutrition_episode(*bands, slots=("mon-dinner",)):
    return episode(
        **{
            "scenario.planning_horizon": {"slots": list(slots)},
            "scenario.recipe_candidate_slugs": ["lean-bowl", "rich-bowl", "bare-bowl"],
            "gold.applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": None,
                "nutrition_bands": list(bands),
            },
        }
    )


def rice_plan(*recipe_ids, claims=()):
    """A plan whose shopping is correct, so only nutrition can decide the score."""
    grams = 200 * len(recipe_ids)
    packages = -(-grams // 500)
    return response(
        plan={
            "assignments": [
                {"slot_id": f"{day}-dinner", "recipe_id": rid, "servings": 2}
                for day, rid in zip(("mon", "tue", "wed"), recipe_ids, strict=False)
            ],
            "shopping": [
                {
                    "ingredient_id": "brown_rice",
                    "unit": "g",
                    "required_quantity": grams,
                    "product_id": "p-rice",
                    "packages": packages,
                    "line_cost_sgd": 4.0 * packages,
                }
            ],
            "total_cost_sgd": 4.0 * packages,
            "constraint_claims": list(claims),
        }
    )


def outcome(result, code):
    return next(check.outcome for check in result.checks if check.code == code)


def test_no_band_means_nutrition_is_not_applicable(nutrition_catalogs):
    result = score(nutrition_episode(), rice_plan("bare-bowl"), nutrition_catalogs)
    assert outcome(result, "nutrition_bands_respected") == "not_applicable"
    assert result.strict_success, result.failed_codes + result.indeterminate_codes


def test_a_per_serving_minimum_binds_every_dish(nutrition_catalogs):
    band = {"metric": "protein_g", "scope": "per_serving", "min": 30}
    met = score(nutrition_episode(band), rice_plan("rich-bowl"), nutrition_catalogs)
    assert met.strict_success, met.failed_codes + met.indeterminate_codes

    missed = score(nutrition_episode(band), rice_plan("lean-bowl"), nutrition_catalogs)
    assert "nutrition_bands_respected" in missed.failed_codes
    assert not missed.strict_success


def test_a_horizon_average_tolerates_one_low_dish_but_not_a_low_week(nutrition_catalogs):
    slots = ("mon-dinner", "tue-dinner")
    # 20 and 40 average to 30: the week meets the target though one dish does not.
    average = {"metric": "protein_g", "scope": "horizon_average", "min": 30}
    mixed = score(nutrition_episode(average, slots=slots), rice_plan("lean-bowl", "rich-bowl"), nutrition_catalogs)
    assert outcome(mixed, "nutrition_bands_respected") == "passed"

    # The same plan fails when the target binds every dish.
    per_dish = dict(average, scope="per_serving")
    strict = score(nutrition_episode(per_dish, slots=slots), rice_plan("lean-bowl", "rich-bowl"), nutrition_catalogs)
    assert outcome(strict, "nutrition_bands_respected") == "failed"

    low_week = score(nutrition_episode(average, slots=slots), rice_plan("lean-bowl", "lean-bowl"), nutrition_catalogs)
    assert outcome(low_week, "nutrition_bands_respected") == "failed"


def test_the_declared_relative_tolerance_applies_and_no_further(nutrition_catalogs):
    # 400 kcal against a 392 cap is 2.04% over: outside the 2% manifest slack.
    over = {"metric": "calories_kcal", "scope": "per_serving", "max": 392}
    assert (
        outcome(score(nutrition_episode(over), rice_plan("lean-bowl"), nutrition_catalogs), "nutrition_bands_respected")
        == "failed"
    )
    # 400 against 393 is 1.78% over: inside it.
    inside = dict(over, max=393)
    assert (
        outcome(
            score(nutrition_episode(inside), rice_plan("lean-bowl"), nutrition_catalogs), "nutrition_bands_respected"
        )
        == "passed"
    )


def test_a_band_without_a_scope_cannot_be_scored_and_blocks_success(nutrition_catalogs):
    unscoped = {"metric": "protein_g", "min": 30}
    result = score(nutrition_episode(unscoped), rice_plan("rich-bowl"), nutrition_catalogs)
    assert "nutrition_bands_respected" in result.indeterminate_codes
    assert not result.strict_success


def test_a_recipe_without_the_nutrient_is_indeterminate_not_a_pass(nutrition_catalogs):
    band = {"metric": "protein_g", "scope": "per_serving", "min": 1}
    result = score(nutrition_episode(band), rice_plan("bare-bowl"), nutrition_catalogs)
    assert "nutrition_bands_respected" in result.indeterminate_codes
    assert not result.strict_success


def test_claiming_a_nutrition_target_was_met_when_it_was_not_is_caught(nutrition_catalogs):
    band = {"metric": "protein_g", "scope": "per_serving", "min": 30}
    claim = {"code": "nutrition_bands_respected", "satisfied": True}
    result = score(nutrition_episode(band), rice_plan("lean-bowl", claims=[claim]), nutrition_catalogs)
    assert "constraint_claims_truthful" in result.failed_codes


def test_the_authoring_checker_uses_the_scorer_vocabulary():
    """The checker runs without the backend, so it carries a copy. Keep them one."""
    import importlib.util

    from app.evaluation import strict_success

    path = repository_root() / "scripts" / "check_heldout_episodes.py"
    spec = importlib.util.spec_from_file_location("check_heldout_episodes", path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)

    assert checker.NUTRITION_METRICS == set(strict_success.NUTRITION_METRICS)
    assert checker.NUTRITION_SCOPES == set(strict_success.NUTRITION_SCOPES)

    cases = [
        {"metric": "protein_g", "scope": "per_serving", "min": 30},
        {"metric": "protein_g", "min": 30},
        {"metric": "fibre_g", "scope": "per_serving", "min": 1},
        {"metric": "protein_g", "scope": "per_serving"},
        {"metric": "protein_g", "scope": "per_serving", "min": 40, "max": 30},
        {"metric": "protein_g", "scope": "per_serving", "min": True},
        "protein",
    ]
    for band in cases:
        assert (checker.nutrition_band_problem(band) is None) == (
            strict_success.nutrition_band_problem(band) is None
        ), band


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
    cat = Catalogs.build(RECIPES, odd_products, INGREDIENTS, tag_implications={})
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
