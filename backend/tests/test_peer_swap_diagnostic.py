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
