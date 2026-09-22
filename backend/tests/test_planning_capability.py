"""The planning capability switch of ADR-0036 section 6: mvp refuses meal compositions."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.test_recipes import _household_profile_payload, recipe_client  # noqa: F401

COMPOSITION = [
    {"role_id": "main", "courses": ["main"]},
    {"role_id": "vegetable", "courses": ["side", "salad"]},
    {"role_id": "soup", "courses": ["soup"], "required": False},
]


@pytest.fixture
def full_capability(monkeypatch):
    monkeypatch.setattr(get_settings(), "planning_capability", "full")


def test_mvp_refuses_a_profile_with_a_meal_composition(recipe_client: TestClient):  # noqa: F811
    response = recipe_client.post(
        "/api/household-profiles", json={**_household_profile_payload(), "meal_composition": COMPOSITION}
    )

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]


def test_full_capability_stores_the_composition_on_the_profile_version(
    recipe_client: TestClient,  # noqa: F811
    full_capability,
):
    response = recipe_client.post(
        "/api/household-profiles", json={**_household_profile_payload(), "meal_composition": COMPOSITION}
    )

    assert response.status_code == 201, response.text
    stored = response.json()["current"]["meal_composition"]
    assert [role["role_id"] for role in stored] == ["main", "vegetable", "soup"]
    assert stored[2]["required"] is False


def test_mvp_refuses_a_plan_request_with_a_meal_composition(recipe_client: TestClient):  # noqa: F811
    response = recipe_client.post("/api/plans/generate", json={"household_size": 2, "meal_composition": COMPOSITION})

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]


def test_a_composition_needs_unique_roles_and_one_required_dish(recipe_client: TestClient):  # noqa: F811
    for composition in (
        [{"role_id": "main", "courses": ["main"]}, {"role_id": "main", "courses": ["soup"]}],
        [{"role_id": "soup", "courses": ["soup"], "required": False}],
    ):
        response = recipe_client.post(
            "/api/plans/generate", json={"household_size": 2, "meal_composition": composition}
        )
        assert response.status_code == 422
