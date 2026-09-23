"""The agent writes constraints in the catalog's own words, and asks about any it cannot match."""

from app.agent.parser import ConstraintVocabulary, align_to_vocabulary
from app.agent.workflow import AgentConstraintWorkflow
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from app.schemas.recommendation import AvailableIngredientInput

VOCABULARY = ConstraintVocabulary(ingredients=frozenset({"wine_cooking", "pork", "mushroom"}))


def test_only_checkable_words_become_constraints_and_the_rest_are_set_aside():
    extraction = AgentConstraintExtraction(
        excluded_ingredients=["wine_cooking", "cooking wine"],
        allergens=["dairy", "lactose"],
        available_ingredients=[AvailableIngredientInput(normalized_name="mushrooms", quantity=None, unit=None)],
    )

    aligned = align_to_vocabulary(extraction, VOCABULARY)

    assert aligned.excluded_ingredients == ["wine_cooking"]
    assert aligned.allergens == ["dairy"]
    assert aligned.available_ingredients is None
    assert aligned.unmatched_terms == ["cooking wine", "lactose", "mushrooms"]


class _Parser:
    provider = "fixture"

    def parse(self, message, *, current, acknowledged_unknowns, history):
        return align_to_vocabulary(
            AgentConstraintExtraction(household_size=2, excluded_ingredients=["cooking wine"]), VOCABULARY
        )


def test_an_unmatched_exclusion_is_asked_about_and_holds_the_plan_back():
    state = AgentConstraintWorkflow(_Parser()).run(
        "Two of us, no cooking wine.", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )

    assert state["status"] == "collecting"
    assert state["missing_fields"] == ["unmatched.cooking wine"]
    assert "cooking wine" in state["assistant_message"]
    assert state["merged_constraints"]["excluded_ingredients"] == []
