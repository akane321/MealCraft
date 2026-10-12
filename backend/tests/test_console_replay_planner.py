"""Debugging replays of composed weeks, and the cheapest week a budget refusal offers."""

from __future__ import annotations

import math
import re

from app.core.config import get_settings
from tests.test_operations_console_api import _planning_run_ids
from tests.test_operations_console_api import console as console
from tests.test_planning_product_path import REQUEST, database
from tests.test_recipes import recipe_client as recipe_client

LUNCH_AND_DINNER = {
    "meals": {
        "lunch": [{"role_id": "main", "courses": ["main"], "required": True}],
        "dinner": [{"role_id": "main", "courses": ["main"], "required": True}],
    }
}


def test_a_lunch_and_dinner_replay_keeps_every_meal_and_applies_the_search_overrides(console) -> None:
    client, factory = console
    plan = client.post(
        "/api/plans/generate",
        json={
            "start_date": "2026-09-01",
            "household_size": 2,
            "max_cooking_time_minutes": 60,
            "pricing_mode": "fixture",
            "plan_shape": LUNCH_AND_DINNER,
        },
    )
    assert plan.status_code == 201, plan.text
    (run_id,) = _planning_run_ids(factory)

    same = client.post(f"/api/ops/replay/planning/{run_id}", json={}).json()
    for side in (same["original"], same["replay"]):
        meals = {(dish["day"], dish["meal"]) for dish in side["dishes"]}
        assert meals == {(day, meal) for day in range(1, 8) for meal in ("lunch", "dinner")}
    # No override: the composed week searches with its own limits, which grow with its slots.
    stored = same["original"]["settings"]
    assert same["replay"]["settings"]["max_expansions"] == stored["max_expansions"] > 10000

    narrow = client.post(f"/api/ops/replay/planning/{run_id}", json={"beam_width": 2}).json()
    assert narrow["replay"]["settings"]["width"] == 2
    assert narrow["replay"]["settings"]["max_expansions"] == stored["max_expansions"]  # left empty: as stored

    both = client.post(f"/api/ops/replay/planning/{run_id}", json={"beam_width": 2, "max_expansions": 50}).json()
    assert (both["replay"]["settings"]["width"], both["replay"]["settings"]["max_expansions"]) == (2, 50)


def test_a_composed_week_refused_before_its_search_replays_with_its_own_step_budget(console, monkeypatch) -> None:
    """Refused while meals of several dishes were off, the run stored the one-dish limits; they are not its own."""
    client, factory = console
    monkeypatch.setattr(get_settings(), "planning_capability", "mvp")
    week = {"start_date": "2026-09-01", "household_size": 2, "pricing_mode": "fixture", "plan_shape": LUNCH_AND_DINNER}
    assert client.post("/api/plans/generate", json=week).status_code == 422
    (run_id,) = _planning_run_ids(factory)

    on = {"planning_capability": "full"}
    own = client.post(f"/api/ops/replay/planning/{run_id}", json=on).json()["replay"]["settings"]
    narrow = client.post(f"/api/ops/replay/planning/{run_id}", json={**on, "beam_width": 2}).json()["replay"]
    assert len(narrow["dishes"]) == 14
    assert narrow["settings"]["width"] == 2
    assert narrow["settings"]["max_expansions"] == own["max_expansions"] > 10000  # not the stored 10000


def test_a_refused_budget_offers_the_same_cheapest_week_whatever_it_was(recipe_client) -> None:
    """The cost-led fallback never reads the budget, so every refusal offers one amount, and it plans."""
    from app.core.paths import repository_root
    from app.data.catalog import import_catalog, load_catalog

    root = repository_root()
    with database() as session:
        import_catalog(
            session, load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json")
        )

    def plan(budget):
        return recipe_client.post("/api/plans/generate", json={**REQUEST, "weekly_budget_sgd": budget})

    offers = set()
    for budget in (10, 20, 28):  # S$31.70, S$46.50 and S$43.25 when the fallback read the budget
        refused = plan(budget)
        assert refused.status_code == 422
        offers.add(float(re.search(r"The cheapest week I found costs S\$(\d+\.\d\d)", refused.text)[1]))
    (offer,) = offers
    # The cheapest week any of those weightings found; weighed at most x16 against the cheapest dish, every
    # refusal offered S$43.25 instead.
    assert offer == 31.70
    planned = plan(math.ceil(offer))
    assert planned.status_code == 201, planned.text
    assert offer <= planned.json()["grocery_estimate"]["purchase_total_sgd"] <= math.ceil(offer)
    assert plan(60).json()["grocery_estimate"]["purchase_total_sgd"] >= offer
