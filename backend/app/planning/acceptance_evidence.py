"""Claim guards for Issue #310 developer acceptance evidence."""

import hashlib
import json
from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.planning.package_optimizer import optimize_packages
from app.schemas.planning_v2 import PlanningProductOption


class PriceReferenceDomain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_scope: Literal["generated_options", "full_supported_catalog"]
    packaging_scope: Literal["fixed_product", "mixed_packages"]
    price_source: Literal["fixture", "observed_snapshot"]
    exact: bool


class PriceGapEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_quote_sgd: Decimal = Field(ge=0)
    reference_price_sgd: Decimal = Field(ge=0)
    ratio: Decimal
    within_five_percent: bool
    claim_scope: Literal["generated-domain-reference", "real-minimum"]


class RealMinimumReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mapped_ingredients: int = Field(ge=0)
    product_observations: int = Field(ge=0)
    multi_product_ingredients: int = Field(ge=0)
    max_products_per_ingredient: int = Field(ge=0)
    observed_snapshot: bool
    full_supported_catalog: bool
    mixed_packages_in_product: bool
    exact_joint_plan_and_purchase_solver: bool
    ready: bool
    blockers: tuple[str, ...]


class PackagePolicyComparison(BaseModel):
    """Matched fixed-product and mixed-package costs for one observed demand."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ingredient_id: str
    demand_grams: Decimal = Field(gt=0)
    fixed_product_cost_sgd: Decimal = Field(ge=0)
    mixed_package_cost_sgd: Decimal = Field(ge=0)
    savings_sgd: Decimal = Field(ge=0)
    mixed_allocations: tuple[tuple[str, int], ...]


def compare_package_policies(
    ingredient_id: str, products: list[dict], demand_grams: float
) -> PackagePolicyComparison | None:
    """Compare the product's one-product rule with exact mixing on identical snapshot facts."""
    options = []
    for product in products:
        quantity = product.get("package_grams")
        price = product.get("price_sgd")
        product_id = str(product.get("external_id") or "")
        if (
            not product.get("in_stock")
            or not product_id
            or not isinstance(quantity, (int, float))
            or quantity <= 0
            or not isinstance(price, (int, float))
            or price < 0
            or (Decimal(str(price)) * 100) % 1
        ):
            continue
        options.append(
            PlanningProductOption(
                ingredient_id=ingredient_id,
                product_id=product_id,
                package_quantity=quantity,
                package_unit="g",
                price_sgd=price,
                available=True,
            )
        )
    if not options or demand_grams <= 0:
        return None
    fixed = min(
        Decimal(str(option.price_sgd)) * ceil(Decimal(str(demand_grams)) / Decimal(str(option.package_quantity)))
        for option in options
    )
    mixed = optimize_packages(ingredient_id, demand_grams, "g", options, max_combinations=1_000_000)
    if mixed.status != "optimal" or mixed.purchase_cost_sgd is None:
        return None
    mixed_cost = Decimal(str(mixed.purchase_cost_sgd))
    if mixed_cost > fixed:
        raise RuntimeError("exact mixed-package cost exceeded the fixed-product feasible solution")
    return PackagePolicyComparison(
        ingredient_id=ingredient_id,
        demand_grams=Decimal(str(demand_grams)),
        fixed_product_cost_sgd=fixed,
        mixed_package_cost_sgd=mixed_cost,
        savings_sgd=fixed - mixed_cost,
        mixed_allocations=tuple((allocation.product_id, allocation.packages) for allocation in mixed.allocations),
    )


def assess_real_minimum_readiness(
    ingredients: dict,
    *,
    observed_snapshot: bool,
    full_supported_catalog: bool,
    mixed_packages_in_product: bool,
    exact_joint_plan_and_purchase_solver: bool,
) -> RealMinimumReadiness:
    """Describe whether a snapshot comparison can support the owner's real-minimum claim."""
    mapped = [entry for entry in ingredients.values() if entry.get("status") == "mapped"]
    sizes = [len(entry.get("products", [])) for entry in mapped]
    blockers = []
    for condition, code in (
        (observed_snapshot, "prices_are_not_an_observed_snapshot"),
        (full_supported_catalog, "candidate_domain_is_not_the_full_supported_catalog"),
        (mixed_packages_in_product, "product_path_does_not_support_mixed_packages"),
        (exact_joint_plan_and_purchase_solver, "no_exact_joint_plan_and_purchase_solve"),
    ):
        if not condition:
            blockers.append(code)
    return RealMinimumReadiness(
        mapped_ingredients=len(mapped),
        product_observations=sum(sizes),
        multi_product_ingredients=sum(size > 1 for size in sizes),
        max_products_per_ingredient=max(sizes, default=0),
        observed_snapshot=observed_snapshot,
        full_supported_catalog=full_supported_catalog,
        mixed_packages_in_product=mixed_packages_in_product,
        exact_joint_plan_and_purchase_solver=exact_joint_plan_and_purchase_solver,
        ready=not blockers,
        blockers=tuple(blockers),
    )


def assess_price_gap(product_quote_sgd, reference_price_sgd, domain: PriceReferenceDomain) -> PriceGapEvidence:
    """Calculate the gap while refusing to upgrade a bounded reference into a real minimum."""
    quote = Decimal(str(product_quote_sgd))
    reference = Decimal(str(reference_price_sgd))
    if reference <= 0:
        raise ValueError("reference price must be positive")
    real_minimum = domain == PriceReferenceDomain(
        candidate_scope="full_supported_catalog",
        packaging_scope="mixed_packages",
        price_source="observed_snapshot",
        exact=True,
    )
    ratio = quote / reference
    return PriceGapEvidence(
        product_quote_sgd=quote,
        reference_price_sgd=reference,
        ratio=ratio,
        within_five_percent=quote >= reference and ratio <= Decimal("1.05"),
        claim_scope="real-minimum" if real_minimum else "generated-domain-reference",
    )


class NearDuplicateReviewRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pair_id: str = Field(min_length=1)
    verdict: Literal["near", "distinct", "unsure"]
    rationale: str = Field(min_length=1)


class NearDuplicateReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["near-duplicate-review-v1"]
    producer_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: tuple[NearDuplicateReviewRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def independent_and_unique(self):
        if self.producer_id == self.reviewer_id:
            raise ValueError("reviewer must be independent from the producer")
        ids = [row.pair_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("review pair IDs must be unique")
        return self

    @property
    def freeze_ready(self) -> bool:
        return all(row.verdict != "unsure" for row in self.rows)

    @property
    def content_sha256(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()


class NearDuplicateThresholdFreeze(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["near-duplicate-threshold-freeze-v1"]
    policy_version: str = Field(min_length=1)
    review_batch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title_min: float = Field(ge=0, le=1)
    ingredients_min: float = Field(ge=0, le=1)
    cosine_min: float = Field(ge=-1, le=1)
    fried_rice_cosine_min: float = Field(ge=-1, le=1)


def verify_near_duplicate_freeze(batch, freeze, policy) -> tuple[str, ...]:
    """Bind a freeze to independently reviewed bytes and the exact runtime policy."""
    issues = []
    if not batch.freeze_ready:
        issues.append("review_batch_has_unsure_verdicts")
    if freeze.review_batch_sha256 != batch.content_sha256:
        issues.append("review_batch_digest_mismatch")
    actual = (
        policy.version,
        policy.title_min,
        policy.ingredients_min,
        policy.cosine_min,
        policy.fried_rice_cosine_min,
    )
    declared = (
        freeze.policy_version,
        freeze.title_min,
        freeze.ingredients_min,
        freeze.cosine_min,
        freeze.fried_rice_cosine_min,
    )
    if actual != declared:
        issues.append("runtime_policy_mismatch")
    return tuple(issues)
