"""One dish a plan must hold: found by name, planned in its role, and, when it alone stands in the way of a week,
offered verified ways out (owner, 2026-11-09)."""

import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.agent import limits
from app.agent.parser import RuleBasedConstraintParser, read_meal_kcal, read_required_dish
from app.agent.required_dish import Replacement, resolve, similar
from app.core import clock
from app.orchestration.interactions import say_interaction
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.planning.meal_beam import meal_permitted
from app.planning.product_path import ProductPlanningError
from app.planning.week_floor import week_floor
from app.schemas.agent import AgentConstraintState, DishAsked, OfferedChange
from app.schemas.household_rules import HouseholdPlanning, PresenceRule
from app.schemas.meal_plan import (
    MEAL_PRESETS,
    STRUCTURED_PRESETS,
    MealPlanShape,
    RequiredDish,
    WeeklyMealPlanRequest,
)
from app.services.replanning import MealPlanReplanningService
from tests.test_agent_limits_and_language import labels, plans, priced, tap
from tests.test_planning_capability import _dish, dish_client

DINNER = {"meals": {"dinner": MEAL_PRESETS["dinner"]["main and vegetable"]}}
CURRY = RequiredDish(
    recipe_slug="luxury-curry", title="Luxury Curry", meal="dinner", role_id="main", weekday="friday", kcal=900
)
SWAP = CURRY.model_copy(update={"recipe_slug": "salmon-curry", "title": "Salmon Curry", "kcal": 500})


@pytest.mark.parametrize(
    ("message", "name", "weekday", "meal"),
    [
        ("Chicken curry on Friday dinner", "chicken curry", "friday", "dinner"),
        ("A week for 2, and I want a Chicken Curry for dinner on Friday please", "chicken curry", "friday", "dinner"),
        ("Friday's dinner must be laksa", "laksa", "friday", "dinner"),
        ("We must have shrimp and scallop curry for dinner.", "shrimp and scallop curry", None, "dinner"),
        ("4 people and chicken and rice on Monday", "chicken and rice", "monday", None),
        ("周五晚餐要吃咖喱鸡，预算100", "咖喱鸡", "friday", "dinner"),
        ("一定要有蛋炒饭", "蛋炒饭", None, None),
    ],
)
def test_a_named_dish_is_read_with_its_day_and_meal(message, name, weekday, meal):
    asked = read_required_dish(message)
    assert (asked.name, asked.weekday, asked.meal) == (name, weekday, meal)


@pytest.mark.parametrize(
    "message",
    [
        "Skip lunch on Friday",
        "something quick on Monday",
        "S$40 for Friday dinner",
        "no pork on Friday dinner",
        "周五晚餐不要鱼",
        "plan a week for 2",
        "Five people want spicy dinners on Friday.",
        "五个人，周五晚餐想吃辣的。",
        "2 people. Friday dinner should be simple.",
        "Friday's dinner is quick",
        "Make it spicy on Friday",
        "vegetarian on Friday",
        "only cook on Friday",
        "周六晚餐要简单一点",
    ],
)
def test_a_message_that_names_no_dish_pins_nothing(message):
    assert read_required_dish(message) is None


@pytest.mark.parametrize(
    ("message", "ceiling"),
    [
        ("each meal under 650 kcal", 650),
        ("700 calories per meal", 700),
        ("每餐不超过650千卡", 650),
        ("at least 400 kcal each meal", None),
        ("2000 kcal a day", None),
        ("no more than 650 calories per meal", 650),
        ("each meal not more than 650 kcal", 650),
        ("eat more than 400 kcal per meal", None),
        ("每餐目标550千卡", None),
        ("budget about 60, each meal under 650 kcal", 650),
    ],
)
def test_only_a_ceiling_on_every_meal_is_read_as_one(message, ceiling):
    assert read_meal_kcal(message.lower()) == ceiling


def test_a_meal_ceiling_is_no_calorie_target_to_aim_at():
    extraction = RuleBasedConstraintParser().parse(
        "Each meal under 650 kcal", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    assert extraction.max_kcal_per_meal == 650
    assert extraction.nutrition_targets is None or extraction.nutrition_targets.calories_kcal is None


def read(message: str):
    return RuleBasedConstraintParser().parse(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )


@pytest.mark.parametrize(
    ("message", "kcal"), [("两个人，每餐目标550千卡。", 550), ("六个人，每餐目标600卡路里。", 600)]
)
def test_a_target_for_each_meal_stays_a_target(message, kcal):
    extraction = read(message)
    assert extraction.max_kcal_per_meal is None and extraction.nutrition_targets.calories_kcal == kcal


def test_a_daily_target_stays_beside_a_meal_ceiling():
    extraction = read("1800 kcal a day, each meal under 650 kcal")
    assert extraction.max_kcal_per_meal == 650 and extraction.nutrition_targets.calories_kcal == 1800


def test_no_more_than_is_the_meal_ceiling_and_no_daily_target():
    extraction = read("no more than 650 calories per meal")
    assert extraction.max_kcal_per_meal == 650
    assert extraction.nutrition_targets is None or extraction.nutrition_targets.calories_kcal is None


def test_a_chinese_calorie_ceiling_is_no_money():
    extraction = read("每餐不超过650千卡")
    assert extraction.max_kcal_per_meal == 650 and extraction.budget_per_meal_sgd is None
    assert read("每餐不超过15").budget_per_meal_sgd == 15


def catalog() -> list:
    luxury, salmon = (
        _dish("luxury-curry", "main", "salmon_fillet", 6000, calories=900),
        _dish("salmon-curry", "main", "salmon_trout", 400, calories=500),
    )
    salmon.recipe_ingredients[0].ingredient = luxury.recipe_ingredients[0].ingredient  # the most alike by what they use
    return [
        luxury,
        salmon,
        _dish("chicken-roast", "main", "chicken_breast", 400, calories=450),
        _dish("tofu-bake", "main", "firm_tofu", 500, calories=350),
        _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
        _dish("spinach-saute", "side", "baby_spinach", 200, calories=80),
    ]


@pytest.fixture
def client(monkeypatch):
    with dish_client(monkeypatch, catalog()) as test_client:
        yield test_client


def start(client, message: str) -> dict:
    return client.post("/api/agent/sessions", json={"message": message}).json()


def said(session: dict) -> str:
    return session["messages"][-1]["content"]


def test_a_named_dish_is_in_the_planned_week_on_its_day_and_in_its_role(client):
    session = start(client, "A week of dinners for 2 people. Chicken Roast on Friday dinner.")
    assert session["status"] == "ready", said(session)
    assert session["constraints"]["required_dish"]["recipe_slug"] == "chicken-roast"
    assert "Chicken Roast is in this plan for Friday dinner." in said(session)

    plan = plans(client, session)

    friday = [day for day in plan["days"] if date.fromisoformat(day["planned_date"]).strftime("%A") == "Friday"]
    assert {(day["recipe"]["slug"], day["role_id"]) for day in friday} >= {("chicken-roast", "main")}


def test_a_dish_no_recipe_names_is_asked_about_not_guessed(client):
    session = start(client, "Dinners for 2 people. Beef Bourguignon on Friday dinner.")
    assert session["status"] == "collecting" and "couldn't find Beef Bourguignon".lower() in said(session).lower()
    assert session["constraints"].get("required_dish") is None


def test_a_name_several_dishes_hold_asks_which_and_the_tap_pins_it(client):
    session = start(client, "Dinners for 2 people. Curry on Friday dinner.")
    assert session["status"] == "collecting" and "Which curry" in said(session), said(session)
    assert set(labels(session)) == {"Luxury Curry", "Salmon Curry"}

    ready = tap(client, session, "Salmon Curry")

    assert ready["constraints"]["required_dish"]["recipe_slug"] == "salmon-curry"


def test_a_dish_that_breaks_a_limit_that_keeps_someone_safe_is_never_pinned(client):
    session = start(client, "Dinners for 2 people, no chicken. Chicken Roast on Friday dinner.")
    assert session["status"] == "collecting", said(session)
    assert said(session).startswith("I can't plan Chicken Roast: it has an ingredient you excluded."), said(session)
    assert session["constraints"].get("required_dish") is None


def test_fresh_food_named_past_its_days_offers_the_latest_day_it_fits():
    recipe = _dish("fresh-curry", "main", "prawn", 400, calories=500)
    recipe.meal_role, recipe.protein_sources = "protein_main", ["seafood"]
    recipe.recipe_ingredients[0].ingredient.perishable = True
    request = WeeklyMealPlanRequest(
        household_size=2,
        start_date=date(2026, 11, 9),
        plan_shape=MealPlanShape.model_validate(
            {"meals": {"dinner": STRUCTURED_PRESETS["dinner"]["Main, vegetable and staple"]}}
        ),
    )
    asked = DishAsked(name="fresh curry", weekday="friday", meal="dinner")

    refused = resolve(asked, request, [recipe], [], lambda _: [], "en")

    assert isinstance(refused, limits.Refusal) and "Friday is too late" in refused.text
    assert refused.options == (("Have it on Wednesday", "Have it on Wednesday"),)
    assert refused.changes[0].required_dish.weekday == "wednesday"


def test_a_meal_the_plan_lacks_is_said_so_not_called_a_missing_dish(client):
    session = start(client, "Dinners for 2 people. Chicken Roast for lunch on Friday.")
    assert session["status"] == "collecting" and said(session) == "This plan doesn't include lunch."


def message(client, session: dict, text: str) -> dict:
    return client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": text}).json()


def test_a_dish_the_plan_no_longer_has_a_day_for_leaves_it_and_says_so(client):
    day = (clock.now() + timedelta(days=3)).strftime("%A")
    session = start(client, f"A week of dinners for 2 people. Chicken Roast on {day} dinner.")
    assert session["status"] == "ready", said(session)

    after = message(client, session, "Actually just plan tomorrow's dinner")

    assert after["status"] == "ready", said(after)
    assert f"This plan doesn't include {day}. Chicken Roast is no longer in this plan." in said(after)
    assert after["constraints"].get("required_dish") is None


def test_an_exclusion_said_after_the_dish_leaves_it_and_says_why(client):
    session = start(client, "A week of dinners for 2 people. Chicken Roast on Friday dinner.")

    after = message(client, session, "no chicken")

    assert after["status"] == "ready", said(after)
    assert "I can't plan Chicken Roast: it has an ingredient you excluded." in said(after)
    assert "Chicken Roast is no longer in this plan." in said(after)
    assert after["constraints"].get("required_dish") is None


def test_a_shape_with_no_role_for_the_dish_leaves_it_and_says_so(client):
    session = start(client, "A week of dinners for 2 people. Broccoli Stirfry on Friday dinner.")
    assert session["constraints"]["required_dish"]["role_id"] != "main"

    after = message(client, session, "just a main for dinner")

    assert after["status"] == "ready", said(after)
    assert "This plan has no place for Broccoli Stirfry." in said(after)
    assert after["constraints"].get("required_dish") is None


def test_a_dish_still_in_the_plan_stays_through_a_later_message(client):
    session = start(client, "A week of dinners for 2 people. Chicken Roast on Friday dinner.")

    after = message(client, session, "under 60 minutes")

    assert after["status"] == "ready", said(after)
    assert after["constraints"]["required_dish"]["recipe_slug"] == "chicken-roast"


def similar_case(household=None):
    recipes = catalog()
    cost = {"luxury-curry": 12.0, "salmon-curry": 6.0}
    ranked = [
        SimpleNamespace(recipe=recipe, grocery_estimate=SimpleNamespace(consumed_total_sgd=cost[recipe.slug]))
        for recipe in recipes
        if recipe.slug in cost
    ]
    request = WeeklyMealPlanRequest(
        household_size=4,
        start_date=date(2026, 11, 9),
        plan_shape=MealPlanShape.model_validate(DINNER),
        household=household,
    )
    return request, recipes, ranked


@pytest.mark.parametrize("stale", [{"meal": "lunch"}, {"role_id": "soup"}])
def test_a_pin_the_shape_has_lost_has_no_replacements(stale):
    request, recipes, ranked = similar_case()
    assert similar(CURRY.model_copy(update=stale), request, recipes, ranked) == []


def test_money_saved_is_for_who_is_home_at_the_pinned_meal():
    away = {"source_text": "x", "restatement": "x", "present": False, "weekdays": ["friday"], "meal_types": ["dinner"]}
    household = HouseholdPlanning(
        members=[{"name": name, "servings": 1} for name in "ABCD"],
        presence_rules=[PresenceRule.model_validate({**away, "member_name": name}) for name in "CD"],
    )

    everyone = similar(CURRY, *similar_case())
    two_home = similar(CURRY, *similar_case(household))

    assert everyone[0].saved_sgd == 6.0 and two_home[0].saved_sgd == 3.0


def budget_conflict(client) -> dict:
    session = start(client, "A week of dinners for 2 people, S$60 total. Luxury Curry on Friday dinner.")
    assert session["status"] == "collecting" and "Luxury Curry" in said(session), said(session)
    return session


def test_a_pinned_dish_over_the_budget_is_refused_with_its_real_costs_and_verified_ways_out(client):
    session = budget_conflict(client)
    reply = said(session)

    assert re.search(r"With Luxury Curry at Friday dinner, the cheapest plan I found costs S\$\d+\.\d\d, over", reply)
    assert re.search(r"Salmon Curry is the closest dish that fits\.", reply), reply
    assert re.search(r"S\$\d+\.\d\d cheaper to cook and 400 kcal lighter a serving", reply), reply
    assert labels(session)[0] == "Use Salmon Curry instead"
    assert re.fullmatch(r"Use S\$\d+ for the week", labels(session)[-1]), labels(session)
    assert len(labels(session)) <= 3


def test_tapping_the_replacement_plans_exactly_it_and_leaves_the_household_alone(client):
    session = budget_conflict(client)
    saved = client.get("/api/household-profiles/current").json()

    ready = tap(client, session, "Use Salmon Curry instead")

    assert ready["status"] == "ready" and ready["can_confirm"], said(ready)
    assert ready["constraints"]["required_dish"]["recipe_slug"] == "salmon-curry"
    assert ready["pending_interaction"] is None
    plan = plans(client, ready)
    assert plan["grocery_estimate"]["purchase_total_sgd"] <= 60
    assert "salmon-curry" in {day["recipe"]["slug"] for day in plan["days"]}
    assert "luxury-curry" not in {day["recipe"]["slug"] for day in plan["days"]}
    assert client.get("/api/household-profiles/current").json() == saved


def test_tapping_the_verified_budget_keeps_the_dish_and_plans_within_it(client):
    session = budget_conflict(client)
    amount = int(re.search(r"Use S\$(\d+)", labels(session)[-1]).group(1))

    ready = tap(client, session, labels(session)[-1])

    assert ready["status"] == "ready", said(ready)
    assert ready["constraints"]["weekly_budget_sgd"] == amount
    plan = plans(client, ready)
    assert plan["grocery_estimate"]["purchase_total_sgd"] <= amount
    assert "luxury-curry" in {day["recipe"]["slug"] for day in plan["days"]}


def test_a_calorie_conflict_is_never_offered_money(client):
    session = start(client, "A week of dinners for 2 people. Luxury Curry on Friday dinner. Each meal under 700 kcal.")
    reply = said(session)

    assert session["status"] == "collecting"
    assert reply.startswith("Luxury Curry is 900 kcal a serving. With the rest of the meal, I found no dinner with it")
    assert not any(label.startswith("Use S$") for label in labels(session))
    assert labels(session) == ["Use Salmon Curry instead"], reply

    ready = tap(client, session, "Use Salmon Curry instead")

    assert ready["status"] == "ready" and ready["constraints"]["max_kcal_per_meal"] == 700
    assert "salmon-curry" in {day["recipe"]["slug"] for day in plans(client, ready)["days"]}


def conflict(lang="en", *, passing=(), weekly=60, ceiling=None, swaps=(SWAP,)):
    """`limits.refusal` over a stubbed planner: only the changes named in `passing` give a real week."""

    def check(**changes):
        passes = "pin_free" in passing and changes.get("required_dish", CURRY) is None
        passes = passes or ("swap" in passing and changes.get("required_dish") == SWAP)
        passes = passes or ("drop" in passing and "plan_shape" in changes)
        passes = passes or ("no_limit" in passing and "nutrition_constraints" in changes)
        passes = passes or ("no_budget" in passing and "weekly_budget_sgd" in changes)
        return None if passes else ProductPlanningError("candidate_rejected", "No week.", {})

    def cheapest(**changes):
        return 41.0 if "plan_shape" in changes else 72.4

    floor = SimpleNamespace(empty_roles=[], uncovered=[], roles={}, meal_sgd={}, total_sgd=1.0)
    constraints = AgentConstraintState(
        required_dish=CURRY,
        weekly_budget_sgd=weekly,
        max_kcal_per_meal=ceiling,
        plan_shape=MealPlanShape.model_validate(
            {"meals": {"dinner": MEAL_PRESETS["dinner"]["main, vegetable and soup"]}}
        ),
        household_size=2,
    )
    return limits.refusal(
        constraints,
        lambda **changes: floor,
        lang,
        check=check,
        cheapest=cheapest,
        replacements=lambda pin: [Replacement(item, 12.5, 400.0) for item in swaps],
    )


def test_every_qualifying_way_out_is_offered_together_and_no_other():
    refused = conflict(passing={"pin_free", "no_budget", "swap", "drop"})

    assert [label for label, _ in refused.options] == [
        "Use Salmon Curry instead",
        "Drop the vegetable dish at dinner",
        "Use S$73 for the week",
    ]
    assert refused.field == "weekly_budget_sgd"
    assert refused.changes == (
        OfferedChange(value="Use Salmon Curry instead of Luxury Curry", required_dish=SWAP),
        OfferedChange(value="Make the weekly budget S$73", weekly_budget_sgd=73),
    )
    assert "S$12.50 cheaper to cook and 400 kcal lighter a serving" in refused.text


def test_none_qualifies_says_what_binds_and_offers_nothing():
    refused = conflict(passing={"pin_free"}, swaps=())

    assert refused.options == () and "Luxury Curry" in refused.text and "S$" in refused.text
    assert "2 people" not in refused.text and "240" not in refused.text


def test_a_conflict_a_week_without_the_dish_shares_is_not_the_dishs_to_answer():
    assert conflict(passing=set(), weekly=None) is None


def test_the_replies_have_chinese_wording():
    refused = conflict("zh", passing={"pin_free", "no_budget", "swap"})

    assert refused.text.startswith("周五晚餐吃 Luxury Curry 的话"), refused.text
    assert refused.options[0] == ("Use Salmon Curry instead", "用 Salmon Curry 代替 Luxury Curry")


class NoModel:
    provider = "stub"

    def parse(self, *args, **kwargs):
        raise AssertionError("the tapped option went to the parser")

    def classify(self, *args, **kwargs):
        raise AssertionError("the tapped option went to the scope classifier")


def test_a_tapped_replacement_asks_no_model():
    sentence = "Use Salmon Curry instead of Luxury Curry"
    current = AgentConstraintState(
        household_size=2,
        weekly_budget_sgd=60,
        required_dish=CURRY,
        offered_changes=[OfferedChange(value=sentence, required_dish=SWAP)],
    )
    outcome = BoundedAgentOrchestrator(NoModel(), scope_classifier=NoModel(), check=lambda *_: None).process(
        sentence,
        current=current,
        acknowledged_unknowns=[],
        history=[],
        current_status="collecting",
        current_missing_fields=["weekly_budget_sgd"],
        current_questions=["No week."],
        context_version=2,
        pending_interaction=say_interaction(
            options=[("Use Salmon Curry instead", sentence)], question_id="q", context_version=2, lang="en"
        ),
    )

    assert outcome.status == "ready" and outcome.constraints.required_dish == SWAP
    assert outcome.constraints.offered_changes == []
    assert outcome.constraints.weekly_budget_sgd == 60
    assert outcome.assistant_message.startswith("Salmon Curry is in this plan for Friday dinner.")


def test_the_floor_holds_one_day_of_the_pinned_dish():
    cheap, dear = priced(1, 2.0), priced(2, 30.0)
    cheap.recipe.slug, dear.recipe.slug = "cheap", "luxury-curry"
    recipes = [SimpleNamespace(id=1, course="main"), SimpleNamespace(id=2, course="main")]
    request = WeeklyMealPlanRequest(
        household_size=2, plan_shape=MealPlanShape.model_validate(DINNER), day_count=7, start_date=date(2026, 11, 9)
    )

    free = week_floor(request, [cheap, dear], recipes)
    pinned = week_floor(request.model_copy(update={"required_dish": CURRY}), [cheap, dear], recipes)

    assert pinned.total_sgd > free.total_sgd
    # Six days at the cheapest dish and one at the curry, at the smallest share a meal gives its main: no more.
    assert pinned.total_sgd == pytest.approx(free.total_sgd + (30.0 - 2.0) * pinned.total_sgd / (6 * 2.0 + 30.0))


def test_the_search_holds_a_meal_of_one_dish_to_the_per_meal_ceiling():
    band = SimpleNamespace(hard=True, scope="per_slot", metric="calories_kcal", lower=None, upper=500.0)
    recipe = SimpleNamespace(nutrients_per_serving=SimpleNamespace(calories_kcal=900.0), meal_role=None)
    problem = SimpleNamespace(nutrition_bands=[band], diversity_policy=None, composition_policy=None, slots=[])
    slot = SimpleNamespace(composition=[object()], members=[], max_time_minutes=None, meal_type="dinner")

    assert not meal_permitted(problem, slot, (("main", "heavy"),), {"heavy": recipe}, {"main": 1})


def test_a_change_to_a_saved_week_is_free_to_swap_the_dish():
    request = WeeklyMealPlanRequest(
        household_size=2, plan_shape=MealPlanShape.model_validate(DINNER), required_dish=CURRY
    )
    saved = SimpleNamespace(constraints=request.model_dump(mode="json"))
    service = SimpleNamespace(live_feedback=False)

    assert MealPlanReplanningService._constraints(service, saved).required_dish is None


def test_asking_for_a_store_s_prices_turns_on_live_prices_for_any_parser():
    from app.agent.parser import apply_rule_dish
    from app.schemas.agent import AgentConstraintExtraction

    asked = AgentConstraintExtraction()
    apply_rule_dish(asked, "Two of us, about S$150, using FairPrice prices.")
    assert asked.pricing_mode == "live"
    echoed = AgentConstraintExtraction(pricing_mode="fixture")
    apply_rule_dish(echoed, "Use FairPrice prices.")
    assert echoed.pricing_mode == "live"
    plain = AgentConstraintExtraction()
    apply_rule_dish(plain, "Two of us, about S$150.")
    assert plain.pricing_mode is None
