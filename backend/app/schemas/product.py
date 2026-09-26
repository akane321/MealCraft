from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievalTrace

ProductSource = Literal["fairprice", "fixture"]
PricingMode = Literal["fixture", "live"]


class ProductResponse(BaseModel):
    external_id: str
    name: str
    brand: str | None
    category: str | None
    package_size: float | None
    package_unit: str | None
    price_sgd: float = Field(ge=0)
    product_url: str
    image_url: str | None
    in_stock: bool
    source: ProductSource
    fetched_at: datetime
    # What the page said, kept beside what was parsed from it, so a wrong basket can be traced to its text.
    package_text: str | None = None
    # The shelf price when the effective price_sgd is a promotion.
    regular_price_sgd: float | None = Field(default=None, ge=0)
    # Typed doubt instead of a guessed quantity: sold by count, or no size could be read at all.
    package_warning: Literal["count_package", "unknown_package"] | None = None


class ProductSearchResponse(BaseModel):
    query: str
    provider_used: ProductSource
    fallback_used: bool
    cached: bool
    warning: str | None
    items: list[ProductResponse]
    retrieval: RetrievalTrace


class PriceEvidence(BaseModel):
    """Where one shown price came from, so it can be traced and replayed (external-retrieval-rag.md).

    `mode` is how the observation was obtained now: a live FairPrice request, the 15-minute cache, the
    reviewed release snapshot, or the offline fixture. `fetched_at` is when the price was observed,
    not when it was read.
    """

    fact_id: str
    source: Literal["fairprice", "fixture", "release_snapshot"]
    mode: Literal["live", "cache", "snapshot", "fixture"]
    query: str | None
    parser_version: str | None
    fetched_at: datetime


class GroceryLineEstimate(BaseModel):
    ingredient_name: str
    ingredient_display_name: str
    required_quantity: float | None
    unit: str | None
    pantry_deduction: float
    remaining_quantity: float | None
    product: ProductResponse | None
    match_score: float | None
    packages_required: int
    purchase_cost_sgd: float
    consumed_cost_sgd: float | None
    excess_quantity: float | None
    note: str | None
    evidence: PriceEvidence | None = None


class GroceryEstimateResponse(BaseModel):
    pricing_mode: PricingMode
    complete: bool
    purchase_total_sgd: float
    consumed_total_sgd: float | None
    budget_per_meal_sgd: float | None
    within_budget: bool | None
    items: list[GroceryLineEstimate]
    unmapped_ingredients: list[str]
    warnings: list[str]
