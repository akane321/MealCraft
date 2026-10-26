"""Product gate regressions with explicit evidence; no model or human-label claim."""

import pytest

from app.planning.recipe_pair_similarity import RecipePairIndex, RecipePairSignals
from tests.test_planning_capability import _composed_plan, composed_client  # noqa: F401


@pytest.mark.parametrize(
    "signals,status",
    [
        (RecipePairSignals(0.5, 0.5, 0.9, "available"), 422),
        (RecipePairSignals(0.1, 0.1, 0.4, "available"), 201),
        (RecipePairSignals(0.5, 0.5, None, "catalog_missing"), 201),
    ],
)
def test_swap_blocks_known_near_without_inventing_missing_evidence(
    composed_client,  # noqa: F811
    monkeypatch,
    signals,
    status,
):
    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "main")
    monkeypatch.setattr(RecipePairIndex, "compare", lambda self, left, right: signals)
    response = composed_client.post(
        f"/api/plans/{initial['id']}/replan/preview",
        json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
    )
    assert response.status_code == status, response.text
    if status == 422:
        assert "near-duplicate" in response.json()["detail"]
    else:
        assert response.json()["after_entry"]["recipe_slug"] != target["recipe"]["slug"]
    saved = composed_client.get(f"/api/plans/{initial['id']}").json()
    assert saved["days"] == initial["days"]
    assert saved["revision"] == initial["revision"]


def test_swap_also_checks_the_other_dishes_staying_in_the_meal(composed_client, monkeypatch):  # noqa: F811
    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "main")
    vegetable = next(
        d for d in initial["days"] if d["day_index"] == target["day_index"] and d["role_id"] == "vegetable"
    )
    vegetable_key = "slug:" + vegetable["recipe"]["slug"]

    def compare(self, left, right):
        if vegetable_key in (left, right):
            return RecipePairSignals(0.5, 0.5, 0.9, "available")
        return RecipePairSignals(0.1, 0.1, 0.4, "available")

    monkeypatch.setattr(RecipePairIndex, "compare", compare)
    response = composed_client.post(
        f"/api/plans/{initial['id']}/replan/preview",
        json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
    )
    assert response.status_code == 422, response.text
    assert "near-duplicate" in response.json()["detail"]
    assert composed_client.get(f"/api/plans/{initial['id']}").json()["days"] == initial["days"]
