"""'No seafood' is a planning restriction over every fish and shellfish (the landing page's own example)."""

import pytest

from app.agent.parser import RuleBasedConstraintParser, apply_rule_seafood, excludes_seafood
from app.orchestration.contracts import ScopeClass
from app.orchestration.scope_classifier import OpenAIScopeClassifier, ScopePrediction
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState


class QuestionModel:
    """A model that reads a planning request as a food question."""

    def invoke(self, prompt: str) -> ScopePrediction:
        del prompt
        return ScopePrediction(scope_class=ScopeClass.DOMAIN_QUESTION, intent="food_question")


@pytest.mark.parametrize(
    "message",
    ["Dinner tonight for two, no seafood", "Dinner tonight for two, no seafood.", "dinners this week without seafood"],
)
def test_a_request_without_seafood_is_planned_even_when_the_model_calls_it_a_question(message: str) -> None:
    classifier = OpenAIScopeClassifier(api_key="test", model="test-model", structured_model=QuestionModel())
    decision = classifier.classify(message)
    assert decision.scope_class is ScopeClass.DOMAIN_ACTION and decision.should_mutate_state


def test_a_question_about_seafood_stays_a_question() -> None:
    classifier = OpenAIScopeClassifier(api_key="test", model="test-model", structured_model=QuestionModel())
    assert classifier.classify("Is seafood good for children?").scope_class is ScopeClass.DOMAIN_QUESTION


@pytest.mark.parametrize(
    "message", ["Dinner tonight for two, no seafood", "晚餐两个人，不吃海鲜", "We don't eat seafood"]
)
def test_no_seafood_keeps_every_fish_and_shellfish_off_the_table(message: str) -> None:
    extraction = RuleBasedConstraintParser().parse(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    assert {"fish", "shellfish"} <= set(extraction.allergens or [])
    assert not {"seafood", "seafood_mix"} & set(extraction.excluded_ingredients or [])


def test_a_model_reading_of_seafood_mix_becomes_fish_and_shellfish() -> None:
    extraction = AgentConstraintExtraction(
        excluded_ingredients=["seafood_mix", "pork"], allergens=["peanut"], unmatched_terms=["shellfish", "kale chips"]
    )
    apply_rule_seafood(extraction, "Dinner tonight for two, no seafood")
    assert extraction.allergens == ["fish", "peanut", "shellfish"]
    assert extraction.excluded_ingredients == ["pork"]
    assert extraction.unmatched_terms == ["kale chips"]


@pytest.mark.parametrize(
    "message",
    [
        "no pork and seafood",
        "don't eat pork or seafood",
        "不吃猪肉和海鲜",
        "I'm allergic to seafood",
        "我对海鲜过敏",
        "We don’t eat seafood",
    ],
)
def test_seafood_in_a_list_or_as_an_allergy_is_ruled_out(message: str) -> None:
    assert excludes_seafood(message)


@pytest.mark.parametrize(
    "message",
    [
        "no seafood allergy",
        "we don't have any seafood allergies",
        "我没有海鲜过敏",
        "冰箱里没有海鲜",
        "Is seafood good for children?",
        "no pork, seafood is fine",
    ],
)
def test_saying_seafood_without_ruling_it_out_changes_nothing(message: str) -> None:
    assert not excludes_seafood(message)


def test_liking_seafood_is_no_restriction() -> None:
    extraction = AgentConstraintExtraction(excluded_ingredients=None, allergens=None)
    apply_rule_seafood(extraction, "We love seafood, plan dinners for two")
    assert extraction.allergens is None and extraction.excluded_ingredients is None
