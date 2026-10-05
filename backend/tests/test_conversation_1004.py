"""What the 2026-10-04 walkthrough found in the conversation about a planned week.

A question still open (keep this week's meals as the usual ones? which dish?) is answered only by an answer; any
other message is a new instruction, handled as one, and the question goes. Keeping a named meal keeps all of it;
a second dish of a kind the meal has is asked about first; skips, discards and budget refusals are said as a
household says them; a question's composer hint is short; and only a turn that went wrong is "degraded".

A planned week's changes are read by rules in both parser modes; the turns that reach the parser run in both.
"""

from datetime import date

import pytest

from app.agent.limits import _budget_short
from app.agent.replanning import AgentReplanInterpreter
from app.agent.replies import weekday
from app.agent.shape_change import read_shape_change
from app.planning.recipe_similarity import wanted
from app.schemas.agent import AgentConstraintState, AgentReplanDraft
from app.schemas.meal_plan import WeeklyMealPlanResponse
from app.services.agent import keep_shape_answer
from tests.test_agent_limits_and_language import stub_openai
from tests.test_planning_capability import (  # noqa: F401
    _broccoli_soup,
    _conversation_week,
    _dishes,
    _friday,
    _labels,
    _tap,
    _title,
    composed_client,
)

PICK = {"en": "Pick an option or type your answer", "zh": "选一个，或者直接输入"}


@pytest.fixture(params=["fixture", "openai"])
def client(request, composed_client, monkeypatch):  # noqa: F811
    """The synthetic catalog (two mains, three vegetables, a soup), in each parser mode."""
    if request.param == "openai":
        stub_openai(monkeypatch)
    composed_client.mode = request.param
    return composed_client


def say(client, session: dict, message: str) -> dict:
    response = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def typed(client, session: dict, message: str) -> dict:
    """Typed into the composer while a question with choices is open: sent as the answer's free text."""
    interaction = session["pending_interaction"]
    response = client.post(
        f"/api/agent/sessions/{session['id']}/interactions",
        json={
            "question_id": interaction["question_id"],
            "free_text": message,
            "context_version": interaction["context_version"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def reply_of(session: dict) -> str:
    return session["messages"][-1]["content"]


def usual_meals(client) -> set[str]:
    return set(client.get("/api/household-profiles/current").json()["current"]["plan_shape"]["meals"])


def latest_run(client, session: dict) -> dict:
    return client.get(f"/api/agent/sessions/{session['id']}/runs").json()["items"][0]


def lunch_added(client, message: str) -> tuple[dict, dict]:
    """A dinner week given lunch in the conversation, confirmed: "should new weeks plan meals this way too?"."""
    session, _ = _conversation_week(client)
    asked = say(client, session, message)
    assert asked["pending_replan"]["event_type"] == "CHANGE_SHAPE", reply_of(asked)
    applied = client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()
    assert applied["session"]["pending_interaction"]["field_path"] == "plan_shape.keep"
    return applied["session"], applied["plan"]


def day_on(plan: dict, weekday_number: int) -> int:
    return next(
        d["day_index"] for d in plan["days"] if date.fromisoformat(d["planned_date"]).weekday() == weekday_number
    )


# P1: "keep this week's meals as the usual ones?" is answered only by an answer.


@pytest.mark.parametrize(
    ("answer", "keep"),
    [
        ("yes", True),
        ("Yes please!", True),
        ("Keep it as our usual", True),  # what the tap sends
        ("以后也这样吧", True),
        ("好的", True),
        ("no", False),
        ("No thanks.", False),
        ("Just this week", False),  # what the tap sends
        ("只这周", False),
        ("不用了", False),
        # Not answers: new instructions whose words used to be read as one.
        ("no lunch on weekdays, keep the weekend", None),
        ("noodles on Friday", None),
        ("keep Monday's dinner as it is", None),
        ("工作日不用做午饭，周末照常", None),
        ("不要午饭", None),
        ("只做一道菜", None),
    ],
)
def test_only_a_whole_answer_answers_keep_the_shape(answer, keep):
    assert keep_shape_answer(answer) is keep


@pytest.mark.parametrize(
    ("first", "message", "lang"),
    [
        ("Also plan lunch", "no lunch on weekdays, keep the weekend", "en"),
        ("午饭也安排一下", "工作日不用做午饭，周末照常", "zh"),
    ],
)
def test_a_new_instruction_while_keep_the_shape_is_asked_is_handled_and_the_question_lapses(
    client, first, message, lang
):
    """The walkthrough: "no lunch on weekdays, keep the weekend" got "OK, only this week changes" and nothing
    changed. It is a new instruction: previewed, the question gone, the household's usual meals untouched."""
    session, plan = lunch_added(client, first)

    asked = say(client, session, message)

    change = asked["pending_replan"]
    assert change is not None and change["event_type"] == "CHANGE_SHAPE", reply_of(asked)
    weekdays = sorted({d["day_index"] for d in plan["days"] if date.fromisoformat(d["planned_date"]).weekday() < 5})
    assert (change["shape_change"]["meal_type"], change["shape_change"]["roles"]) == ("lunch", None)
    assert change["shape_change"]["day_indexes"] == weekdays
    assert asked["pending_interaction"] is None  # the question lapsed: this week only
    assert ("工作日" in reply_of(asked)) == (lang == "zh")
    assert usual_meals(client) == {"dinner"}


def test_keep_mondays_dinner_while_keep_the_shape_is_asked_locks_it_and_saves_nothing(client):
    session, plan = lunch_added(client, "Also plan lunch")

    asked = say(client, session, "keep Monday's dinner as it is")

    assert asked["pending_replan"]["event_type"] == "LOCK_MEAL", reply_of(asked)
    monday = day_on(plan, 0)
    dinner = {d["entry_id"] for d in plan["days"] if d["day_index"] == monday and d["meal_type"] == "dinner"}
    assert {item["entry_id"] for item in asked["pending_replan"]["meal_entries"]} == dinner
    assert usual_meals(client) == {"dinner"}


def test_a_swap_for_noodles_while_keep_the_shape_is_asked_is_a_swap(client):
    session, _ = lunch_added(client, "Also plan lunch")

    asked = say(client, session, "Swap Friday's dinner for noodles")

    assert asked["pending_replan"]["event_type"] == "REPLACE_MEAL", reply_of(asked)
    assert usual_meals(client) == {"dinner"}


@pytest.mark.parametrize(("answer", "kept"), [("yes", True), ("以后也这样", True), ("no", False), ("只这周", False)])
def test_a_typed_answer_to_keep_the_shape_still_answers_it(composed_client, answer, kept):  # noqa: F811
    session, _ = lunch_added(composed_client, "Also plan lunch")

    answered = say(composed_client, session, answer)

    assert answered["pending_replan"] is None and answered["pending_interaction"] is None
    assert usual_meals(composed_client) == ({"dinner", "lunch"} if kept else {"dinner"})
    # An answer is a turn done, not one that went wrong or still waits.
    assert latest_run(composed_client, session)["status"] == "committed"


# P2: an open "which dish?" does not swallow the next instruction.


def test_a_new_request_while_which_dish_is_asked_is_handled_and_the_question_goes(client):
    session, _ = _conversation_week(client)
    asked = say(client, session, "Swap tomorrow's dinner")
    assert asked["clarification_questions"] and "which one" in reply_of(asked)

    lunch = typed(client, asked, "also plan lunch")

    assert lunch["pending_replan"] is not None and lunch["pending_replan"]["event_type"] == "CHANGE_SHAPE"
    assert lunch["pending_replan"]["shape_change"]["meal_type"] == "lunch", reply_of(lunch)
    assert lunch["clarification_questions"] == [] and lunch["replan_draft"]["event_type"] == "CHANGE_SHAPE"


def test_an_answer_to_which_dish_still_answers_it(client):
    session, _ = _conversation_week(client)
    asked = say(client, session, "Swap tomorrow's dinner")

    answered = say(client, asked, "no, the vegetable")

    assert answered["pending_replan"]["event_type"] == "REPLACE_MEAL", reply_of(answered)
    assert answered["pending_replan"]["before_entry"]["role_id"] == "vegetable"


def test_a_shape_request_stands_on_its_own_only_when_it_names_the_meal_or_adds_a_dish(composed_client):  # noqa: F811
    _, plan = _conversation_week(composed_client)
    week = WeeklyMealPlanResponse.model_validate(plan)

    def stands(message):
        return read_shape_change(message, plan=week, day_indexes=None).stands_alone

    assert stands("also plan lunch") and stands("no lunch on weekdays") and stands("add a soup")
    assert stands("no side dish tonight")
    # "No vegetable" answers "which dish?" (the vegetable) as much as it takes the vegetable off: while a
    # question is open, it answers the question.
    assert not stands("no vegetable")


# P7: keeping a named meal keeps every dish of it; "don't" is never a wish for food.


@pytest.mark.parametrize(
    ("message", "lang"),
    [("Don't change Monday's dinner", "en"), ("别动周一的晚饭", "zh"), ("周一的晚饭不要改", "zh")],
)
def test_keeping_a_named_meal_keeps_every_dish_of_it_in_one_preview(client, message, lang):
    session, plan = _conversation_week(client)
    monday = day_on(plan, 0)
    dishes = [d for d in plan["days"] if d["day_index"] == monday]
    assert len(dishes) == 2

    asked = say(client, session, message)

    change = asked["pending_replan"]
    assert change is not None and change["event_type"] == "LOCK_MEAL", reply_of(asked)
    assert sorted(item["entry_id"] for item in change["meal_entries"]) == sorted(d["entry_id"] for d in dishes)
    titles = [item["recipe_title"] for item in change["meal_entries"]]
    day = weekday(date.fromisoformat(dishes[0]["planned_date"]), lang)
    if lang == "en":
        assert reply_of(asked) == (
            f"Keep the dinner on {day} as it is ({titles[0]} and {titles[1]})? Nothing changes until you confirm."
        )
    else:
        assert reply_of(asked) == f"保留{day}的晚餐不变（{titles[0]}和{titles[1]}）？确认之前什么都不会改。"

    applied = client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]
    assert {d["entry_id"] for d in applied["days"] if d["is_locked"]} == {d["entry_id"] for d in dishes}


def test_keeping_a_named_dish_keeps_that_dish_only(client):
    session, plan = _conversation_week(client)
    monday = day_on(plan, 0)
    vegetable = next(d for d in plan["days"] if d["day_index"] == monday and d["role_id"] == "vegetable")

    asked = say(client, session, "Lock Monday's vegetable")

    assert asked["pending_replan"]["before_entry"]["entry_id"] == vegetable["entry_id"], reply_of(asked)
    assert asked["pending_replan"]["meal_entries"] == []
    assert reply_of(asked) == f"Keep {vegetable['recipe']['title']} as it is? Nothing changes until you confirm."


def test_dont_is_never_read_as_a_wish_for_food():
    assert wanted("Don't change Monday's dinner") is None
    assert wanted("别动周一的晚饭") is None
    assert wanted("Swap Monday's dinner, I don't want fish") is None  # ordering by "fish" would bring fish
    assert wanted("Can Wednesday be fish instead?") == "fish"


def test_a_title_names_its_dish_whatever_other_words_name(composed_client):  # noqa: F811
    """The walkthrough's "Swap the Hot And Sour Cabbage Salad on day 5" swapped day 5's main: the title named
    one dish, "salad" named the day's vegetables, and the main was taken as what a wish would swap."""
    _, plan = _conversation_week(composed_client)
    week = WeeklyMealPlanResponse.model_validate(plan)
    vegetable = next(d for d in week.days if d.day_index == 3 and d.role_id == "vegetable")

    draft, questions = AgentReplanInterpreter().parse(
        f"Swap the {vegetable.recipe.title} on day 3, the main stays", plan=week, current=AgentReplanDraft()
    )

    assert (draft.entry_id, questions) == (vegetable.entry_id, [])


# P15: a second dish of a kind the meal has is asked about first.


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_a_soup_asked_for_a_dinner_that_has_one_asks_first_naming_it(composed_client, lang):  # noqa: F811
    _broccoli_soup()
    session, plan = _conversation_week(composed_client, minutes=240)  # four dishes take more than 90 minutes
    friday = _friday(plan)
    say(composed_client, session, "Add a soup on Friday")
    week = composed_client.post(f"/api/agent/sessions/{session['id']}/replan/confirm").json()["plan"]
    soup = _title(_dishes(week, friday)["soup"])
    message = "Add a soup to Friday dinner" if lang == "en" else "周五晚餐加个汤"

    asked = say(composed_client, session, message)

    assert asked["pending_replan"] is None
    if lang == "en":
        assert reply_of(asked) == f"Dinner on Friday already has {soup}: add another soup, or swap it?"
        add, swap = "Add another soup", f"Swap the {soup}"
    else:
        assert reply_of(asked) == f"周五的晚餐已经有{soup}了：再加一道汤，还是换掉它？"
        add, swap = "再加一道汤", f"换掉{soup}"
    assert _labels(asked) == [add, swap]
    assert asked["pending_interaction"]["prompt"] == PICK[lang]

    swapped = _tap(composed_client, asked, swap)
    assert swapped["pending_replan"]["event_type"] == "REPLACE_MEAL", reply_of(swapped)
    assert swapped["pending_replan"]["before_entry"]["recipe_title"] == soup
    composed_client.post(f"/api/agent/sessions/{session['id']}/replan/discard")

    added = _tap(composed_client, say(composed_client, session, message), add)
    change = added["pending_replan"]
    assert change is not None and change["event_type"] == "CHANGE_SHAPE", reply_of(added)
    assert [d["role_id"] for d in change["shape_change"]["added"]] == ["soup-2"]


# P20: skips and discards in plain words.


def test_a_skip_says_what_it_does_to_the_groceries_never_a_bare_zero(client):
    session, plan = _conversation_week(client)
    said = []
    for day in sorted({d["day_index"] for d in plan["days"]}):
        asked = say(client, session, f"Skip day {day}'s vegetable")
        change, reply = asked["pending_replan"], reply_of(asked)
        assert change["event_type"] == "CANCEL_MEAL", reply
        client.post(f"/api/agent/sessions/{session['id']}/replan/discard")
        assert "S$0.00" not in reply and "+S$" not in reply, reply
        if change["purchase_total_delta_sgd"] < 0:
            assert f"That takes S${-change['purchase_total_delta_sgd']:.2f} off the groceries." in reply
        else:
            assert "Groceries stay the same" in reply, reply
        said.append(reply)
    # Some vegetable's whole packages are still bought for its other days: said, with who uses them.
    assert any("still used by" in reply for reply in said), said


@pytest.mark.parametrize(
    ("message", "discarded"),
    [("Swap tomorrow's main", "OK, your week stays as it is."), ("换掉明天的主菜", "好的，这周保持原样。")],
)
def test_keep_as_is_says_the_week_stays(client, message, discarded):
    session, _ = _conversation_week(client)
    asked = say(client, session, message)
    assert asked["pending_replan"] is not None, reply_of(asked)

    kept = client.post(f"/api/agent/sessions/{session['id']}/replan/discard").json()

    assert reply_of(kept) == discarded


# P5: the household is offered fewer people only when that week is backed and cheaper.


@pytest.mark.parametrize(
    ("two", "labels"),
    [
        (40.2, ["Use S$24 for the week"]),  # the walkthrough's "2 people at S$41" beside S$24 for 4
        (23.5, ["Use S$24 for the week"]),  # no cheaper
        (15.3, ["Use S$24 for the week", "2 people at S$16 a week"]),
        (9.5, ["Use S$24 for the week", "Plan for 2 people"]),
        (None, ["Use S$24 for the week"]),  # no week found for two
    ],
)
def test_fewer_people_are_offered_only_when_a_real_week_backs_it_for_less(two, labels):
    constraints = AgentConstraintState(household_size=4, weekly_budget_sgd=10)

    refusal = _budget_short(
        23.36, constraints, "en", lambda **changes: two if changes == {"household_size": 2} else None
    )

    assert [label for label, _ in refusal.options] == labels
    assert refusal.text == (
        "S$10 a week for 4 people comes to about S$0.36 a person a meal (7 meals). "
        "The cheapest week I could find costs S$23.36."
    )
    chinese = _budget_short(23.36, constraints, "zh", lambda **changes: None)
    assert chinese.text == "4 个人一周 S$10，每人每餐大约只有 S$0.36（一周 7 餐）。我能找到的最便宜的一周要 S$23.36。"


# P12: the composer's hint is short; the question is the reply above it.


@pytest.mark.parametrize(
    ("message", "lang"), [("Plan a week for 4 for S$10 total", "en"), ("我们4个人，一周一共10新币", "zh")]
)
def test_a_refusals_choices_hint_is_short(client, message, lang):
    session = client.post("/api/agent/sessions", json={"message": message}).json()

    assert session["pending_interaction"]["options"], reply_of(session)
    assert session["pending_interaction"]["prompt"] == PICK[lang]


def test_a_planned_weeks_questions_hint_is_short(client):
    session, _ = _conversation_week(client)
    asked = say(client, session, "Swap tomorrow's dinner")
    assert asked["pending_interaction"]["prompt"] == PICK["en"] != reply_of(asked)


def test_keep_the_shapes_hint_is_short(client):
    keep, _ = lunch_added(client, "Also plan lunch")

    assert keep["pending_interaction"]["prompt"] == PICK["en"]


# P18: only a turn that went wrong is degraded.


@pytest.mark.parametrize(("message", "status"), [("hello", "committed"), ("我想吃点好的", "needs_clarification")])
def test_a_greeting_or_a_question_back_is_not_degraded(client, message, status):
    session = client.post("/api/agent/sessions", json={"message": message}).json()

    assert session["latest_run"]["status"] == status


def test_a_greeting_beside_a_planned_week_is_not_degraded(client):
    session, _ = _conversation_week(client)

    greeted = say(client, session, "thanks")

    assert latest_run(client, greeted)["status"] == "committed"
