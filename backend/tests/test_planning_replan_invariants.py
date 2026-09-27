"""Product-level invariants for one-dish edits inside composed meals."""

from decimal import Decimal

import pytest

from tests.test_planning_capability import _composed_plan, composed_client  # noqa: F401


def cents(value):
    return round(Decimal(str(value)) * 100)


@pytest.mark.parametrize("event_type", ["REPLACE_MEAL", "ITEM_UNAVAILABLE", "CANCEL_MEAL"])
def test_confirmed_edit_preserves_every_other_dish_and_reports_actual_cost_delta(composed_client, event_type):  # noqa: F811
    plan = _composed_plan(composed_client)
    plan_id = plan["id"]
    locked = next(d for d in plan["days"] if d["day_index"] == 2 and d["role_id"] == "soup")
    lock = composed_client.post(
        f"/api/plans/{plan_id}/replan/preview",
        json={"entry_id": locked["entry_id"], "event_type": "LOCK_MEAL"},
    )
    assert lock.status_code == 201, lock.text
    confirmed_lock = composed_client.post(f"/api/plans/{plan_id}/replan/{lock.json()['id']}/confirm")
    assert confirmed_lock.status_code == 200, confirmed_lock.text
    cooked = composed_client.patch(f"/api/plans/{plan_id}/meals/1/dinner", json={"status": "completed"})
    assert cooked.status_code == 200, cooked.text
    before = composed_client.get(f"/api/plans/{plan_id}").json()
    target = next(d for d in before["days"] if d["day_index"] == 3 and d["role_id"] == "vegetable")
    request = {"entry_id": target["entry_id"], "event_type": event_type}
    if event_type == "ITEM_UNAVAILABLE":
        request["unavailable_ingredient"] = {
            "broccoli-stirfry": "broccoli",
            "spinach-saute": "baby_spinach",
            "zucchini-salad": "zucchini",
        }[target["recipe"]["slug"]]
    preview = composed_client.post(f"/api/plans/{plan_id}/replan/preview", json=request)
    assert preview.status_code == 201, preview.text
    event = preview.json()
    untouched = composed_client.get(f"/api/plans/{plan_id}").json()
    assert untouched["days"] == before["days"]
    assert untouched["revision"] == before["revision"]
    response = composed_client.post(f"/api/plans/{plan_id}/replan/{event['id']}/confirm")
    assert response.status_code == 200, response.text
    after = response.json()["plan"]
    previous = {d["entry_id"]: d for d in before["days"]}
    current = {d["entry_id"]: d for d in after["days"]}
    assert set(previous) == set(current)
    assert {key for key in previous if previous[key] != current[key]} == {target["entry_id"]}
    assert current[locked["entry_id"]]["is_locked"]
    assert all(d["status"] == "completed" for d in after["days"] if d["day_index"] == 1)
    edited = current[target["entry_id"]]
    assert (edited["role_id"], edited["portion_share"]) == (target["role_id"], target["portion_share"])
    if event_type == "CANCEL_MEAL":
        assert edited["status"] == "skipped"
    else:
        assert edited["recipe"]["slug"] == event["after_entry"]["recipe_slug"] != target["recipe"]["slug"]
    assert after["revision"] == before["revision"] + 1
    assert composed_client.get(f"/api/plans/{plan_id}").json()["days"] == after["days"]
    actual_delta = cents(after["grocery_estimate"]["purchase_total_sgd"]) - cents(
        before["grocery_estimate"]["purchase_total_sgd"]
    )
    assert cents(event["purchase_total_delta_sgd"]) == actual_delta
    assert sum(cents(row["purchase_cost_delta_sgd"]) for row in event["grocery_delta"]) == actual_delta
