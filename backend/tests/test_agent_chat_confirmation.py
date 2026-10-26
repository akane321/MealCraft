"""ADR-0098: a clear confirmation typed in the chat confirms a waiting plan or change, through the buttons' checks."""

import pytest

from app.db.session import get_db_session
from app.evaluation.conversation_adapter import CONFIRMATION_MESSAGE
from app.main import app
from app.models.agent import AgentSession
from app.models.meal_plan import MealPlan
from app.services.agent import AgentSessionService, clear_confirmation
from app.services.replanning import MealPlanReplanConflictError, MealPlanReplanningService
from tests.test_recipes import _set_authenticated_household_role
from tests.test_recipes import recipe_client as recipe_client

ENGLISH = ("Build a weekly plan for 2 people with a S$20 per meal budget.", "Replace day 3 with a different meal.")
CHINESE = ("为2个人制定每餐20新币的每周计划。", "把周三晚餐换掉。")
# (the request, its change, a clear confirmation, a second one, what the saved plan's reply says, a refusal's opening)
LANGUAGES = [
    pytest.param(*ENGLISH, "I confirm. Please proceed.", "Confirm", "Here's your week", "Nothing was saved.", id="en"),
    pytest.param(*CHINESE, "确认", "我确认", "这是你这一周的安排", "没有保存任何改动。", id="zh"),
]
NOT_CLEAR = [
    "ok",
    "sure",
    "yes",
    "好",
    "嗯",
    "可以",
    "Confirm?",
    "确认？",
    "Yes, but swap Tuesday",
    "确认，但是换掉周二",
]


@pytest.mark.parametrize(
    "message",
    [
        "I confirm. Please proceed.",
        "i confirm please proceed",
        "Confirm!",
        "  CONFIRM.  ",
        "Yes, apply it.",
        "Apply the changes",
        "Please proceed",
        "确认",
        "我确认。",
        "确认，继续",
        "确认继续",
        "确认应用！",
    ],
)
def test_clear_confirmations_are_recognised_after_case_spaces_and_punctuation(message):
    assert clear_confirmation(message)


@pytest.mark.parametrize(
    "message",
    [
        *NOT_CLEAR,
        "I confirm. Please proceed?",
        "Confirm, and add lunch on Friday",
        "确认，再加一道汤",
        "yes please",
        "sounds good",
        "",
    ],
)
def test_vague_agreement_questions_and_added_changes_are_not_clear_confirmations(message):
    assert not clear_confirmation(message)


def test_the_evaluation_harness_confirmation_is_a_clear_confirmation():
    """ADR-0098 item 4: the bytes every system receives confirm the product too (the product never imports them)."""
    assert clear_confirmation(CONFIRMATION_MESSAGE)


def _database():
    generator = app.dependency_overrides[get_db_session]()
    return generator, next(generator)


def _change(model, row_id, **values):
    generator, database = _database()
    try:
        row = database.get(model, row_id)
        for key, value in values.items():
            setattr(row, key, value(getattr(row, key)) if callable(value) else value)
        database.commit()
    finally:
        generator.close()


def _ready(client, request):
    created = client.post("/api/agent/sessions", json={"message": request})
    assert created.status_code == 201, created.text
    assert created.json()["can_confirm"]
    return created.json()


def _say(client, session_id, message, **headers):
    response = client.post(f"/api/agent/sessions/{session_id}/messages", json={"message": message}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _plans(client):
    return client.get("/api/plans").json()["items"]


def _previewed(client, request, change):
    session = _ready(client, request)
    plan = client.post(f"/api/agent/sessions/{session['id']}/confirm").json()["plan"]
    previewed = _say(client, session["id"], change)
    assert previewed["pending_replan"]["status"] == "previewed"
    return previewed, plan


def _applied(client, plan_id):
    return [
        event for event in client.get(f"/api/plans/{plan_id}/events").json()["items"] if event["status"] == "applied"
    ]


CHAT_CONFIRMATION_CODES = {"CHAT_CONFIRMATION", "CHAT_CONFIRMATION_NOT_APPLIED"}
CONFIRM_TOOLS = {"generate_plan_preview", "save_plan_revision", "confirm_replan"}


def _runs(client, session_id):
    return client.get(f"/api/agent/sessions/{session_id}/runs").json()["items"]


def _answered_as_chat(client, answered, runs_before):
    """The words went through the chat, not the confirm logic: a scope of their own and one ordinary turn's run."""
    assert (answered["last_scope_decision"] or {}).get("reason_code") not in CHAT_CONFIRMATION_CODES
    runs = _runs(client, answered["id"])
    assert len(runs) == runs_before + 1
    assert "turn_completed" in {checkpoint["stage"] for checkpoint in runs[0]["checkpoints"]}
    assert not {tool["tool_name"] for tool in runs[0]["tool_executions"]} & CONFIRM_TOOLS


def _commits(client, session_id):
    runs = client.get(f"/api/agent/sessions/{session_id}/runs").json()["items"]
    return [
        tool["tool_name"]
        for run in runs
        for tool in run["tool_executions"]
        if tool["effect"] == "commit" and tool["status"] == "succeeded"
    ]


# The plan preview: the Plan my week card.


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_clear_confirmation_saves_the_waiting_plan_once(
    recipe_client, request_text, change, clear, again, saved, refused
):
    session = _ready(recipe_client, request_text)
    confirmed = _say(recipe_client, session["id"], clear)
    assert confirmed["status"] == "planned" and confirmed["plan_id"] is not None
    assert [item["id"] for item in _plans(recipe_client)] == [confirmed["plan_id"]]
    # Said in the chat like the button's reply, after the household's own words; the run is the button's.
    assert [(m["role"], m["content"]) for m in confirmed["messages"][-2:]][0] == ("user", clear)
    assert saved in confirmed["messages"][-1]["content"]
    assert confirmed["latest_run"]["termination_reason_code"] == "PLAN_SAVED"
    assert confirmed["last_scope_decision"]["reason_code"] == "CHAT_CONFIRMATION"
    assert _commits(recipe_client, session["id"]) == ["save_plan_revision"]

    # Nothing waits any more: a second confirmation is ordinary chat and saves nothing.
    runs_before = len(_runs(recipe_client, session["id"]))
    second = _say(recipe_client, session["id"], again)
    _answered_as_chat(recipe_client, second, runs_before)
    assert second["plan_id"] == confirmed["plan_id"]
    assert [item["id"] for item in _plans(recipe_client)] == [confirmed["plan_id"]]
    assert recipe_client.get(f"/api/plans/{confirmed['plan_id']}").json()["revision"] == 1
    assert _commits(recipe_client, session["id"]) == ["save_plan_revision"]


def test_resending_a_confirmation_with_its_key_replays_it(recipe_client):
    session = _ready(recipe_client, ENGLISH[0])
    first = _say(recipe_client, session["id"], "Confirm", **{"Idempotency-Key": "typed-confirm"})
    replay = _say(recipe_client, session["id"], "Confirm", **{"Idempotency-Key": "typed-confirm"})
    assert replay["plan_id"] == first["plan_id"] and len(replay["messages"]) == len(first["messages"])
    assert len(_plans(recipe_client)) == 1


@pytest.mark.parametrize(("start", "clear"), [("Plan dinner", "I confirm. Please proceed."), ("安排晚餐", "确认")])
def test_a_confirmation_with_no_plan_waiting_is_ordinary_chat(recipe_client, start, clear):
    created = recipe_client.post("/api/agent/sessions", json={"message": start}).json()
    assert not created["can_confirm"]
    runs_before = len(_runs(recipe_client, created["id"]))
    answered = _say(recipe_client, created["id"], clear)
    assert answered["plan_id"] is None and _plans(recipe_client) == []
    assert answered["messages"][-2]["content"] == clear and answered["messages"][-1]["role"] == "assistant"
    _answered_as_chat(recipe_client, answered, runs_before)


@pytest.mark.parametrize("message", NOT_CLEAR)
def test_vague_or_questioning_or_changing_words_never_save_the_plan(recipe_client, message):
    session = _ready(recipe_client, ENGLISH[0])
    answered = _say(recipe_client, session["id"], message)
    assert answered["plan_id"] is None and _plans(recipe_client) == []
    assert _commits(recipe_client, session["id"]) == []


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_plan_card_that_changed_before_the_confirmation_saves_nothing(
    recipe_client, monkeypatch, request_text, change, clear, again, saved, refused
):
    """The plan's revision for a card is the conversation's context version: one moved meanwhile is refused."""
    session = _ready(recipe_client, request_text)
    start = AgentSessionService._start_run

    def intervening_edit(self, **values):
        if values["input_payload"] == {"message": clear}:
            _change(AgentSession, session["id"], context_version=lambda version: version + 1)
        return start(self, **values)

    monkeypatch.setattr(AgentSessionService, "_start_run", intervening_edit)
    answered = _say(recipe_client, session["id"], clear)
    assert answered["plan_id"] is None and _plans(recipe_client) == []
    assert answered["messages"][-2]["content"] == clear
    assert answered["messages"][-1]["content"].startswith(refused)
    assert answered["last_scope_decision"]["reason_code"] == "CHAT_CONFIRMATION_NOT_APPLIED"
    assert answered["latest_run"]["status"] == "failed"


def test_a_week_the_planner_cannot_find_is_explained_after_the_typed_confirmation(recipe_client, monkeypatch):
    monkeypatch.setattr(AgentSessionService, "_refusal", lambda self, constraints, lang: None)  # fails at Plan
    session = _ready(recipe_client, "Plan a week for 4 for S$10 total")
    answered = _say(recipe_client, session["id"], "Confirm")
    assert answered["plan_id"] is None and _plans(recipe_client) == []
    assert [m["role"] for m in answered["messages"][-2:]] == ["user", "assistant"]
    assert answered["messages"][-2]["content"] == "Confirm"
    assert "S$" in answered["messages"][-1]["content"]  # the planner's own reason, as after the button
    assert answered["last_scope_decision"]["reason_code"] == "CHAT_CONFIRMATION_NOT_APPLIED"
    assert answered["latest_run"]["status"] == "failed"


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_plan_card_that_expired_before_the_confirmation_saves_nothing(
    recipe_client, monkeypatch, request_text, change, clear, again, saved, refused
):
    session = _ready(recipe_client, request_text)
    confirm = AgentSessionService.confirm

    def card_gone(self, session_id, **values):
        _change(AgentSession, session_id, status="collecting", context_version=lambda version: version + 1)
        return confirm(self, session_id, **values)

    monkeypatch.setattr(AgentSessionService, "confirm", card_gone)
    answered = _say(recipe_client, session["id"], clear)
    assert answered["plan_id"] is None and _plans(recipe_client) == []
    assert answered["messages"][-1]["content"].startswith(refused)


def test_a_viewer_cannot_save_the_plan_by_typing_a_confirmation(recipe_client):
    session = _ready(recipe_client, ENGLISH[0])
    _set_authenticated_household_role("viewer")
    response = recipe_client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": "Confirm"})
    assert response.status_code == 403
    assert _plans(recipe_client) == []


# The replan preview: a proposed change to the week.


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_clear_confirmation_applies_the_waiting_change_once(
    recipe_client, request_text, change, clear, again, saved, refused
):
    previewed, plan = _previewed(recipe_client, request_text, change)
    applied = _say(recipe_client, previewed["id"], clear)
    assert applied["pending_replan"] is None
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"] + 1
    assert [event["id"] for event in _applied(recipe_client, plan["id"])] == [previewed["pending_replan"]["id"]]
    assert applied["messages"][-2]["content"] == clear
    assert applied["messages"][-1]["content"].startswith(("Done.", "好了"))
    assert applied["latest_run"]["termination_reason_code"] == "REPLAN_APPLIED"
    assert applied["last_scope_decision"]["reason_code"] == "CHAT_CONFIRMATION"

    runs_before = len(_runs(recipe_client, previewed["id"]))
    second = _say(recipe_client, previewed["id"], again)
    _answered_as_chat(recipe_client, second, runs_before)
    assert second["pending_replan"] is None
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"] + 1
    assert len(_applied(recipe_client, plan["id"])) == 1
    assert len(_plans(recipe_client)) == 1


def test_resending_a_change_confirmation_with_its_key_replays_it(recipe_client):
    previewed, plan = _previewed(recipe_client, *ENGLISH)
    first = _say(recipe_client, previewed["id"], "Confirm", **{"Idempotency-Key": "typed-change"})
    replay = _say(recipe_client, previewed["id"], "Confirm", **{"Idempotency-Key": "typed-change"})  # not a 409
    assert len(replay["messages"]) == len(first["messages"])
    assert replay["latest_run"]["id"] == first["latest_run"]["id"]
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"] + 1
    assert len(_applied(recipe_client, plan["id"])) == 1


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_confirmation_with_no_change_waiting_is_ordinary_chat(
    recipe_client, request_text, change, clear, again, saved, refused
):
    session = _ready(recipe_client, request_text)
    plan = recipe_client.post(f"/api/agent/sessions/{session['id']}/confirm").json()["plan"]
    runs_before = len(_runs(recipe_client, session["id"]))
    answered = _say(recipe_client, session["id"], clear)
    assert answered["pending_replan"] is None
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"]
    assert _applied(recipe_client, plan["id"]) == [] and len(_plans(recipe_client)) == 1
    assert answered["messages"][-2]["content"] == clear and answered["messages"][-1]["role"] == "assistant"
    _answered_as_chat(recipe_client, answered, runs_before)


@pytest.mark.parametrize("message", NOT_CLEAR)
def test_vague_or_questioning_or_changing_words_never_apply_the_change(recipe_client, message):
    previewed, plan = _previewed(recipe_client, *ENGLISH)
    _say(recipe_client, previewed["id"], message)
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"]
    assert _applied(recipe_client, plan["id"]) == []


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_change_previewed_on_an_older_revision_is_not_applied(
    recipe_client, request_text, change, clear, again, saved, refused
):
    previewed, plan = _previewed(recipe_client, request_text, change)
    _change(MealPlan, plan["id"], revision=plan["revision"] + 1)  # the week moved on since the preview
    answered = _say(recipe_client, previewed["id"], clear)
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"] + 1
    assert _applied(recipe_client, plan["id"]) == []
    assert answered["messages"][-2]["content"] == clear
    assert answered["messages"][-1]["content"].startswith(refused)
    # A stale preview can never be confirmed: its card goes, as after a refused button.
    assert answered["pending_replan"] is None


@pytest.mark.parametrize(("request_text", "change", "clear", "again", "saved", "refused"), LANGUAGES)
def test_a_change_already_applied_elsewhere_waits_for_nothing(
    recipe_client, request_text, change, clear, again, saved, refused
):
    """The conversation still links the preview the week's page applied: nothing waits, so the words are chat."""
    previewed, plan = _previewed(recipe_client, request_text, change)
    event_id = previewed["pending_replan"]["id"]
    assert recipe_client.post(f"/api/plans/{plan['id']}/replan/{event_id}/confirm").status_code == 200
    runs_before = len(_runs(recipe_client, previewed["id"]))
    answered = _say(recipe_client, previewed["id"], clear)
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"] + 1
    assert [event["id"] for event in _applied(recipe_client, plan["id"])] == [event_id]
    _answered_as_chat(recipe_client, answered, runs_before)


def test_a_late_refused_confirmation_keeps_what_the_session_moved_on_to(recipe_client, monkeypatch):
    """Two confirmations at once: the one that lands second, refused, leaves the session's newer state alone."""
    previewed, plan = _previewed(recipe_client, *ENGLISH)
    newer = recipe_client.post(
        f"/api/plans/{plan['id']}/replan/preview",
        json={"event_type": "LOCK_MEAL", "entry_id": plan["days"][0]["entry_id"]},
    )
    assert newer.status_code == 201, newer.text

    def overtaken(self, *, plan_id, event_id):
        # Meanwhile the conversation moved on to a new preview, and the one this tried went stale.
        _change(AgentSession, previewed["id"], pending_event_id=newer.json()["id"])
        raise MealPlanReplanConflictError(
            "This preview is stale because the meal plan has changed. Generate a new preview."
        )

    monkeypatch.setattr(MealPlanReplanningService, "confirm", overtaken)
    answered = _say(recipe_client, previewed["id"], "Confirm")
    assert answered["messages"][-1]["content"].startswith("Nothing was saved.")
    assert answered["pending_replan"]["id"] == newer.json()["id"]
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"]


def test_a_viewer_cannot_apply_the_change_by_typing_a_confirmation(recipe_client):
    previewed, plan = _previewed(recipe_client, *ENGLISH)
    _set_authenticated_household_role("viewer")
    response = recipe_client.post(f"/api/agent/sessions/{previewed['id']}/messages", json={"message": "确认"})
    assert response.status_code == 403
    assert recipe_client.get(f"/api/plans/{plan['id']}").json()["revision"] == plan["revision"]
    assert _applied(recipe_client, plan["id"]) == []
