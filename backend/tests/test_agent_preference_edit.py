import pytest

from app.services.agent import AgentSessionService
from tests.test_recipes import _set_authenticated_household_role
from tests.test_recipes import recipe_client as recipe_client

EMPTY = {"repeat_allowed_meals": [], "flavor_boosts": [], "more_vegetables": False, "lighter": False}


def ready(client):
    response = client.post("/api/agent/sessions", json={"message": "Dinners for two, no peanuts, under S$90"})
    assert response.status_code == 201, response.text
    assert response.json()["can_confirm"]
    return response.json()


def edit(client, session, preferences):
    return client.put(
        f"/api/agent/sessions/{session['id']}/preferences",
        json={"context_version": session["context_version"], "planning_preferences": preferences},
    )


def test_preferences_replace_persist_clear_and_undo_without_changing_hard_limits(recipe_client):
    before = ready(recipe_client)
    wanted = {**EMPTY, "more_vegetables": True, "repeat_allowed_meals": ["breakfast"]}
    response = edit(recipe_client, before, wanted)
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["context_version"] == before["context_version"] + 1
    assert changed["constraints"]["planning_preferences"] == wanted
    assert changed["can_confirm"]
    for key in ("allergens", "household_size", "weekly_budget_sgd", "excluded_ingredients"):
        assert changed["constraints"][key] == before["constraints"][key]
    assert recipe_client.get(f"/api/agent/sessions/{before['id']}").json()["constraints"] == changed["constraints"]
    assert edit(recipe_client, before, EMPTY).status_code == 409
    undone = edit(recipe_client, changed, EMPTY)
    assert undone.status_code == 200, undone.text
    assert undone.json()["constraints"].get("planning_preferences", EMPTY) == EMPTY
    assert undone.json()["constraints"]["allergens"] == before["constraints"]["allergens"]
    runs = recipe_client.get(f"/api/agent/sessions/{before['id']}/runs").json()["items"]
    assert runs[0]["used_llm_calls"] == 0


@pytest.mark.parametrize("extra", [{"allergens": []}, {"weekly_budget_sgd": 1}, {"requires_halal": False}])
def test_preference_edit_cannot_modify_hard_fields(recipe_client, extra):
    before = ready(recipe_client)
    response = recipe_client.put(
        f"/api/agent/sessions/{before['id']}/preferences",
        json={"context_version": before["context_version"], "planning_preferences": EMPTY, **extra},
    )
    assert response.status_code == 422


def test_edit_rejects_not_ready_and_nonexistent_sessions(recipe_client):
    collecting = recipe_client.post("/api/agent/sessions", json={"message": "Plan dinner"}).json()
    assert edit(recipe_client, collecting, EMPTY).status_code == 409
    assert edit(recipe_client, {"id": 999999, "context_version": 1}, EMPTY).status_code == 404


def test_confirmation_rechecks_context_if_preferences_changed_before_run_started(recipe_client, monkeypatch):
    before = ready(recipe_client)
    start = AgentSessionService._start_run

    def intervening_edit(self, **values):
        if values["input_payload"].get("operation") == "confirm_plan":
            current = self.repository.get(before["id"])
            current.context_version += 1
            self.repository.session.commit()
        return start(self, **values)

    monkeypatch.setattr(AgentSessionService, "_start_run", intervening_edit)
    response = recipe_client.post(f"/api/agent/sessions/{before['id']}/confirm")
    assert response.status_code == 409
    assert recipe_client.get(f"/api/agent/sessions/{before['id']}").json()["plan_id"] is None


def test_viewer_cannot_edit_confirmation_preferences(recipe_client):
    before = ready(recipe_client)
    _set_authenticated_household_role("viewer")
    assert edit(recipe_client, before, {**EMPTY, "lighter": True}).status_code == 403
    assert recipe_client.get(f"/api/agent/sessions/{before['id']}").json()["constraints"] == before["constraints"]


def test_another_active_run_blocks_preference_replacement(recipe_client, monkeypatch):
    from app.orchestration.contracts import AgentRunStatus

    before = ready(recipe_client)
    start = AgentSessionService._start_run

    def competing_run(self, **values):
        started = start(self, **values)
        if values["input_payload"].get("operation") == "edit_preferences":
            other = start(
                self,
                **{**values, "idempotency_key": "competing-confirm", "input_payload": {"operation": "confirm_plan"}},
            )
            self.run_lifecycle.transition(other.run, AgentRunStatus.RUNNING)
        return started

    monkeypatch.setattr(AgentSessionService, "_start_run", competing_run)
    assert edit(recipe_client, before, {**EMPTY, "lighter": True}).status_code == 409
    assert recipe_client.get(f"/api/agent/sessions/{before['id']}").json()["constraints"] == before["constraints"]
