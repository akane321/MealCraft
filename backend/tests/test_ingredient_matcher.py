"""Ingredient suggestions for words the planner cannot check: offered for a tap, never applied."""

from app.agent.ingredient_matcher import IngredientMatcher, catalog_aliases, catalog_vectors, fold
from app.agent.parser import ConstraintVocabulary, align_to_vocabulary
from app.agent.workflow import AgentConstraintWorkflow
from app.orchestration.contracts import InteractionType
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState
from app.schemas.recommendation import AvailableIngredientInput
from app.services.agent import AgentSessionService

NAMES = {"wine_cooking": "cooking wine", "rice_wine": "rice wine", "green_onion": "green onion", "pork": "pork"}
# Toy vectors on three axes: wine-ness, onion-ness, meat-ness.
VECTORS = {"wine_cooking": [1, 0, 0], "rice_wine": [0.9, 0.1, 0], "green_onion": [0, 1, 0], "pork": [0, 0, 1]}
QUERIES = {"shaoxing": [0.95, 0.05, 0], "scallion": [0.1, 0.9, 0]}


def embed(texts):
    return [QUERIES[text] for text in texts]


def test_embedding_ranks_by_meaning_not_spelling():
    matcher = IngredientMatcher(NAMES, vectors=VECTORS, embed=embed)
    assert matcher.suggest("scallion", limit=2) == ["green_onion", "rice_wine"]
    assert matcher.suggest("shaoxing", limit=2) == ["wine_cooking", "rice_wine"]


def test_an_exact_other_name_goes_first_even_when_the_embedding_disagrees():
    matcher = IngredientMatcher(NAMES, vectors=VECTORS, embed=embed, aliases={"green_onion": ["葱", "Scallion"]})
    assert matcher.suggest("shaoxing")[0] == "wine_cooking"
    assert matcher.suggest("scallion")[0] == "green_onion"
    matcher = IngredientMatcher(
        NAMES, vectors=VECTORS, embed=lambda texts: [[1, 0, 0]], aliases={"green_onion": ["葱"]}
    )
    assert matcher.suggest("葱")[0] == "green_onion"


def test_a_failed_embedding_call_falls_back_to_spelling():
    def broken(texts):
        raise RuntimeError("no network")

    matcher = IngredientMatcher(NAMES, vectors=VECTORS, embed=broken)
    assert matcher.suggest("cooking wine")[0] == "wine_cooking"
    assert IngredientMatcher(NAMES).suggest("green onions")[0] == "green_onion"  # no vectors at all


def test_fold_meets_accents_case_and_underscores():
    assert fold("Jalapeño") == fold("jalapeno") == "jalapeno"
    assert fold("green_onion") == "green onion"
    assert fold("葱") == "葱"


def test_the_committed_vectors_and_aliases_cover_the_same_ingredients():
    vectors, aliases = catalog_vectors(), catalog_aliases()
    assert len(vectors) > 700
    assert set(aliases) <= set(vectors)
    assert len({len(v) for v in vectors.values()}) == 1


VOCABULARY = ConstraintVocabulary(
    ingredients=frozenset(NAMES), matcher=IngredientMatcher(NAMES, vectors=VECTORS, embed=embed)
)


def test_unmatched_words_carry_their_field_and_proposals_but_are_not_applied():
    extraction = AgentConstraintExtraction(
        household_size=2,
        excluded_ingredients=["shaoxing"],
        allergens=["lactose"],
        available_ingredients=[AvailableIngredientInput(normalized_name="scallion", quantity=None, unit=None)],
    )
    aligned = align_to_vocabulary(extraction, VOCABULARY)

    assert aligned.excluded_ingredients is None and aligned.available_ingredients is None
    by_term = {item.term: item for item in aligned.unmatched_suggestions}
    assert by_term["shaoxing"].field == "excluded_ingredients"
    assert by_term["shaoxing"].options[0] == "wine_cooking"
    assert by_term["scallion"].field == "available_ingredients"
    assert by_term["scallion"].options[0] == "green_onion"
    assert by_term["lactose"].options == []  # allergens are a closed list the household reads in full


def test_the_model_is_never_shown_the_suggestions_field():
    assert "unmatched_suggestions" not in AgentConstraintExtraction.model_json_schema()["properties"]


class _Parser:
    provider = "fixture"

    def parse(self, message, *, current, acknowledged_unknowns, history):
        return align_to_vocabulary(
            AgentConstraintExtraction(household_size=2, excluded_ingredients=["shaoxing"]), VOCABULARY
        )


def test_the_question_offers_the_proposals_as_one_tap_choices_and_the_answer_is_an_exclusion():
    state = AgentConstraintWorkflow(_Parser()).run(
        "Two of us, no shaoxing.", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    assert "Did you mean one of these: wine cooking" in state["clarification_questions"][0]

    interaction = BoundedAgentOrchestrator._interaction_for(
        state["missing_fields"],
        question=state["clarification_questions"][0],
        context_version=2,
        suggestions={item["term"]: item for item in state["extraction"]["unmatched_suggestions"]},
    )
    assert interaction.type is InteractionType.SINGLE_SELECT
    assert interaction.allow_free_text
    assert interaction.options[0].value == "wine_cooking"

    message = AgentSessionService._interaction_value_as_message(interaction, "wine_cooking")
    assert message.startswith("Exclude wine_cooking")
