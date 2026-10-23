from datetime import UTC, datetime

import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.orchestration.capabilities import allowed_tools_for, authorize_tool_call
from app.orchestration.contracts import (
    ActionReceipt,
    ClaimVerificationMode,
    EvidenceFact,
    InteractionAnswer,
    ResponseClaim,
    ScopeClass,
    ScopeDecision,
    ToolEffect,
    ToolRunStatus,
)
from app.orchestration.grounding import verify_structured_claims
from app.orchestration.interactions import (
    InteractionAnswerError,
    household_size_interaction,
    validate_interaction_answer,
)
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.schemas.agent import AgentConstraintState


def test_movie_request_is_out_of_scope_and_cannot_mutate_state() -> None:
    decision = ReferenceScopePolicy().classify("我明天看什么电影？")

    assert decision.scope_class is ScopeClass.OUT_OF_SCOPE
    assert decision.reason_code == "OUT_OF_DOMAIN"
    assert decision.should_mutate_state is False
    assert decision.should_call_tools is False


def test_mixed_movie_snack_request_keeps_only_supported_capability() -> None:
    decision = ReferenceScopePolicy().classify("帮我规划看电影时的零食，再推荐一部电影")

    assert decision.scope_class is ScopeClass.PARTIALLY_SUPPORTED
    assert decision.detected_intents == ["create_plan"]
    assert decision.unsupported_segments


def test_medical_treatment_request_is_restricted() -> None:
    decision = ReferenceScopePolicy().classify("请为我的糖尿病设计一个治疗饮食")

    assert decision.scope_class is ScopeClass.RESTRICTED
    assert decision.reason_code == "MEDICAL_TARGET_DERIVATION_NOT_ALLOWED"


def test_non_medical_health_preference_remains_supported() -> None:
    decision = ReferenceScopePolicy().classify("I have diabetes and want low sugar recipes.")

    assert decision.scope_class is ScopeClass.DOMAIN_ACTION
    assert decision.should_mutate_state is True


def test_grounded_domain_question_does_not_mutate_plan_state() -> None:
    decision = ReferenceScopePolicy().classify("Why was this recipe selected?")

    assert decision.scope_class is ScopeClass.DOMAIN_QUESTION
    assert decision.should_mutate_state is False
    assert decision.should_call_tools is False
    assert decision.reason_code == "GROUNDED_DOMAIN_QUESTION_DEFERRED"


def test_saved_plan_nutrition_question_routes_to_read_only_tool() -> None:
    decision = ReferenceScopePolicy().classify("How much protein is in my meal plan?")

    assert decision.scope_class is ScopeClass.DOMAIN_QUESTION
    assert decision.detected_intents == ["answer_food_question"]
    assert decision.should_call_tools is True
    assert decision.should_mutate_state is False
    assert decision.reason_code == "GROUNDED_SAVED_PLAN_QUESTION"


def test_food_question_context_handler_receives_current_hard_constraints() -> None:
    current = AgentConstraintState(allergens=["peanut"], excluded_ingredients=["pork"], requires_halal=True)
    seen = {}
    decision = ScopeDecision(
        scope_class=ScopeClass.DOMAIN_QUESTION,
        detected_intents=["answer_food_question"],
        supported_segments=["What can I use instead of butter?"],
        should_call_tools=True,
        reason_code="GROUNDED_DOMAIN_QUESTION",
    )

    def answer(message, lang, constraints):
        seen.update(message=message, lang=lang, constraints=constraints)
        return "Filtered substitute answer"

    orchestrator = BoundedAgentOrchestrator(
        RuleBasedConstraintParser(),
        scope_classifier=type("Classifier", (), {"classify": lambda _self, _message, history: decision})(),
        food_question_context_handler=answer,
    )
    outcome = orchestrator.process(
        "What can I use instead of butter?",
        current=current,
        acknowledged_unknowns=[],
        history=[],
        current_status="collecting",
        current_missing_fields=[],
        current_questions=[],
        context_version=1,
    )

    assert outcome.assistant_message == "Filtered substitute answer"
    assert seen == {
        "message": "What can I use instead of butter?",
        "lang": "en",
        "constraints": current,
    }
    assert outcome.state_mutated is False


def test_unconfirmed_capability_cannot_call_commit_tool() -> None:
    preview_tools = allowed_tools_for("create_plan", confirmed=False)
    confirmed_tools = allowed_tools_for("create_plan", confirmed=True)

    assert "generate_plan_preview" in preview_tools
    assert "save_plan_revision" not in preview_tools
    assert "save_plan_revision" in confirmed_tools

    denied = authorize_tool_call("create_plan", "save_plan_revision", confirmed=False)
    allowed = authorize_tool_call("create_plan", "save_plan_revision", confirmed=True)
    cross_capability = authorize_tool_call("find_tutorial", "save_plan_revision", confirmed=True)

    assert denied.allowed is False
    assert denied.reason_code == "CONFIRMATION_REQUIRED"
    assert allowed.allowed is True
    assert allowed.reason_code == "AUTHORIZED"
    assert cross_capability.allowed is False
    assert cross_capability.reason_code == "TOOL_NOT_ALLOWED_FOR_CAPABILITY"


def test_food_question_capability_is_read_only() -> None:
    allowed = allowed_tools_for("answer_food_question")
    read = authorize_tool_call("answer_food_question", "read_saved_plan")
    commit = authorize_tool_call("answer_food_question", "save_plan_revision", confirmed=True)

    assert allowed == {"read_saved_plan", "get_recipe_detail"}
    assert read.allowed is True
    assert read.confirmation_present is False
    assert commit.allowed is False


@pytest.mark.parametrize("message", ["Plan halal meals for this week.", "这周吃清真餐。"])
def test_explicit_halal_request_becomes_a_hard_planning_constraint(message: str) -> None:
    parser = RuleBasedConstraintParser()
    extraction = parser.parse(message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[])
    assert extraction.requires_halal is True


def test_halal_is_not_inferred_without_an_explicit_request() -> None:
    parser = RuleBasedConstraintParser()
    extraction = parser.parse(
        "Plan Malaysian dinners.", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    assert extraction.requires_halal is None


def test_negated_halal_mention_does_not_create_a_halal_requirement() -> None:
    parser = RuleBasedConstraintParser()
    extraction = parser.parse(
        "I don't need halal meals.", current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )
    assert extraction.requires_halal is None


def test_structured_interaction_uses_stable_option_value() -> None:
    interaction = household_size_interaction(question_id="household-1", context_version=3)
    answer = InteractionAnswer(
        question_id="household-1",
        option_ids=["household_size_2"],
        context_version=3,
    )

    values = validate_interaction_answer(interaction, answer, current_context_version=3)

    assert values == [2]


def test_stale_interaction_answer_is_rejected() -> None:
    interaction = household_size_interaction(question_id="household-1", context_version=3)
    answer = InteractionAnswer(
        question_id="household-1",
        option_ids=["household_size_2"],
        context_version=3,
    )

    with pytest.raises(InteractionAnswerError, match="stale conversation"):
        validate_interaction_answer(interaction, answer, current_context_version=4)


def test_duplicate_or_mixed_interaction_answer_is_rejected() -> None:
    interaction = household_size_interaction(question_id="household-1", context_version=3)
    duplicate = InteractionAnswer(
        question_id="household-1",
        option_ids=["household_size_2", "household_size_2"],
        context_version=3,
    )
    mixed = InteractionAnswer(
        question_id="household-1",
        option_ids=["household_size_2"],
        free_text="3",
        context_version=3,
    )

    with pytest.raises(InteractionAnswerError, match="duplicate option"):
        validate_interaction_answer(interaction, duplicate, current_context_version=3)
    with pytest.raises(InteractionAnswerError, match="option or provide free text"):
        validate_interaction_answer(interaction, mixed, current_context_version=3)


def test_grounding_rejects_numeric_value_that_disagrees_with_evidence() -> None:
    evidence = [
        EvidenceFact(
            fact_id="plan.total_cost",
            kind="money_sgd",
            value=84.6,
            source_type="planner",
            source_reference="plan:18:revision:4",
        )
    ]
    claims = [
        ResponseClaim(
            claim_id="correct-cost",
            kind="money_sgd",
            value=84.6,
            evidence_fact_id="plan.total_cost",
        ),
        ResponseClaim(
            claim_id="invented-cost",
            kind="money_sgd",
            value=75.0,
            evidence_fact_id="plan.total_cost",
        ),
    ]

    report = verify_structured_claims(claims, evidence)

    assert report.supported_claim_ids == ["correct-cost"]
    assert report.unsupported_claim_ids == ["invented-cost"]
    assert report.unsupported_reason_codes == {"invented-cost": "EVIDENCE_VALUE_MISMATCH"}
    assert report.grounded_claim_precision == 0.5


def test_saved_claim_requires_successful_commit_receipt() -> None:
    now = datetime.now(UTC)
    preview_receipt = ActionReceipt(
        receipt_id="preview-1",
        tool_name="generate_plan_preview",
        effect=ToolEffect.PREVIEW,
        status=ToolRunStatus.SUCCEEDED,
        result_kind="plan_revision",
        result_value=4,
        result_reference="plan:18:preview:4",
        completed_at=now,
    )
    commit_receipt = ActionReceipt(
        receipt_id="commit-1",
        tool_name="save_plan_revision",
        effect=ToolEffect.COMMIT,
        status=ToolRunStatus.SUCCEEDED,
        result_kind="plan_revision",
        result_value=4,
        result_reference="plan:18:revision:4",
        completed_at=now,
    )
    claims = [
        ResponseClaim(
            claim_id="preview-is-not-saved",
            kind="plan_revision",
            value=4,
            verification_mode=ClaimVerificationMode.ACTION_RECEIPT,
            action_receipt_id="preview-1",
        ),
        ResponseClaim(
            claim_id="saved-revision",
            kind="plan_revision",
            value=4,
            verification_mode=ClaimVerificationMode.ACTION_RECEIPT,
            action_receipt_id="commit-1",
        ),
    ]

    report = verify_structured_claims(claims, [], [preview_receipt, commit_receipt])

    assert report.supported_claim_ids == ["saved-revision"]
    assert report.unsupported_reason_codes == {"preview-is-not-saved": "ACTION_NOT_COMMITTED"}


def test_live_price_claim_requires_timestamped_live_provenance() -> None:
    claims = [
        ResponseClaim(
            claim_id="claimed-live-price",
            kind="live_price_sgd",
            value=3.95,
            evidence_fact_id="product.price",
        )
    ]
    cached_fact = EvidenceFact(
        fact_id="product.price",
        kind="live_price_sgd",
        value=3.95,
        source_type="fixture",
        source_reference="fairprice-fixture:tomato-500g",
    )
    live_fact = cached_fact.model_copy(
        update={
            "source_type": "live_retrieval",
            "source_reference": "retrieval-trace:trace-17",
            "observed_at": datetime.now(UTC),
        }
    )

    cached_report = verify_structured_claims(claims, [cached_fact])
    live_report = verify_structured_claims(claims, [live_fact])

    assert cached_report.unsupported_reason_codes == {"claimed-live-price": "LIVE_PROVENANCE_MISSING"}
    assert live_report.supported_claim_ids == ["claimed-live-price"]
