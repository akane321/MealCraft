"""Protocol v3-meal-day-week: drawn pools, proven labels, and the product path scored."""

import copy
import json

from app.core.paths import repository_root
from app.evaluation.meal_day_week_runner import evaluate, run_episode, scorer_catalogs, v3_checks
from app.evaluation.multidish_labels import check, slot_roles
from app.evaluation.multidish_pool import draw

EPISODES = repository_root() / "data/evaluation/dev/v3-meal-day-week/episodes"


def load(episode_id: str) -> dict:
    return json.loads((EPISODES / f"{episode_id}.json").read_text(encoding="utf-8"))


def test_the_committed_pools_are_the_drawn_ones_and_every_label_is_proven():
    paths = sorted(EPISODES.glob("*.json"))
    assert len(paths) >= 12
    for path in paths:
        episode = json.loads(path.read_text(encoding="utf-8"))
        slugs, products = draw(episode)
        assert episode["scenario"]["recipe_candidate_slugs"] == slugs, path.name
        assert episode["scenario"]["fairprice_product_ids"] == products, path.name
        assert check(episode) is None, (path.name, check(episode))


def test_a_shape_change_applies_to_its_days_and_meal_only():
    soup_on_friday = load("mdw-dev-015")
    before, after = slot_roles(soup_on_friday), slot_roles(soup_on_friday, after_change=True)
    assert list(before) == list(after) and len(after) == 7
    assert [r["role_id"] for r in after["fri-dinner"]] == ["main", "vegetable", "soup"]
    assert all(before[slot] == after[slot] for slot in after if slot != "fri-dinner")

    no_breakfast = slot_roles(load("mdw-dev-014"), after_change=True)
    assert list(no_breakfast) == [f"{day}-dinner" for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]


def test_a_label_names_the_slots_a_change_touches():
    episode = load("mdw-dev-015")
    episode["gold"]["replan_invariants"]["changed_slots"] = ["thu-dinner"]
    assert "changed_slots should be" in check(episode)


def test_the_product_adds_a_soup_to_one_dinner_and_keeps_the_rest():
    episode = load("mdw-dev-015")
    report = evaluate([episode])
    row = report["episodes"][0]
    assert row["strict_success"], row["details"]
    assert row["dishes"] == 15  # seven dinners of two dishes, Friday's with a soup

    # The v3 checks catch a week where another meal moved.
    response, extra = run_episode(episode)
    moved = copy.deepcopy(extra)
    moved["before"]["mon-dinner"] = {"main": "RCP2_NOT_THIS_ONE"}
    codes = {c.code: c.outcome for c in v3_checks(episode, response, moved, scorer_catalogs(episode))}
    assert codes == {"shape_request_understood": "passed", "unchanged_meals_identical": "failed"}


def test_a_daily_target_is_a_hard_day_band_and_a_soft_meal_guide():
    from app.planning.nutrition_scope import compile_nutrition_targets
    from app.schemas.planning_nutrition import ProductNutritionTarget

    target = ProductNutritionTarget(metric="calories_kcal", lower=900, upper=1500, scope="per_day")
    day, meal = compile_nutrition_targets([target], 0.25, meals_per_day=3)
    assert (day.scope, day.hard, day.lower, day.upper) == ("per_day", True, 900, 1500)
    assert (meal.scope, meal.hard, meal.lower, meal.upper) == ("per_slot", False, 225, 625)


def synthetic(episode_id: str, meals: dict, *, budget=None, bands=(), size=None) -> dict:
    """A developer episode of this shape and limit, its pool drawn and its label proven."""
    episode = copy.deepcopy(load("mdw-dev-008"))
    episode["episode_id"] = episode_id
    if size is not None:
        episode["scenario"]["household_profile"]["household_size"] = size
    episode["scenario"]["household_profile"]["plan_shape"] = {"meals": meals}
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    order = ("breakfast", "lunch", "dinner")
    episode["scenario"]["planning_horizon"]["slots"] = [f"{d}-{m}" for d in days for m in order if m in meals]
    hard = episode["gold"]["applicable_hard_constraints"]
    hard["budget_sgd"], hard["nutrition_bands"] = budget, list(bands)
    episode["scenario"]["recipe_candidate_slugs"], episode["scenario"]["fairprice_product_ids"] = draw(episode)
    assert check(episode) is None, check(episode)
    return episode


BREAKFAST = [{"role_id": "main", "courses": ["breakfast", "baked_good"], "required": True}]
LUNCH = [{"role_id": "main", "courses": ["main", "salad", "soup"], "required": True}]
DINNER = [
    {"role_id": "main", "courses": ["main"], "required": True},
    {"role_id": "vegetable", "courses": ["side", "salad"], "required": False},
]
DINNER_WITH_SOUP = [
    {"role_id": "main", "courses": ["main"], "required": True},
    {"role_id": "vegetable", "courses": ["side", "salad"], "required": True},
    {"role_id": "soup", "courses": ["soup"], "required": True},
]


def test_a_budget_the_search_prunes_to_nothing_is_planned_by_a_cost_led_search():
    """1.15 times the label's S$46.80 witness: the budget-pruned meal beam held no complete week."""
    episode = synthetic("syn-budget-003", {"breakfast": BREAKFAST, "dinner": DINNER_WITH_SOUP}, budget=53.82)
    row = evaluate([episode])["episodes"][0]
    assert row["strict_success"], row
    assert row["total_cost_sgd"] <= 53.82


def test_a_day_ceiling_the_search_prunes_to_nothing_is_planned_by_a_band_led_search():
    """At most 30 g of fat a day over three meals: every week the beam held broke a day's ceiling."""
    fat = {"metric": "fat_g", "scope": "per_day", "max": 30}
    episode = synthetic("syn-band-006", {"breakfast": BREAKFAST, "lunch": LUNCH, "dinner": DINNER}, bands=[fat])
    row = evaluate([episode])["episodes"][0]
    assert row["strict_success"], row


def test_a_budget_week_whose_cheap_meals_share_packages_is_planned():
    """mdw-dev-020: ranked by packages bought so far, a week built on shared packs looked dear on day one."""
    row = evaluate([load("mdw-dev-020")])["episodes"][0]
    assert row["strict_success"], row
    assert row["total_cost_sgd"] <= load("mdw-dev-020")["gold"]["applicable_hard_constraints"]["budget_sgd"]


def test_a_tight_budget_week_spends_its_room_on_variety():
    """S$2.50 a person a meal, the label's witness S$20.85: ranked by packages bought so far, the beam's
    cheap room kept the repeats (they buy nothing new) and the week left was 8 dishes of 21."""
    meals = {"breakfast": BREAKFAST, "lunch": LUNCH, "dinner": [DINNER[0]]}
    episode = synthetic("syn-var-007", meals, budget=210.0, size=4)
    row = evaluate([episode])["episodes"][0]
    assert row["strict_success"], row
    assert row["total_cost_sgd"] <= 210.0
    assert row["distinct_recipes"] >= 14, row


def test_a_tight_budget_week_fills_its_optional_dishes_when_they_fit():
    """S$105 for two, the label's witness S$48.56: charged nothing for an empty optional role, the cheap
    room preferred leaving twelve vegetables out to repeating one (ADR-0050: included if it fits)."""
    lunch = [DINNER[0], DINNER[1]]
    meals = {"breakfast": BREAKFAST, "lunch": lunch, "dinner": DINNER}
    episode = synthetic("syn-var-021", meals, budget=105.0, size=2)
    row = evaluate([episode])["episodes"][0]
    assert row["strict_success"], row
    assert row["total_cost_sgd"] <= 105.0
    assert row["dishes"] == 35, row


def test_a_no_repeats_week_keeps_enough_candidates_for_every_meal():
    """mdw-dev-021: eight candidates a role ran out before Sunday once no dish could come back."""
    row = evaluate([load("mdw-dev-021")])["episodes"][0]
    assert row["strict_success"], row
    assert row["dishes"] == row["distinct_recipes"]


def test_a_label_holds_an_unstated_time_limit_to_the_one_the_runner_sends():
    from app.evaluation.meal_day_week_runner import NO_TIME_LIMIT
    from app.evaluation.multidish_labels import valid_meals

    episode = load("mdw-dev-002")  # no stated limit; its pool holds a 360-minute noodle soup
    assert episode["gold"]["applicable_hard_constraints"]["max_cooking_time_minutes"] is None
    roles = [{"role_id": "main", "courses": ["soup"], "required": True}]

    def longest(meals):
        return max(r["prep_time_minutes"] + r["cook_time_minutes"] for meal in meals for _, r in meal)

    assert longest(valid_meals(episode, roles)) > NO_TIME_LIMIT  # protocol v2 reads no limit as none
    assert longest(valid_meals(episode, roles, "lunch")) <= NO_TIME_LIMIT


def test_a_label_never_uses_a_recipe_the_product_never_plans():
    from app.evaluation.multidish_labels import product_candidates, valid_meals

    episode = load("mdw-dev-020")
    lost_line = "RCP2_B12163C95EC7"  # "Tofu Stir Fry" with no tofu, 72 kcal: recipe_quality.incomplete
    assert lost_line not in product_candidates(tuple(episode["scenario"]["recipe_candidate_slugs"]))
    roles = [{"role_id": "main", "courses": ["main"], "required": True}]
    assert any(r["slug"] == lost_line for meal in valid_meals(episode, roles) for _, r in meal)
    assert all(r["slug"] != lost_line for meal in valid_meals(episode, roles, "lunch") for _, r in meal)
