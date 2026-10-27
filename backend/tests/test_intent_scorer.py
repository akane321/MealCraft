"""The class and field scorer for intent cases, checked on invented gold only (draft; needs independent review)."""

from __future__ import annotations

import pytest

from app.evaluation.conversation_adapter import PlanDish, PlanMeal, PlanOutput, UnifiedOutput
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


def test_list_fields_compare_as_sets_ignoring_case_space_and_order():
    expected = gold(excluded_ingredients=["pork", "shrimp"])
    got = out(plan=plan(), request_fields={"excluded_ingredients": [" Shrimp", "PORK"]})
    assert score_intent(expected, got).outcome == "pass"
    short = out(plan=plan(), request_fields={"excluded_ingredients": ["pork"]})
    assert score_intent(expected, short).outcome == "fail"


def test_halal_required_true_must_be_stated_and_false_is_satisfied_by_silence():
    assert score_intent(gold(halal_required=True), out(plan=plan(), request_fields={})).outcome == "fail"
    assert (
        score_intent(gold(halal_required=True), out(plan=plan(), request_fields={"requires_halal": True})).outcome
        == "pass"
    )
    assert score_intent(gold(halal_required=False), out(plan=plan(), request_fields={})).outcome == "pass"


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


def test_reference_answers_and_rubrics_are_never_read():
    base = score_intent(gold(), out(plan=plan()))
    changed = {**gold(), "reference_answer": "something else", "rubric": ["another"]}
    assert score_intent(changed, out(plan=plan())) == base
    assert "SECRET" not in repr(base)


def test_a_gold_without_an_action_is_rejected():
    with pytest.raises(ValueError, match="action"):
        score_intent({"kind": "intent", "disposition": "feasible", "expected_fields": {}}, out(plan=plan()))
