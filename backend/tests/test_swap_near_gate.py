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


@pytest.mark.parametrize("explicit_cap", [None, 2])
def test_near_filter_precedes_default_repeat_fallback_but_never_relaxes_explicit_cap(monkeypatch, explicit_cap):
    from collections import Counter

    from app.core.clock import today
    from tests.test_planning_capability import _dish, dish_client

    dishes = [
        _dish("oat-bake", "main", "rolled_oats", 100, calories=450, prep=1, cook=1),
        *[
            _dish(slug, "main", ingredient, 100, calories=450)
            for slug, ingredient in (
                ("chickpea-stew", "chickpea"),
                ("tuna-melt", "canned_tuna"),
                ("tomato-stew", "canned_tomato"),
                ("broccoli-bake", "broccoli"),
                ("mushroom-rice", "mushroom"),
            )
        ],
    ]
    with dish_client(monkeypatch, dishes) as client:
        response = client.post(
            "/api/plans/generate",
            json={
                "requires_halal": False,
                "start_date": today().isoformat(),
                "household_size": 4,
                "max_cooking_time_minutes": 90,
                "pricing_mode": "fixture",
                "plan_shape": {"meals": {"dinner": [{"role_id": "main", "courses": ["main"]}]}},
                **({"max_uses_per_recipe": explicit_cap} if explicit_cap is not None else {}),
            },
        )
        assert response.status_code == 201, response.text
        plan = response.json()
        assert Counter(d["recipe"]["slug"] for d in plan["days"])["oat-bake"] == 2
        target = next(d for d in plan["days"] if d["recipe"]["slug"] == "chickpea-stew")

        def compare(self, left, right):
            if "slug:oat-bake" in (left, right):
                return RecipePairSignals(0.1, 0.1, 0.4, "available")
            return RecipePairSignals(0.5, 0.5, 0.9, "available")

        monkeypatch.setattr(RecipePairIndex, "compare", compare)
        preview = client.post(
            f"/api/plans/{plan['id']}/replan/preview",
            json={
                "entry_id": target["entry_id"],
                "event_type": "REPLACE_MEAL",
            },
        )
        if explicit_cap is None:
            assert preview.status_code == 201, preview.text
            assert preview.json()["after_entry"]["recipe_slug"] == "oat-bake"
        else:
            assert preview.status_code == 422, preview.text
        assert client.get(f"/api/plans/{plan['id']}").json()["days"] == plan["days"]
