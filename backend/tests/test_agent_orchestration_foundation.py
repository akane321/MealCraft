import pytest

from app.orchestration.capabilities import allowed_tools_for
from app.orchestration.contracts import (
    EvidenceFact,
    InteractionAnswer,
    ResponseClaim,
    ScopeClass,
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


def test_unconfirmed_capability_cannot_call_commit_tool() -> None:
    preview_tools = allowed_tools_for("create_plan", confirmed=False)
    confirmed_tools = allowed_tools_for("create_plan", confirmed=True)

    assert "generate_plan_preview" in preview_tools
    assert "save_plan_revision" not in preview_tools
    assert "save_plan_revision" in confirmed_tools


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
    assert report.grounded_claim_precision == 0.5
