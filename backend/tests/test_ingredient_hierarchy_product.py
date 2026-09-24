"""The product uses the ingredient hierarchy: an exclusion removes what belongs to it.

Two entry points expand a household's exclusions (ADR-0039, WP1): the recommendation engine
and the planning product path. The agent's vocabulary offers groups. None of these tests reads
WP2 or WP3 data; a test needing `bacon` -> `pork` writes its own table in a temporary directory.
"""

import json
from decimal import Decimal

import pytest

from app.agent.parser import ConstraintVocabulary, align_to_vocabulary, catalog_groups
from app.data import ingredient_hierarchy
from app.data.ingredient_hierarchy import FILES, GROUPS_FILE, expand_exclusions, read_links
from app.models.recipe import Ingredient, Recipe, RecipeIngredient, RecipeNutrition, RecipeStep
from app.planning import product_path
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.schemas.agent import AgentConstraintExtraction
from app.schemas.recommendation import AvailableIngredientInput, RecipeRecommendationRequest
from tests.test_recipes import recipe_client as recipe_client

REQUEST = {"start_date": "2026-09-20", "household_size": 2, "pricing_mode": "fixture"}
ALCOHOL = {"group:alcohol": {"description": "Every drink that contains alcohol.", "serves": "No alcohol at all."}}


def use_table(monkeypatch, tmp_path, entries=None, groups=None):
    """Make the product read a table written for this test, not the committed one."""
    directory = tmp_path / "data/ingredients/hierarchy"
    directory.mkdir(parents=True)
    directory.joinpath(GROUPS_FILE).write_text(
        json.dumps({"schema_version": "ingredient-hierarchy-v1", "groups": groups or {}}), encoding="utf-8"
    )
    document = {"schema_version": "ingredient-hierarchy-v1", "package": "WP2", "entries": entries or {}}
    directory.joinpath(FILES["WP2"]).write_text(json.dumps(document), encoding="utf-8")
    links = read_links(tmp_path)
    monkeypatch.setattr(ingredient_hierarchy, "runtime", lambda: links)
    return links


def link(child_parent, relation="made_from"):
    return {"parents": [{"id": child_parent, "relation": relation}], "not_parents": [], "reason": "a test link"}


def recipe(recipe_id, slug, *ingredient_names):
    return Recipe(
        id=recipe_id,
        slug=slug,
        title=slug.replace("-", " ").title(),
        description="A test dish.",
        cuisine="Test",
        meal_type="main",
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=20,
        dietary_tags=[],
        nutrition=RecipeNutrition(
            calories_kcal=Decimal("500"),
            protein_g=Decimal("30"),
            carbohydrate_g=Decimal("50"),
            fat_g=Decimal("15"),
            sodium_mg=Decimal("500"),
            sugar_g=Decimal("5"),
        ),
        recipe_ingredients=[
            RecipeIngredient(
                ingredient=Ingredient(normalized_name=name, display_name=name, allergens=[]),
                quantity=Decimal("100"),
                unit="g",
                sort_order=order,
            )
            for order, name in enumerate(ingredient_names, start=1)
        ],
        steps=[RecipeStep(step_number=1, instruction="Cook it.")],
    )


def recommend(recipes, *excluded):
    request = RecipeRecommendationRequest(household_size=2, excluded_ingredients=list(excluded))
    recommended, excluded_recipes = RecipeRecommendationEngine().recommend(recipes, request)
    return [item.recipe.slug for item in recommended], {item.slug: item.reasons for item in excluded_recipes}


# ----- 1. an empty table changes nothing -----


def test_an_empty_table_leaves_exclusions_exactly_as_they_were(monkeypatch, tmp_path):
    use_table(monkeypatch, tmp_path)

    assert expand_exclusions(["x"]) == ["x"]
    assert expand_exclusions(["pork", "wine_cooking"]) == ["pork", "wine_cooking"]
    assert expand_exclusions([]) == []

    kept, excluded = recommend([recipe(1, "bacon-pasta", "bacon"), recipe(2, "pork-stew", "pork")], "pork")
    assert kept == ["bacon-pasta"]  # today's behaviour: nothing says bacon is pork
    assert excluded == {"pork-stew": ["Contains excluded ingredient: pork."]}  # the wording it always had


def test_an_empty_table_still_lets_the_planner_serve_tofu_for_a_tofu_exclusion(recipe_client, monkeypatch, tmp_path):
    use_table(monkeypatch, tmp_path)

    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "excluded_ingredients": ["tofu"]})

    assert response.status_code == 201, response.text
    assert {entry["recipe"]["slug"] for entry in response.json()["days"]} == {"lemon-chicken", "tofu-soba"}


# ----- 2. the planning path expands -----


def test_the_planning_path_hands_the_planner_the_expanded_exclusions(recipe_client, monkeypatch):
    """Real WP1 data: `firm_tofu` is a kind of `tofu`, so excluding tofu excludes it."""
    handed = []
    real = product_path.FinalPlanningProblem

    def spy(**fields):
        handed.append(fields["excluded_ingredients"])
        return real(**fields)

    monkeypatch.setattr(product_path, "FinalPlanningProblem", spy)

    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "excluded_ingredients": ["tofu"]})

    assert response.status_code == 201, response.text
    assert handed and all(excluded == ["firm_tofu", "tofu"] for excluded in handed)
    assert {entry["recipe"]["slug"] for entry in response.json()["days"]} == {"lemon-chicken"}


def test_excluding_the_curated_id_does_not_climb_to_the_release_id(recipe_client, monkeypatch):
    handed = []
    real = product_path.FinalPlanningProblem

    def spy(**fields):
        handed.append(fields["excluded_ingredients"])
        return real(**fields)

    monkeypatch.setattr(product_path, "FinalPlanningProblem", spy)

    response = recipe_client.post("/api/plans/generate", json={**REQUEST, "excluded_ingredients": ["firm_tofu"]})

    assert response.status_code == 201, response.text
    assert handed and all(excluded == ["firm_tofu"] for excluded in handed)  # not tofu, not every kind of tofu


# ----- 3. the recommendation engine expands, and says why truthfully -----


def test_recommendations_exclude_what_belongs_to_an_exclusion_and_name_both_words(monkeypatch, tmp_path):
    use_table(monkeypatch, tmp_path, {"bacon": link("pork"), "bacon_grease": link("bacon")})

    kept, excluded = recommend(
        [
            recipe(1, "carbonara", "bacon", "pasta"),
            recipe(2, "fried-eggs", "bacon_grease", "egg"),
            recipe(3, "pork-stew", "pork"),
            recipe(4, "tomato-pasta", "tomato", "pasta"),
        ],
        "pork",
    )

    assert kept == ["tomato-pasta"]
    assert excluded["carbonara"] == ["Contains excluded ingredient: bacon (excluded: pork)."]
    assert excluded["fried-eggs"] == ["Contains excluded ingredient: bacon_grease (excluded: pork)."]
    assert excluded["pork-stew"] == ["Contains excluded ingredient: pork."]  # what the household said stays as it was


def test_a_group_the_household_names_excludes_its_members(monkeypatch, tmp_path):
    use_table(
        monkeypatch,
        tmp_path,
        {"sake": link("group:alcohol", "variety"), "wine_cooking": link("group:alcohol", "variety")},
        ALCOHOL,
    )

    kept, excluded = recommend(
        [recipe(1, "teriyaki", "sake", "chicken"), recipe(2, "salad", "lettuce")], "group:alcohol"
    )

    assert kept == ["salad"]
    assert excluded["teriyaki"] == ["Contains excluded ingredient: sake (excluded: group:alcohol)."]


def test_recommendations_expand_once_per_call_not_once_per_recipe(monkeypatch, tmp_path):
    use_table(monkeypatch, tmp_path, {"bacon": link("pork")})
    calls = []
    real = ingredient_hierarchy.expand_exclusions
    monkeypatch.setattr(
        ingredient_hierarchy, "expand_exclusions", lambda excluded: calls.append(list(excluded)) or real(excluded)
    )

    recommend([recipe(i, f"dish-{i}", "bacon") for i in range(1, 6)], "pork")

    assert calls == [["pork"]]


def test_the_committed_wp1_data_makes_a_tofu_exclusion_catch_the_curated_tofu(recipe_client):
    response = recipe_client.post(
        "/api/recommendations/recipes", json={"household_size": 2, "excluded_ingredients": ["tofu"]}
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["recipe"]["slug"] for item in payload["recommendations"]] == ["lemon-chicken"]
    assert payload["excluded"][0]["slug"] == "tofu-soba"
    assert payload["excluded"][0]["reasons"] == ["Contains excluded ingredient: firm_tofu (excluded: tofu)."]


# ----- 4. the agent accepts groups -----


VOCABULARY = ConstraintVocabulary(
    ingredients=frozenset({"sake", "pork", "wine_cooking"}),
    groups={"group:alcohol": "Every drink that contains alcohol."},
)


def test_the_agent_keeps_a_group_as_an_exclusion_and_does_not_ask_about_it():
    extraction = AgentConstraintExtraction(excluded_ingredients=["group:alcohol", "pork", "group:seafood", "beer"])

    aligned = align_to_vocabulary(extraction, VOCABULARY)

    assert aligned.excluded_ingredients == ["group:alcohol", "pork"]
    assert aligned.unmatched_terms == ["group:seafood", "beer"]  # an undeclared group is still not a word


def test_a_group_is_no_pantry_item():
    extraction = AgentConstraintExtraction(
        available_ingredients=[AvailableIngredientInput(normalized_name="group:alcohol", quantity=None, unit=None)]
    )

    aligned = align_to_vocabulary(extraction, VOCABULARY)

    assert aligned.available_ingredients is None
    assert aligned.unmatched_terms == ["group:alcohol"]


def test_the_prompt_lists_each_group_with_what_it_covers_and_is_unchanged_without_groups():
    prompt = VOCABULARY.prompt()

    assert "group:alcohol: Every drink that contains alcohol." in prompt
    assert "group id" in prompt
    assert "group:" not in ConstraintVocabulary(ingredients=frozenset({"pork"})).prompt()


def test_the_products_own_vocabulary_carries_the_declared_groups():
    groups = catalog_groups()

    assert "group:alcohol" in groups
    assert groups["group:alcohol"].strip()


@pytest.mark.parametrize("excluded", [["group:alcohol"]])
def test_a_declared_group_survives_alignment_with_the_products_vocabulary(excluded):
    vocabulary = ConstraintVocabulary(ingredients=frozenset({"pork"}), groups=catalog_groups())

    aligned = align_to_vocabulary(AgentConstraintExtraction(excluded_ingredients=excluded), vocabulary)

    assert aligned.excluded_ingredients == excluded
    assert aligned.unmatched_terms == []
