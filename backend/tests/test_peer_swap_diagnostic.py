"""Developer swap diagnostic; observations do not assert a frozen human policy."""

import json
from collections import defaultdict

from app.planning.recipe_quality import dish_kind
from tests.test_household_planning import ONE_MAIN, catalog_client, plan, recipe_client  # noqa: F401
from tests.test_planning_capability import _composed_plan, _dish, composed_client, dish_client  # noqa: F401


def assert_product_roles_and_kinds(plan_output):
    meals = defaultdict(lambda: {"roles": [], "kinds": []})
    for dish in plan_output["days"]:
        meal = meals[(dish["day_index"], dish["meal_type"])]
        meal["roles"].append(dish["role_id"])
        meal["kinds"].append(dish_kind(dish["recipe"]["title"]))
    assert len(meals) == 7
    for meal in meals.values():
        assert set(meal["roles"]) == {"main", "vegetable", "soup"}
        assert len(meal["roles"]) == len(set(meal["roles"]))
        assert len(meal["kinds"]) == len(set(meal["kinds"]))


def test_twenty_one_composed_product_swap_previews_are_accepted(monkeypatch):
    dishes = [
        _dish("salmon-bake", "main", "salmon_fillet", 400, calories=500),
        _dish("chicken-roast", "main", "chicken_breast", 400, calories=450),
        _dish("broccoli-stirfry", "side", "broccoli", 300, calories=100),
        _dish("spinach-saute", "side", "baby_spinach", 200, calories=80),
        _dish("zucchini-salad", "salad", "zucchini", 300, calories=60),
        _dish("tomato-soup", "soup", "tomato", 500, calories=150, cook=25),
        _dish("carrot-soup", "soup", "carrot", 250, calories=90, cook=20),
    ]
    with dish_client(monkeypatch, dishes) as client:
        initial = _composed_plan(client)
        assert len(initial["days"]) == 21
        assert_product_roles_and_kinds(initial)
        observations = []
        for target in initial["days"]:
            response = client.post(
                f"/api/plans/{initial['id']}/replan/preview",
                json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
            )
            assert response.status_code == 201, response.text
            event = response.json()
            row = {
                "entry_id": target["entry_id"],
                "before": "slug:" + target["recipe"]["slug"],
                "after": "slug:" + event["after_entry"]["recipe_slug"],
                "purchase_total_delta_sgd": event["purchase_total_delta_sgd"],
            }
            assert event["after_entry"]["role_id"] == target["role_id"]
            assert row["before"] != row["after"]
            observations.append(row)
            saved = client.get(f"/api/plans/{initial['id']}").json()
            assert saved["days"] == initial["days"]
            assert saved["revision"] == initial["revision"]
        assert len(observations) == 21
        print("SWAP_ACCEPTANCE=" + json.dumps(observations))


def test_twenty_one_sequential_swaps_save_only_the_confirmed_dish(catalog_client):  # noqa: F811
    from decimal import Decimal

    current = plan(
        catalog_client,
        plan_shape={"meals": {meal: ONE_MAIN for meal in ("breakfast", "lunch", "dinner")}},
    )
    assert len(current["days"]) == 21
    entry_ids = [dish["entry_id"] for dish in current["days"]]
    confirmed = 0
    for entry_id in entry_ids:
        before = current
        original = {dish["entry_id"]: dish for dish in before["days"]}
        response = catalog_client.post(
            f"/api/plans/{before['id']}/replan/preview",
            json={"entry_id": entry_id, "event_type": "REPLACE_MEAL"},
        )
        assert response.status_code == 201, response.text
        event = response.json()
        unchanged = catalog_client.get(f"/api/plans/{before['id']}").json()
        assert unchanged["days"] == before["days"]
        assert unchanged["revision"] == before["revision"]
        saved = catalog_client.post(f"/api/plans/{before['id']}/replan/{event['id']}/confirm")
        assert saved.status_code == 200, saved.text
        current = saved.json()["plan"]
        actual = {dish["entry_id"]: dish for dish in current["days"]}
        assert set(actual) == set(original)
        assert {key for key in actual if actual[key] != original[key]} == {entry_id}
        assert actual[entry_id]["recipe"]["slug"] == event["after_entry"]["recipe_slug"]
        assert actual[entry_id]["recipe"]["slug"] != original[entry_id]["recipe"]["slug"]
        assert current["revision"] == before["revision"] + 1
        delta = Decimal(str(current["grocery_estimate"]["purchase_total_sgd"])) - Decimal(
            str(before["grocery_estimate"]["purchase_total_sgd"])
        )
        assert abs(delta - Decimal(str(event["purchase_total_delta_sgd"]))) < Decimal("0.01")
        persisted = catalog_client.get(f"/api/plans/{before['id']}").json()
        assert persisted["days"] == current["days"]
        assert persisted["revision"] == current["revision"]
        confirmed += 1
    assert confirmed == 21
