"""A household renames, pins and deletes its conversations and deletes its weeks; the console deletes one of either
for an account (2026-10-12, owner)."""

from sqlalchemy import select

from app.models.agent import AgentSession
from app.models.meal_plan import MealPlan
from app.models.platform import AuditEvent, HouseholdMembership
from tests.test_operations_console_api import _count, _second_account, console  # noqa: F401

WEEK = {"household_size": 2, "max_cooking_time_minutes": 60, "weekly_budget_sgd": 40, "pricing_mode": "fixture"}


def _titles(client) -> list[str | None]:
    return [item["title"] for item in client.get("/api/agent/sessions", params={"limit": 50}).json()["items"]]


def test_a_household_renames_pins_and_deletes_its_conversations(console) -> None:  # noqa: F811
    client, factory = console
    first = client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    second = client.post("/api/agent/sessions", json={"message": "Dinners for three"}).json()

    renamed = client.patch(f"/api/agent/sessions/{first['id']}", json={"title": "  Lim   family week "})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Lim family week"
    # A rename does not count as a change: the list keeps its order by what the conversation last did.
    assert renamed.json()["updated_at"] == first["updated_at"]
    assert _titles(client) == [None, "Lim family week"]

    pinned = client.patch(f"/api/agent/sessions/{first['id']}", json={"pinned": True}).json()
    assert pinned["pinned_at"] is not None and pinned["title"] == "Lim family week"
    assert _titles(client) == ["Lim family week", None]
    assert client.patch(f"/api/agent/sessions/{first['id']}", json={"pinned": False}).json()["pinned_at"] is None
    # A blank title goes back to the first message.
    assert client.patch(f"/api/agent/sessions/{first['id']}", json={"title": " "}).json()["title"] is None

    assert client.delete(f"/api/agent/sessions/{second['id']}").status_code == 204
    assert [item["id"] for item in client.get("/api/agent/sessions").json()["items"]] == [first["id"]]
    assert client.get(f"/api/agent/sessions/{second['id']}").status_code == 404
    assert client.delete(f"/api/agent/sessions/{second['id']}").status_code == 404
    assert client.patch(f"/api/agent/sessions/{second['id']}", json={"pinned": True}).status_code == 404


def test_a_household_cannot_touch_another_household_s_conversation_or_week(console) -> None:  # noqa: F811
    client, factory = console
    bob = _second_account(factory)
    with factory() as database:
        household = database.scalar(select(HouseholdMembership.household_id).where(HouseholdMembership.user_id == bob))
        session_id = database.scalar(select(AgentSession.id).where(AgentSession.household_id == household))
        plan_id = database.scalar(select(MealPlan.id).where(MealPlan.household_id == household))

    assert client.delete(f"/api/agent/sessions/{session_id}").status_code == 404
    assert client.patch(f"/api/agent/sessions/{session_id}", json={"title": "mine"}).status_code == 404
    assert client.delete(f"/api/plans/{plan_id}").status_code == 404
    assert _count(factory, AgentSession, AgentSession.id == session_id) == 1
    assert _count(factory, MealPlan, MealPlan.id == plan_id) == 1


def test_deleting_a_week_keeps_the_conversation_that_planned_it(console) -> None:  # noqa: F811
    client, factory = console
    plan = client.post("/api/plans/generate", json=WEEK)
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]
    talk = client.post("/api/agent/sessions", json={"message": "Dinners for two"}).json()
    with factory() as database:
        database.get(AgentSession, talk["id"]).plan_id = plan_id
        database.commit()

    assert client.delete(f"/api/plans/{plan_id}").status_code == 204
    assert client.get(f"/api/plans/{plan_id}").status_code == 404
    kept = client.get(f"/api/agent/sessions/{talk['id']}").json()
    assert kept["plan_id"] is None and kept["messages"]
    assert client.delete(f"/api/plans/{plan_id}").status_code == 404


def test_the_console_deletes_one_conversation_or_one_week_of_an_account(console) -> None:  # noqa: F811
    client, factory = console
    bob = _second_account(factory)
    detail = client.get(f"/api/ops/users/{bob}").json()
    session_id = detail["recent_conversations"][0]["id"]
    plan_id = detail["recent_plans"][0]["id"]
    assert "title" in detail["recent_conversations"][0]

    assert client.delete(f"/api/ops/users/{bob}/conversations/{session_id}").json() == {"deleted": 1}
    assert client.delete(f"/api/ops/users/{bob}/conversations/{session_id}").status_code == 404
    assert client.delete(f"/api/ops/users/{bob}/plans/{plan_id}").json() == {"deleted": 1}
    assert client.delete(f"/api/ops/users/{bob}/plans/{plan_id}").status_code == 404
    after = client.get(f"/api/ops/users/{bob}").json()
    assert (after["conversations"], after["plans"]) == (0, 0)
    with factory() as database:
        actions = set(database.scalars(select(AuditEvent.action).where(AuditEvent.target_type == "user")))
    assert {"user.conversation_deleted", "user.plan_deleted"} <= actions
