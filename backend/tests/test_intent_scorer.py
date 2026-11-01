"""The class and field scorer for intent cases, checked on invented gold only (draft; needs independent review)."""

from __future__ import annotations

import pytest

from app.evaluation.conversation_adapter import PlanDish, PlanMeal, PlanOutput, UnifiedOutput
from app.evaluation.field_mapping import NO_COOKING_TIME_LIMIT
from app.evaluation.intent_scorer import score_intent


def gold(action="plan", disposition="feasible", **expected):
    return {
        "kind": "intent",
        "disposition": disposition,
        "expected_fields": {"action": action, **expected},
        "clarification_fields": ["household_size"],
        "reference_answer": "SECRET REFERENCE",
        "rubric": ["SECRET RUBRIC"],
    }


def plan():
    meal = PlanMeal(date="2026-10-23", meal_type="dinner", dishes=[PlanDish(name="Invented bowl")])
    return PlanOutput(meals=[meal])


def out(**changes):
    return UnifiedOutput(**changes)


def test_the_observed_action_must_match_the_expected_one():
    assert score_intent(gold("plan"), out(plan=plan())).outcome == "pass"
    assert score_intent(gold("clarify", "clarify"), out(clarification=["How many people?"])).outcome == "pass"
    assert score_intent(gold("refuse", "refuse"), out(refusal="I cannot help with that.")).outcome == "pass"
    assert score_intent(gold("food_qa", "answer"), out(answer="Rice keeps for two days.")).outcome == "pass"
    wrong = score_intent(gold("clarify", "clarify"), out(plan=plan()))
    assert wrong.outcome == "fail" and "action" in wrong.reasons[0]


def test_a_refusal_or_a_question_next_to_a_plan_is_not_a_clean_refusal_or_clarification():
    assert score_intent(gold("refuse", "refuse"), out(refusal="No.", plan=plan())).outcome == "fail"
    assert score_intent(gold("clarify", "clarify"), out(clarification=["Which day?"], plan=plan())).outcome == "fail"


def test_stated_fields_are_compared_and_a_missing_one_fails():
    expected = gold(allergens=["peanut"], household_size=2)
    assert (
        score_intent(expected, out(plan=plan(), request_fields={"household_size": 2, "allergens": ["Peanut "]})).outcome
        == "pass"
    )
    wrong = score_intent(expected, out(plan=plan(), request_fields={"household_size": 3, "allergens": ["peanut"]}))
    assert wrong.outcome == "fail" and any("household_size" in r for r in wrong.reasons)
    missing = score_intent(expected, out(plan=plan(), request_fields={"household_size": 2}))
    assert missing.outcome == "fail" and any("not stated" in r for r in missing.reasons)


def test_list_fields_compare_as_sets_ignoring_case_space_order_and_repeats():
    expected = gold(excluded_ingredients=["pork", "shrimp"])
    got = out(plan=plan(), request_fields={"excluded_ingredients": [" Shrimp", "PORK"]})
    assert score_intent(expected, got).outcome == "pass"
    short = out(plan=plan(), request_fields={"excluded_ingredients": ["pork"]})
    assert score_intent(expected, short).outcome == "fail"
    repeated = out(plan=plan(), request_fields={"excluded_ingredients": ["pork", "Pork", "shrimp"]})
    assert score_intent(expected, repeated).outcome == "pass"
    assert (
        score_intent(
            gold(excluded_ingredients=["pork", "pork"]),
            out(plan=plan(), request_fields={"excluded_ingredients": ["pork"]}),
        ).outcome
        == "pass"
    )


def test_a_boolean_never_matches_a_number():
    assert (
        score_intent(gold(household_size=True), out(plan=plan(), request_fields={"household_size": 1})).outcome
        == "fail"
    )
    assert (
        score_intent(gold(household_size=1), out(plan=plan(), request_fields={"household_size": 1})).outcome == "pass"
    )
    stated_halal = out(plan=plan(), request_fields={"requires_halal": True})
    assert score_intent(gold(halal_required=1), stated_halal).outcome == "fail"
    assert score_intent(gold(halal_required=False), stated_halal).outcome == "fail"


def test_halal_required_true_must_be_stated_and_false_is_satisfied_by_silence():
    assert score_intent(gold(halal_required=True), out(plan=plan(), request_fields={})).outcome == "fail"
    assert (
        score_intent(gold(halal_required=True), out(plan=plan(), request_fields={"requires_halal": True})).outcome
        == "pass"
    )
    assert score_intent(gold(halal_required=False), out(plan=plan(), request_fields={})).outcome == "pass"


def test_an_empty_expected_value_is_satisfied_by_silence_but_not_by_a_contrary_statement():
    # The echo cannot tell "stated none" from "not stated", so an expected none is met when nothing is echoed.
    silent = out(answer="Rice keeps for two days.")
    for empty in ([], None, {}):
        assert score_intent(gold("food_qa", "answer", allergens=empty), silent).outcome == "pass"
    assert (
        score_intent(gold("food_qa", "answer", excluded_ingredients=[], dietary_requirements=[]), silent).outcome
        == "pass"
    )
    # the no-limit cooking time is met by silence as well, and the product's no-limit echo reads as silence
    no_limit = gold(cooking_time_minutes=NO_COOKING_TIME_LIMIT)
    assert score_intent(no_limit, out(plan=plan(), request_fields={})).outcome == "pass"
    assert (
        score_intent(
            no_limit, out(plan=plan(), request_fields={"max_cooking_time_minutes": NO_COOKING_TIME_LIMIT})
        ).outcome
        == "pass"
    )
    # a stated value against an expected none still fails
    stated = out(plan=plan(), request_fields={"allergens": ["peanut"], "max_cooking_time_minutes": 30})
    assert score_intent(gold(allergens=[]), stated).outcome == "fail"
    assert score_intent(no_limit, stated).outcome == "fail"
    # a non-empty expected value is still not met by silence
    assert score_intent(gold(allergens=["peanut"]), silent).outcome == "fail"
    assert score_intent(gold(household_size=0), out(plan=plan())).outcome == "fail"


def test_what_cannot_be_observed_is_not_scorable_and_never_a_wrong_answer():
    # swap, meal-structure and budget changes are not visible in the output slots
    assert score_intent(gold("swap"), out(plan=plan())).outcome == "not_scorable"
    # a field the product's echo cannot carry
    assert score_intent(gold(pantry=[{"ingredient": "egg"}]), out(plan=plan())).outcome == "not_scorable"
    # a mismatch elsewhere still fails: unknown does not hide a wrong answer
    mixed = score_intent(gold(pantry=[], household_size=2), out(plan=plan(), request_fields={"household_size": 5}))
    assert mixed.outcome == "fail"


def test_other_kinds_are_not_scored_here():
    for kind in ("plan", "qa", "replan", "refusal"):
        assert score_intent({**gold(), "kind": kind}, out(plan=plan())).outcome == "not_scorable"


def test_the_kind_is_checked_before_the_action_so_other_kinds_without_one_do_not_raise():
    assert score_intent({"kind": "planning", "expected_fields": {}}, out(plan=plan())).outcome == "not_scorable"
    assert score_intent({"kind": "qa"}, out(answer="Rice keeps for two days.")).outcome == "not_scorable"
    assert score_intent({"kind": "planning", "expected_fields": None}, out()).outcome == "not_scorable"


def test_an_expected_refusal_the_product_can_only_state_as_a_reply_or_question_is_not_scorable():
    # A limits-type refusal (an impossible budget and the like) reaches the output as an answer or a question.
    limits = gold("refuse", "refuse")
    as_answer = score_intent(limits, out(answer="That budget is below the cheapest week."))
    assert as_answer.outcome == "not_scorable" and "limits refusal" in as_answer.reasons[0]
    assert score_intent(limits, out(clarification=["Could you raise the budget?"])).outcome == "not_scorable"
    # a plan is still not a refusal, and a field that differs still fails
    assert score_intent(limits, out(plan=plan())).outcome == "fail"
    assert score_intent(limits, out()).outcome == "fail"
    mixed = gold("refuse", "refuse", household_size=2)
    assert score_intent(mixed, out(answer="No.", request_fields={"household_size": 5})).outcome == "fail"
    # a refusal the product does state as one is scored as before, and a refusal elsewhere does not become unscorable
    assert (
        score_intent(limits, out(refusal="I cannot help with that.", answer="I cannot help with that.")).outcome
        == "pass"
    )
    assert score_intent(gold("plan"), out(answer="That budget is below the cheapest week.")).outcome == "fail"


def test_reference_answers_and_rubrics_are_never_read():
    base = score_intent(gold(), out(plan=plan()))
    changed = {**gold(), "reference_answer": "something else", "rubric": ["another"]}
    assert score_intent(changed, out(plan=plan())) == base
    assert "SECRET" not in repr(base)


def test_a_gold_without_an_action_is_rejected():
    with pytest.raises(ValueError, match="action"):
        score_intent({"kind": "intent", "disposition": "feasible", "expected_fields": {}}, out(plan=plan()))
