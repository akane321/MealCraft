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
    # FairPrice's internal product id (the listing's `id`), which its cart takes; external_id is the product
    # URL's clientItemId. None for fixture products and for rows saved before it was kept.
    cart_item_id: str | None = None
    # True when the listing's "Dietary Attributes" carry "Halal"; None is unknown, never False (docs/design/halal.md).
    halal_certified: bool | None = None


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
    # Final-basket evidence. Old saved JSON remains readable without a migration.
    price_source: Literal["live", "cache", "snapshot", "fixture", "no_external_product"] | None = None
    lookup_status: (
        Literal[
            "success",
            "timeout",
            "provider_error",
            "schema_drift",
            "invalid_price",
            "selected_product_not_returned",
            "no_external_id",
            "out_of_stock",
        ]
        | None
    ) = None
    checked_at: datetime | None = None


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
    # The shopping trip of a plan longer than a week (ADR-0072: before day 1, before day 8); None is its only trip.
    shopping_trip: int | None = Field(default=None, ge=1, le=2)
    # A perishable ingredient (layer 08): used within 3 days of its trip; None is not marked.
    perishable: bool | None = None


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
