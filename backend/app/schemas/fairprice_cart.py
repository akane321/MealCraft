"""The FairPrice cart of a plan (docs/design/fairprice-cart.md): the lines to put in the cart, what the person's
browser extension reported, and what the plan remembers of it."""

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.product import GroceryLineEstimate

LineStatus = Literal["ready", "out_of_stock", "not_found", "no_product", "not_bought"]
ResultStatus = Literal["added", "out_of_stock", "reduced", "failed"]
# A plan's only trip is null in a request and "1" in a stored record.
TripNumber = Literal[1, 2]


class FairPriceCartTripRequest(BaseModel):
    shopping_trip: TripNumber | None = None


class FairPriceCartLine(BaseModel):
    line_key: str
    ingredient_name: str
    ingredient_display_name: str
    product_name: str | None
    client_item_id: str | None
    cart_item_id: str | None
    quantity: int
    planned_price_sgd: float | None
    live_price_sgd: float | None
    product_url: str | None
    status: LineStatus


class FairPriceCartPrepareResponse(BaseModel):
    plan_id: int
    shopping_trip: TripNumber | None
    fingerprint: str
    lines: list[FairPriceCartLine]
    ready_total_sgd: float
    planned_total_sgd: float
    projected_total_sgd: float
    budget_sgd: float | None
    over_budget: bool


class FairPriceCartResult(BaseModel):
    line_key: str = Field(max_length=300)
    cart_item_id: str | None = Field(default=None, max_length=40)
    status: ResultStatus
    quantity: int = Field(ge=0, le=999)  # what this add put in the cart; 0 unless added or reduced
    cart_price_sgd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class FairPriceCartReport(BaseModel):
    shopping_trip: TripNumber | None = None
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    results: list[FairPriceCartResult] = Field(max_length=500)


class FairPriceCartTrip(BaseModel):
    status: Literal["in_cart", "ordered"]
    sent_at: datetime
    ordered_at: datetime | None = None
    fingerprint: str
    results: list[FairPriceCartResult]
    # True when the plan's lines changed after they were sent.
    stale: bool = False


# Trips keyed "1" and "2".
FairPriceCartState = dict[str, FairPriceCartTrip]


def line_key(line: GroceryLineEstimate) -> str:
    return f"{line.shopping_trip or 1}|{line.ingredient_name}|{line.unit or ''}"


def trip_lines(lines: list[GroceryLineEstimate], trip: int | None) -> list[GroceryLineEstimate]:
    return [line for line in lines if (line.shopping_trip or 1) == (trip or 1)]


def fingerprint(lines: list[GroceryLineEstimate]) -> str:
    """The trip's bought FairPrice lines, from stored fields only, so the plan response can recompute it."""
    bought = sorted(
        f"{line_key(line)}|{line.product.external_id}|{line.packages_required}"
        for line in lines
        if line.product is not None and line.product.source == "fairprice" and line.packages_required > 0
    )
    return sha256("\n".join(bought).encode()).hexdigest()


def cart_state(stored: dict | None, lines: list[GroceryLineEstimate]) -> FairPriceCartState | None:
    """The stored record with `stale` worked out against the plan's current lines."""
    if not stored:
        return None
    return {
        key: FairPriceCartTrip.model_validate(
            {**trip, "stale": trip["fingerprint"] != fingerprint(trip_lines(lines, int(key)))}
        )
        for key, trip in stored.items()
    }
