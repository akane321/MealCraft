from app.orchestration.contracts import EvidenceFact, GroundingReport, ResponseClaim


def verify_structured_claims(
    claims: list[ResponseClaim],
    evidence: list[EvidenceFact],
) -> GroundingReport:
    """Verify structured claims; natural-language claim extraction remains future work."""

    facts = {fact.fact_id: fact for fact in evidence}
    supported: list[str] = []
    unsupported: list[str] = []
    for claim in claims:
        fact = facts.get(claim.evidence_fact_id or "")
        if fact is not None and fact.kind == claim.kind and fact.value == claim.value:
            supported.append(claim.claim_id)
        else:
            unsupported.append(claim.claim_id)
    return GroundingReport(
        total_claims=len(claims),
        supported_claim_ids=supported,
        unsupported_claim_ids=unsupported,
    )
