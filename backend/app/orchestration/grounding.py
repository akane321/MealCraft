from app.orchestration.contracts import (
    ActionReceipt,
    ClaimVerificationMode,
    EvidenceFact,
    GroundingReport,
    ResponseClaim,
    ToolEffect,
    ToolRunStatus,
)


def verify_structured_claims(
    claims: list[ResponseClaim],
    evidence: list[EvidenceFact],
    action_receipts: list[ActionReceipt] | None = None,
) -> GroundingReport:
    """Verify typed response claims against facts or successful commit receipts.

    Natural-language atomic-claim extraction remains future work. High-risk
    wording should be generated from these verified claims, not independently.
    """

    facts = {fact.fact_id: fact for fact in evidence}
    receipts = {receipt.receipt_id: receipt for receipt in action_receipts or []}
    supported: list[str] = []
    unsupported: list[str] = []
    reason_codes: dict[str, str] = {}
    for claim in claims:
        if claim.verification_mode is ClaimVerificationMode.ACTION_RECEIPT:
            receipt = receipts.get(claim.action_receipt_id or "")
            if receipt is None:
                reason_codes[claim.claim_id] = "ACTION_RECEIPT_MISSING"
            elif receipt.status is not ToolRunStatus.SUCCEEDED:
                reason_codes[claim.claim_id] = "ACTION_NOT_SUCCEEDED"
            elif receipt.effect is not ToolEffect.COMMIT:
                reason_codes[claim.claim_id] = "ACTION_NOT_COMMITTED"
            elif receipt.result_kind != claim.kind or receipt.result_value != claim.value:
                reason_codes[claim.claim_id] = "ACTION_RESULT_MISMATCH"
            else:
                supported.append(claim.claim_id)
                continue
            unsupported.append(claim.claim_id)
            continue

        fact = facts.get(claim.evidence_fact_id or "")
        if fact is None:
            reason_codes[claim.claim_id] = "EVIDENCE_FACT_MISSING"
        elif fact.kind != claim.kind or fact.value != claim.value:
            reason_codes[claim.claim_id] = "EVIDENCE_VALUE_MISMATCH"
        elif claim.kind.startswith("live_") and (fact.source_type != "live_retrieval" or fact.observed_at is None):
            reason_codes[claim.claim_id] = "LIVE_PROVENANCE_MISSING"
        else:
            supported.append(claim.claim_id)
            continue
        unsupported.append(claim.claim_id)
    return GroundingReport(
        total_claims=len(claims),
        supported_claim_ids=supported,
        unsupported_claim_ids=unsupported,
        unsupported_reason_codes=reason_codes,
    )
