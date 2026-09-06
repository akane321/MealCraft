from datetime import UTC, datetime

import pytest

from app.orchestration.capabilities import allowed_tools_for, authorize_tool_call
from app.orchestration.contracts import (
    ActionReceipt,
    ClaimVerificationMode,
    EvidenceFact,
    InteractionAnswer,
    ResponseClaim,
    ScopeClass,
    ToolEffect,
    ToolRunStatus,
)
from app.orchestration.grounding import verify_structured_claims
from app.orchestration.interactions import (
    InteractionAnswerError,
    household_size_interaction,
    validate_interaction_answer,
)
from app.orchestration.scope_policy import ReferenceScopePolicy


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
