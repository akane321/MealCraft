"""Developer swap diagnostic; observations do not assert a frozen human policy."""

import json

from tests.test_household_planning import ONE_MAIN, catalog_client, plan, recipe_client  # noqa: F401


def test_twenty_one_catalog_swap_previews_preserve_saved_plan(catalog_client):  # noqa: F811
    initial = plan(
        catalog_client,
        plan_shape={"meals": {meal: ONE_MAIN for meal in ("breakfast", "lunch", "dinner")}},
    )
    assert len(initial["days"]) == 21
    observations = []
    for target in initial["days"]:
        response = catalog_client.post(
            f"/api/plans/{initial['id']}/replan/preview",
            json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
        )
        row = {"entry_id": target["entry_id"], "before": "slug:" + target["recipe"]["slug"]}
        row["http_status"] = response.status_code
        assert response.status_code in (201, 409, 422), response.text
        if response.status_code == 201:
            event = response.json()
            row["after"] = "slug:" + event["after_entry"]["recipe_slug"]
            row["purchase_total_delta_sgd"] = event["purchase_total_delta_sgd"]
            assert row["before"] != row["after"]
        else:
            row["refusal"] = response.json()
        observations.append(row)
        saved = catalog_client.get(f"/api/plans/{initial['id']}").json()
        assert saved["days"] == initial["days"]
        assert saved["revision"] == initial["revision"]
    print("SWAP_DIAGNOSTIC=" + json.dumps(observations))


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
