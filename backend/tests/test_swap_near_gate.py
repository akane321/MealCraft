"""Near dishes are a preference for a swap, never a refusal; no model or human-label claim."""

import pytest

from app.planning.recipe_pair_similarity import RecipePairIndex, RecipePairSignals
from tests.test_planning_capability import _composed_plan, composed_client  # noqa: F401

NEAR = RecipePairSignals(0.5, 0.5, 0.9, "available")
FAR = RecipePairSignals(0.1, 0.1, 0.4, "available")
UNAVAILABLE = {"broccoli-stirfry": "broccoli", "spinach-saute": "baby_spinach", "zucchini-salad": "zucchini"}


def _preview(client, plan, target, event_type):
    request = {"entry_id": target["entry_id"], "event_type": event_type}
    if event_type == "ITEM_UNAVAILABLE":
        request["unavailable_ingredient"] = UNAVAILABLE[target["recipe"]["slug"]]
    return client.post(f"/api/plans/{plan['id']}/replan/preview", json=request)


@pytest.mark.parametrize(
    "signals",
    [NEAR, FAR, RecipePairSignals(0.5, 0.5, None, "catalog_missing")],
)
@pytest.mark.parametrize("event_type", ["REPLACE_MEAL", "ITEM_UNAVAILABLE"])
def test_swap_is_never_refused_for_near_evidence(composed_client, monkeypatch, signals, event_type):  # noqa: F811
    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "vegetable")
    monkeypatch.setattr(RecipePairIndex, "compare", lambda self, left, right: signals)
    response = _preview(composed_client, initial, target, event_type)
    assert response.status_code == 201, response.text
    assert response.json()["after_entry"]["recipe_slug"] != target["recipe"]["slug"]
    saved = composed_client.get(f"/api/plans/{initial['id']}").json()
    assert saved["days"] == initial["days"]
    assert saved["revision"] == initial["revision"]


@pytest.mark.parametrize("event_type", ["REPLACE_MEAL", "ITEM_UNAVAILABLE"])
def test_swap_prefers_the_one_dish_that_is_not_near(composed_client, monkeypatch, event_type):  # noqa: F811
    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "vegetable")
    monkeypatch.setattr(RecipePairIndex, "compare", lambda self, left, right: NEAR)
    fallback = _preview(composed_client, initial, target, event_type)
    assert fallback.status_code == 201, fallback.text
    near_slug = fallback.json()["after_entry"]["recipe_slug"]
    other = next(slug for slug in UNAVAILABLE if slug not in (target["recipe"]["slug"], near_slug))

    def compare(self, left, right):
        return FAR if "slug:" + other in (left, right) else NEAR

    monkeypatch.setattr(RecipePairIndex, "compare", compare)
    preferred = _preview(composed_client, initial, target, event_type)
    assert preferred.status_code == 201, preferred.text
    assert preferred.json()["after_entry"]["recipe_slug"] == other


def test_swap_also_checks_the_other_dishes_staying_in_the_meal(composed_client, monkeypatch):  # noqa: F811
    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "main")
    vegetable = next(
        d for d in initial["days"] if d["day_index"] == target["day_index"] and d["role_id"] == "vegetable"
    )
    vegetable_key = "slug:" + vegetable["recipe"]["slug"]

    def compare(self, left, right):
        return NEAR if vegetable_key in (left, right) else FAR

    monkeypatch.setattr(RecipePairIndex, "compare", compare)
    response = composed_client.post(
        f"/api/plans/{initial['id']}/replan/preview",
        json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
    )
    # Every main is near the vegetable that stays, so the swap falls back to a near dish rather than refuse.
    assert response.status_code == 201, response.text
    assert composed_client.get(f"/api/plans/{initial['id']}").json()["days"] == initial["days"]


def test_swap_cannot_duplicate_a_product_dish_kind_in_the_same_meal(composed_client, monkeypatch):  # noqa: F811
    from app.services import replanning

    initial = _composed_plan(composed_client)
    target = next(d for d in initial["days"] if d["role_id"] == "main")
    retained = next(d for d in initial["days"] if d["day_index"] == target["day_index"] and d["role_id"] == "vegetable")
    real_kind = replanning.dish_kind

    def collide(title):
        return "forced-collision" if title != target["recipe"]["title"] else real_kind(title)

    monkeypatch.setattr(replanning, "dish_kind", collide)
    response = composed_client.post(
        f"/api/plans/{initial['id']}/replan/preview",
        json={"entry_id": target["entry_id"], "event_type": "REPLACE_MEAL"},
    )
    assert response.status_code in (409, 422), response.text
    assert retained["recipe"]["title"] != target["recipe"]["title"]


@pytest.mark.parametrize("explicit_cap", [None, 2])
def test_near_preference_precedes_default_repeat_fallback_but_never_relaxes_explicit_cap(monkeypatch, explicit_cap):
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
        assert preview.status_code == 201, preview.text
        if explicit_cap is None:
            assert preview.json()["after_entry"]["recipe_slug"] == "oat-bake"
        else:
            # The stated cap holds, so the only dish within it is a near one, taken as the fallback.
            assert preview.json()["after_entry"]["recipe_slug"] != "oat-bake"
        assert client.get(f"/api/plans/{plan['id']}").json()["days"] == plan["days"]
