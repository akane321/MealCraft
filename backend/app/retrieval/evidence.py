"""Evidence packets: every externally sourced number a plan shows, frozen with its provenance.

A packet is data, never instructions: product titles travel inside it as strings, no model reads them,
and nothing downstream acts on what they say (see the injection tests). Its digest is recorded in the
agent run that saved the plan, so a shown price can be traced to the observation behind it later.
"""

import hashlib
import json
from datetime import UTC, datetime

from app.orchestration.contracts import EvidenceFact, GroundingReport, ResponseClaim
from app.orchestration.grounding import verify_structured_claims
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse
from app.schemas.product import GroceryEstimateResponse
from app.schemas.retrieval import (
    RetrievalEvidenceItem,
    RetrievalEvidencePacket,
    RetrievalTrace,
    TutorialVideoResponse,
)

Estimate = WeeklyGroceryEstimateResponse | GroceryEstimateResponse


def grocery_packet(estimate: Estimate, *, generated_at: datetime | None = None) -> RetrievalEvidencePacket:
    items = [
        RetrievalEvidenceItem(
            source="fairprice",
            external_id=line.product.external_id,
            title=line.product.name,
            url=line.product.product_url,
            fetched_at=line.evidence.fetched_at,
            facts={
                "fact_id": line.evidence.fact_id,
                "ingredient": line.ingredient_name,
                "price_sgd": line.product.price_sgd,
                "package_size": line.product.package_size,
                "package_unit": line.product.package_unit,
                "in_stock": line.product.in_stock,
                "provider": line.evidence.source,
                "mode": line.evidence.mode,
                "query": line.evidence.query,
                "parser_version": line.evidence.parser_version,
            },
        )
        for line in estimate.items
        if line.product is not None and line.evidence is not None
    ]
    unsourced = [line.ingredient_name for line in estimate.items if line.product is not None and line.evidence is None]
    return RetrievalEvidencePacket(
        purpose="grocery_grounding",
        query=f"{len(items)} shopping lines, pricing mode {estimate.pricing_mode}",
        generated_at=generated_at or datetime.now(UTC),
        items=items,
        warnings=[f"No provenance recorded for {name}." for name in unsourced],
    )


def tutorial_packet(
    video: TutorialVideoResponse | None, trace: RetrievalTrace, *, recipe_slug: str
) -> RetrievalEvidencePacket:
    """The one video shown for a dish, with where and how it was found; a title is data, never read as a
    rule (its words only score it)."""
    items = []
    if video is not None:
        items.append(
            RetrievalEvidenceItem(
                source="youtube",
                external_id=video.video_id,
                title=video.title,
                url=video.watch_url,
                fetched_at=trace.fetched_at,
                facts={
                    "recipe": recipe_slug,
                    "channel": video.channel_title,
                    "provider": trace.provider_used,
                    "mode": trace.mode,
                    "query": trace.query,
                    "parser_version": trace.parser_version,
                    "relevance_score": video.relevance_score,
                    "candidates": trace.candidate_count,
                },
            )
        )
    return RetrievalEvidencePacket(
        purpose="cooking_support",
        query=trace.query,
        generated_at=trace.fetched_at,
        items=items,
        warnings=list(trace.warnings),
    )


def packet_digest(packet: RetrievalEvidencePacket) -> str:
    """SHA-256 over the packet's content, not over when it was assembled."""
    body = packet.model_dump(mode="json", exclude={"generated_at"})
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verify_grocery_totals(estimate: Estimate, packet: RetrievalEvidencePacket) -> GroundingReport:
    """Recompute each priced line and the purchase total from the packet alone, and check the numbers the
    estimate shows against them: a shown price that no observation supports is reported, not trusted."""
    facts: list[EvidenceFact] = []
    claims: list[ResponseClaim] = []
    evidence_price = {item.facts["fact_id"]: item for item in packet.items}
    total = 0.0
    for line in estimate.items:
        if line.product is None:
            continue
        fact_id = line.evidence.fact_id if line.evidence else f"unsourced:{line.ingredient_name}"
        item = evidence_price.get(fact_id)
        claims.append(
            ResponseClaim(
                claim_id=f"line:{line.ingredient_name}",
                kind="purchase_cost_sgd",
                value=line.purchase_cost_sgd,
                evidence_fact_id=f"cost:{fact_id}",
            )
        )
        if item is None:
            continue
        cost = round(float(item.facts["price_sgd"]) * line.packages_required, 2)
        total += cost
        facts.append(
            EvidenceFact(
                fact_id=f"cost:{fact_id}",
                kind="purchase_cost_sgd",
                value=cost,
                source_type="live_retrieval" if item.facts["mode"] in ("live", "cache") else "snapshot",
                source_reference=item.url,
                observed_at=item.fetched_at,
            )
        )
    facts.append(
        EvidenceFact(
            fact_id="purchase_total",
            kind="purchase_total_sgd",
            value=round(total, 2),
            source_type="derived",
            source_reference="sum of packet line costs",
        )
    )
    claims.append(
        ResponseClaim(
            claim_id="purchase_total",
            kind="purchase_total_sgd",
            value=estimate.purchase_total_sgd,
            evidence_fact_id="purchase_total",
        )
    )
    return verify_structured_claims(claims, facts)
