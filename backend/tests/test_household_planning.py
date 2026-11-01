"""What the household block does to a planned week (layer 08 PR-1): who is home, cooking-time rules, basics
at home and the sodium limit, on the repository catalog. Without the block a request plans exactly as before."""

import json
from collections import Counter
from datetime import date, timedelta

import pytest

from app.core.paths import repository_root
from app.data.catalog import import_catalog, load_catalog
from app.data.household_reference import basic_seasonings, basic_short_labels
from app.models.recipe import Recipe
from app.planning.household_slots import assumed_basics, limit_targets, slot_servings, slot_time_limit
from app.schemas.household_rules import CookingTimeRule, HouseholdPlanning, PresenceRule
from app.schemas.meal_plan import WeeklyMealPlanRequest
from tests.test_planning_product_path import database, latest_trace
from tests.test_recipes import recipe_client as recipe_client

START = "2027-01-03"  # a Sunday
ONE_MAIN = [{"role_id": "main", "courses": ["main"]}]
LUNCH_AND_DINNER = {"meals": {"lunch": ONE_MAIN, "dinner": ONE_MAIN}}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
# The curated catalog's own ingredients that the owner's list (2026-10-29) assumes at home.
BASICS_IN_CATALOG = {"garlic", "ginger", "soy_sauce", "sesame_oil", "brown_rice"}


def catalog_recipes() -> dict[str, dict]:
    recipes = json.loads((repository_root() / "data/recipes/recipes.json").read_text(encoding="utf-8"))
    return {recipe["slug"]: recipe for recipe in recipes}


@pytest.fixture
def catalog_client(recipe_client):
    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    with database() as session:
        import_catalog(session, catalog)
    return recipe_client


def rule(member, present, weekdays=(), meals=()):
    return {
        "source_text": "x",
        "restatement": "x",
        "member_name": member,
        "present": present,
        "weekdays": list(weekdays),
        "meal_types": list(meals),
    }


def plan(client, **request):
    body = {"start_date": START, "household_size": 2, "pricing_mode": "fixture", "plan_shape": LUNCH_AND_DINNER}
    response = client.post("/api/plans/generate", json={"requires_halal": False, **{**body, **request}})
    assert response.status_code == 201, response.text
    return response.json()


def weekday(day) -> str:
    return date.fromisoformat(day["planned_date"]).strftime("%A").lower()


def ingredients_of(client, slug) -> set[str]:
    return {item["normalized_name"] for item in client.get(f"/api/recipes/{slug}").json()["ingredients"]}


def basics_of(client, days) -> set[str]:
    return {name for d in days for name in ingredients_of(client, d["recipe"]["slug"])} & BASICS_IN_CATALOG


def test_who_is_home_sets_each_meals_servings_and_a_meal_nobody_eats_is_not_planned(catalog_client):
    household = {
        "members": [
            {"name": "Ann", "servings": 1},
            {"name": "Mei", "servings": 0.73},
            {"name": "Grandma", "servings": 0.89, "default_present": False},
        ],
        "presence_rules": [
            rule("Mei", False, WEEKDAYS, ["lunch"]),
            rule("Grandma", True, ["saturday", "sunday"], ["dinner"]),
            rule("Ann", False, ["wednesday"], ["lunch"]),
        ],
    }
    week = plan(catalog_client, household=household)
    servings = {(weekday(d), d["meal_type"]): d["servings"] for d in week["days"]}
    assert servings[("monday", "lunch")] == 1
    assert servings[("monday", "dinner")] == 1.73
    assert servings[("sunday", "lunch")] == 1.73
    assert servings[("saturday", "dinner")] == servings[("sunday", "dinner")] == 2.62
    # Wednesday lunch: Ann is out and Mei is at school.
    assert ("wednesday", "lunch") not in servings
    assert len(week["days"]) == 13
    assert "Wednesday lunch is not planned: nobody is home." in week["warnings"]
    assert week["end_date"] == "2027-01-09"
    assert all(d["portion_share"] == 1 for d in week["days"])
    # Each dish costs what its servings use of the household-size estimate (2 servings here).
    _, trace = latest_trace()
    assert trace["unattended_slots"] == ["Wednesday lunch is not planned: nobody is home."]
    with database() as session:
        from app.models.meal_plan import MealPlanEntry

        stored = {row.id: row for row in session.query(MealPlanEntry).all()}
    assert {float(stored[d["entry_id"]].servings) for d in week["days"]} == {1, 1.73, 2.62}


def test_the_grocery_list_buys_for_the_servings_present(catalog_client):
    shape = {"meals": {"dinner": ONE_MAIN}}
    both = {"members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}]}
    alone = {**both, "presence_rules": [rule("Ben", False)]}
    full = plan(catalog_client, plan_shape=shape, household=both, max_uses_per_recipe=1)
    half = plan(catalog_client, plan_shape=shape, household=alone, max_uses_per_recipe=1)
    assert {d["servings"] for d in half["days"]} == {1}
    if [d["recipe"]["slug"] for d in full["days"]] == [d["recipe"]["slug"] for d in half["days"]]:
        needed = {(i["ingredient_name"], i["unit"]): i["required_quantity"] for i in full["grocery_estimate"]["items"]}
        for item in half["grocery_estimate"]["items"]:
            assert item["required_quantity"] == pytest.approx(needed[item["ingredient_name"], item["unit"]] / 2)
    for d in half["days"]:
        assert d["purchase_cost_sgd"] <= max(f["purchase_cost_sgd"] for f in full["days"])


def test_a_weekday_dinner_rule_keeps_long_dishes_to_the_weekend(catalog_client):
    recipes = catalog_recipes()
    household = {
        "members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}],
        "cooking_time_rules": [
            {"source_text": "x", "restatement": "x", "weekdays": WEEKDAYS, "meal_types": ["dinner"], "max_minutes": 30}
        ],
    }
    week = plan(
        catalog_client, plan_shape={"meals": {"dinner": ONE_MAIN}}, max_cooking_time_minutes=60, household=household
    )
    minutes = {weekday(d): d["recipe"]["total_time_minutes"] for d in week["days"]}
    assert all(minutes[day] <= 30 for day in WEEKDAYS)
    assert all(minutes[day] <= 60 for day in ("saturday", "sunday"))
    assert any(recipes[slug]["prep_time_minutes"] + recipes[slug]["cook_time_minutes"] > 30 for slug in recipes)


def test_basics_leave_the_list_unless_the_household_has_run_out(catalog_client):
    household = {"members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}]}
    week = plan(catalog_client, household=household)
    listed = {item["ingredient_name"] for item in week["grocery_estimate"]["items"]}
    used = basics_of(catalog_client, week["days"])
    assert used, "the week should use a basic seasoning"
    assert not listed & BASICS_IN_CATALOG
    note = next(w for w in week["warnings"] if w.startswith("Pantry basics are assumed at home"))
    # Categories and counts, not every name.
    counts = Counter(basic_seasonings()[name]["category"] for name in used)
    assert note == (
        "Pantry basics are assumed at home and left off this list: "
        + ", ".join(f"{noun} ({counts[key]})" for key, noun in basic_short_labels().items() if key in counts)
        + ". Mark one as run out on your profile to buy it."
    )
    assert not any(name.replace("_", " ") in note for name in used)

    bought = plan(catalog_client, household={**household, "missing_basics": sorted(BASICS_IN_CATALOG)})
    listed = {item["ingredient_name"] for item in bought["grocery_estimate"]["items"]}
    assert basics_of(catalog_client, bought["days"]) <= listed
    assert not any(w.startswith("Pantry basics are assumed") for w in bought["warnings"])

    plain = plan(catalog_client)
    assert basics_of(catalog_client, plain["days"]) <= {
        item["ingredient_name"] for item in plain["grocery_estimate"]["items"]
    }


def test_rice_and_ketchup_are_at_home_until_the_household_marks_them_run_out():
    planning = HouseholdPlanning(members=[{"name": "Ann", "servings": 1}])
    out = HouseholdPlanning(members=[{"name": "Ann", "servings": 1}], missing_basics=["rice", "ketchup"])
    at_home = {"rice", "brown_rice", "ketchup", "mustard", "cumin", "flour", "rice_vinegar", "thyme", "bouillon"}
    assert at_home <= assumed_basics(planning, [])
    assert {"rice", "ketchup"}.isdisjoint(assumed_basics(out, []))
    assert {"brown_rice", "mustard", "cumin", "flour"} <= assumed_basics(out, [])
    # A member who excludes one still buys it knowingly, and cooking sauces, tomato products and fresh herbs
    # are shopping as before.
    assert "ketchup" not in assumed_basics(planning, ["ketchup"])
    assert {"curry_paste", "marinara", "tomato_paste", "coconut_milk", "basil", "olive_oil"}.isdisjoint(
        assumed_basics(planning, [])
    )


def test_rice_leaves_the_list_and_comes_back_when_marked_run_out(catalog_client):
    household = {"members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}]}
    week = plan(catalog_client, household=household)
    assert "brown_rice" in {name for d in week["days"] for name in ingredients_of(catalog_client, d["recipe"]["slug"])}
    assert "brown_rice" not in {item["ingredient_name"] for item in week["grocery_estimate"]["items"]}
    bought = plan(catalog_client, household={**household, "missing_basics": ["rice", "brown_rice"]})
    assert "brown_rice" in {item["ingredient_name"] for item in bought["grocery_estimate"]["items"]}


@pytest.fixture
def plain_rice_client(recipe_client):
    """A catalog of one dish, plain brown rice, which the owner's list makes a dish of at-home items alone."""
    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    rice = next(r for r in catalog.recipes if r.slug == "vegetable-rice-skillet").model_copy(
        update={"slug": "plain-brown-rice", "title": "Plain Brown Rice"}
    )
    rice.ingredients = [i for i in rice.ingredients if i.ingredient == "brown_rice"]
    with database() as session:
        for seeded in session.query(Recipe).all():
            session.delete(seeded)
        session.flush()
        import_catalog(session, catalog.model_copy(update={"recipes": [rice]}))
    return recipe_client


def test_a_plain_rice_staple_buys_nothing_unless_rice_has_run_out(plain_rice_client):
    shape = {"meals": {"dinner": ONE_MAIN}}
    household = {"members": [{"name": "Ann", "servings": 1}]}
    week = plan(plain_rice_client, plan_shape=shape, day_count=1, household=household)
    assert [d["recipe"]["slug"] for d in week["days"]] == ["plain-brown-rice"]
    assert week["grocery_estimate"]["items"] == [] and week["grocery_estimate"]["complete"]
    assert any(w.startswith("Pantry basics are assumed at home") and "rice (1)" in w for w in week["warnings"])
    assert week["grocery_estimate"]["purchase_total_sgd"] == 0
    assert week["days"][0]["purchase_cost_sgd"] == 0
    bought = plan(
        plain_rice_client, plan_shape=shape, day_count=1, household={**household, "missing_basics": ["brown_rice"]}
    )
    assert {item["ingredient_name"] for item in bought["grocery_estimate"]["items"]} == {"brown_rice"}
    assert bought["grocery_estimate"]["purchase_total_sgd"] > 0


@pytest.fixture
def rice_heavy_client(recipe_client):
    """A catalog of two dishes: a curry, and brown rice (300 g, an at-home item) with 480 g of vegetables, which is
    half vegetables only once the rice line is left out."""
    root = repository_root()
    catalog = load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
    by_slug = {r.slug: r for r in catalog.recipes}
    dish = by_slug["vegetable-rice-skillet"].model_copy(
        update={"slug": "rice-with-vegetables", "title": "Rice With Vegetables"}
    )
    grams = {"brown_rice": 300, "zucchini": 200, "mushroom": 180, "baby_spinach": 100}
    dish.ingredients = [
        i.model_copy(update={"quantity": grams[i.ingredient], "unit": "g"})
        for i in dish.ingredients
        if i.ingredient in grams
    ]
    with database() as session:
        for seeded in session.query(Recipe).all():
            session.delete(seeded)
        session.flush()
        import_catalog(session, catalog.model_copy(update={"recipes": [by_slug["chickpea-sweet-potato-curry"], dish]}))
    return recipe_client


def test_a_rice_dish_does_not_become_vegetable_led_when_rice_is_assumed_at_home(rice_heavy_client):
    """Review of the pantry change: the vegetable role reads the dish's real lines, not those left after the at-home
    items were stripped, so rice no longer drops out of the denominator."""
    two = [{"role_id": "main", "courses": ["main"]}, {"role_id": "vegetable", "courses": ["main"]}]
    household = {"members": [{"name": "Ann", "servings": 1}]}

    def generate(**extra):
        body = {"start_date": START, "household_size": 1, "pricing_mode": "fixture", "day_count": 1}
        body["plan_shape"] = {"meals": {"dinner": two}}
        return rice_heavy_client.post("/api/plans/generate", json={"requires_halal": False, **body, **extra})

    # Neither dish is a vegetable dish on its full lines, so no meal fills the vegetable role.
    assert generate().status_code == 422
    assert generate(household=household).status_code == 422
    assert generate(household={**household, "missing_basics": ["brown_rice"]}).status_code == 422


def test_a_dish_of_basics_keeps_its_vegetable_flag_from_the_full_lines():
    from app.planning.vegetable_led import candidate_vegetable_led
    from app.schemas.planning_v2 import PlanningRecipeCandidate

    lines = [("brown_rice", 300), ("zucchini", 200), ("mushroom", 180), ("baby_spinach", 100)]
    candidate = PlanningRecipeCandidate(
        recipe_id="x",
        title="X",
        servings=1,
        allowed_meal_types=["dinner"],
        total_time_minutes=10,
        ingredients=[dict(ingredient_id=n, quantity=g, unit="g") for n, g in lines[1:]],
        nutrients_per_serving=dict(calories_kcal=1, protein_g=1, carbohydrate_g=1, fat_g=1, sodium_mg=1, sugar_g=1),
    )
    assert candidate_vegetable_led(candidate)  # the stripped lines alone read as vegetable-led
    assert not candidate_vegetable_led(candidate.model_copy(update={"vegetable_led": False}))


def test_basics_stay_ingredients_for_every_safety_check(catalog_client):
    household = {"members": [{"name": "Ann", "servings": 1}, {"name": "Ben", "servings": 1}]}
    soy_free = plan(catalog_client, household=household, allergens=["soy"])
    for day in soy_free["days"]:
        assert not ingredients_of(catalog_client, day["recipe"]["slug"]) & {"soy_sauce", "firm_tofu"}
    no_garlic = plan(catalog_client, household=household, excluded_ingredients=["garlic"])
    for day in no_garlic["days"]:
        assert "garlic" not in ingredients_of(catalog_client, day["recipe"]["slug"])
    # An excluded basic is never assumed: its exclusion is matched against every recipe line.
    planning = HouseholdPlanning(members=[{"name": "Ann", "servings": 1}])
    assert "garlic" not in assumed_basics(planning, ["garlic"]) and "garlic" in assumed_basics(planning, [])
    assert assumed_basics(None, []) == frozenset()


def test_a_daily_sodium_limit_is_a_hard_band_shared_by_the_meals_planned(catalog_client):
    household = {
        "members": [{"name": "Ann", "servings": 1}],
        "nutrition_limits": [{"nutrient": "sodium_mg", "max_value": 1500}],
    }
    # Dinner alone has 35% of the day: 525 mg per person.
    week = plan(catalog_client, plan_shape={"meals": {"dinner": ONE_MAIN}}, household=household)
    assert all(d["nutrition_per_person"]["sodium_mg"] <= 525 for d in week["days"])
    assert "Sodium: at most 525 mg per person for each day." in week["warnings"]
    _, trace = latest_trace()
    assert trace["policy_version"] == "product-scoped-nutrition-v1"
    targets = limit_targets(HouseholdPlanning.model_validate(household), ["breakfast", "lunch", "dinner"])
    assert [(t.metric, t.scope, t.upper) for t in targets] == [("sodium_mg", "per_day", 1425.0)]


def test_without_a_household_block_a_request_plans_and_dumps_as_before(catalog_client):
    request = {"plan_shape": LUNCH_AND_DINNER, "weekly_budget_sgd": 120}
    first, second = plan(catalog_client, **request), plan(catalog_client, **request, household=None)

    def kept(week):
        return [(d["day_index"], d["meal_type"], d["recipe"]["slug"], d["servings"]) for d in week["days"]], [
            (i["ingredient_name"], i["required_quantity"]) for i in week["grocery_estimate"]["items"]
        ]

    assert kept(first) == kept(second)
    assert all(d["servings"] is None for d in first["days"])
    assert "household" not in WeeklyMealPlanRequest(household_size=2).model_dump()
    with database() as session:
        from app.models.meal_plan import MealPlan

        assert all("household" not in row.constraints for row in session.query(MealPlan).all())


def test_whole_portions_plan_slots_of_the_household_size():
    household = HouseholdPlanning(members=[{"name": "A", "servings": 1}, {"name": "B", "servings": 2}])
    servings = slot_servings(household, date(2027, 1, 4), "dinner")
    assert servings == 3 and isinstance(servings, int)
    later = household.model_copy(
        update={
            "presence_rules": [
                PresenceRule.model_validate(rule("B", False, ["monday"])),
                PresenceRule.model_validate(rule("B", True, ["monday"], ["dinner"])),
            ],
            "cooking_time_rules": [
                CookingTimeRule(source_text="x", restatement="x", weekdays=["saturday"], max_minutes=240),
            ],
        }
    )
    # The last rule for a member wins; a rule may loosen a meal's limit.
    assert slot_servings(later, date(2027, 1, 4), "dinner") == 3
    assert slot_servings(later, date(2027, 1, 4), "lunch") == 1
    assert slot_time_limit(later, 45, date(2027, 1, 9), "dinner") == 240
    assert slot_time_limit(later, 45, date(2027, 1, 4) + timedelta(days=1), "dinner") == 45


def test_a_swap_and_an_added_meal_keep_who_is_home(catalog_client):
    household = {
        "members": [{"name": "Ann", "servings": 1}, {"name": "Mei", "servings": 0.73}],
        "presence_rules": [rule("Mei", False, WEEKDAYS, ["dinner", "lunch"])],
    }
    week = plan(catalog_client, plan_shape={"meals": {"dinner": ONE_MAIN}}, household=household)
    monday = next(d for d in week["days"] if weekday(d) == "monday")
    assert monday["servings"] == 1
    preview = catalog_client.post(
        f"/api/plans/{week['id']}/replan/preview", json={"event_type": "REPLACE_MEAL", "entry_id": monday["entry_id"]}
    )
    assert preview.status_code == 201, preview.text
    confirmed = catalog_client.post(f"/api/plans/{week['id']}/replan/{preview.json()['id']}/confirm").json()
    swapped = next(d for d in confirmed["plan"]["days"] if d["entry_id"] == monday["entry_id"])
    assert swapped["recipe"]["slug"] != monday["recipe"]["slug"] and swapped["servings"] == 1

    added = catalog_client.post(
        f"/api/plans/{week['id']}/shape/preview", json={"meal_type": "lunch", "roles": ONE_MAIN}
    )
    assert added.status_code == 201, added.text
    after = catalog_client.post(f"/api/plans/{week['id']}/replan/{added.json()['id']}/confirm").json()["plan"]
    lunches = {weekday(d): d["servings"] for d in after["days"] if d["meal_type"] == "lunch"}
    assert lunches["monday"] == 1 and lunches["saturday"] == 1.73


def test_a_conversation_from_a_profile_carries_the_household_until_it_states_a_size():
    from types import SimpleNamespace

    from app.agent.workflow import AgentConstraintWorkflow
    from app.schemas.agent import AgentConstraintExtraction
    from app.services.agent import profile_constraints

    version = SimpleNamespace(
        planning_household_size=2,
        max_cooking_time_minutes=60,
        budget_per_meal_sgd=None,
        weekly_budget_sgd=None,
        allergens=[],
        excluded_ingredients=[],
        dietary_preferences=[],
        health_preferences=[],
        nutrition_targets={},
        max_sodium_mg_per_meal=None,
        available_ingredients=[],
        pricing_mode="fixture",
        plan_shape=None,
        meal_composition=None,
        members=[
            {"name": "Ann", "servings_per_meal": 1},
            {"name": "Mei", "servings_per_meal": None, "age_band": "child"},
        ],
        presence_rules=[rule("Mei", False, WEEKDAYS, ["lunch"])],
        cooking_time_rules=None,
        missing_basics=["salt"],
        nutrition_limits=[{"nutrient": "sodium_mg"}],
        requires_halal=False,
    )
    state = profile_constraints(version)
    assert [m.servings for m in state.household.members] == [1, 0.73]
    assert state.household.nutrition_limits[0].max_value == 2000  # Ann's HPB limit; HPB gives Mei none
    kept = AgentConstraintWorkflow._merge_constraints(state, AgentConstraintExtraction(weekly_budget_sgd=80))
    assert kept.household == state.household
    resized = AgentConstraintWorkflow._merge_constraints(state, AgentConstraintExtraction(household_size=4))
    assert resized.household.members is None and resized.household.presence_rules == []
    assert resized.household.missing_basics == ["salt"]
    assert (
        "household"
        not in AgentConstraintWorkflow._merge_constraints(
            state.model_copy(update={"household": None}), AgentConstraintExtraction(household_size=4)
        ).model_dump()
    )


def test_a_swap_keeps_the_daily_sodium_limit(catalog_client):
    household = {
        "members": [{"name": "Ann", "servings": 1}],
        "nutrition_limits": [{"nutrient": "sodium_mg", "max_value": 1500}],
    }
    week = plan(catalog_client, plan_shape={"meals": {"dinner": ONE_MAIN}}, household=household)
    for day in week["days"][:3]:
        preview = catalog_client.post(
            f"/api/plans/{week['id']}/replan/preview", json={"event_type": "REPLACE_MEAL", "entry_id": day["entry_id"]}
        )
        assert preview.status_code == 201, preview.text
        slug = preview.json()["after_entry"]["recipe_slug"]
        assert catalog_client.get(f"/api/recipes/{slug}").json()["nutrition"]["sodium_mg"] <= 525
