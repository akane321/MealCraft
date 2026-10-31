from datetime import UTC, datetime

from app.models.meal_plan import MealPlan
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.fairprice_cart import (
    FairPriceCartLine,
    FairPriceCartPrepareResponse,
    FairPriceCartReport,
    FairPriceCartState,
    LineStatus,
    TripNumber,
    cart_state,
    fingerprint,
    line_key,
    trip_lines,
)
from app.schemas.product import GroceryLineEstimate
from app.services.meal_plan import WeeklyMealPlanService
from app.services.product import ProductSearchService


class FairPriceCartNotFoundError(RuntimeError):
    pass


class FairPriceCartConflictError(RuntimeError):
    pass


def _cents(value: float) -> int:
    return round(value * 100)


class FairPriceCartService:
    """What goes into the household's own FairPrice cart. The server only checks the lines and keeps the record;
    the browser extension writes the cart (docs/design/fairprice-cart.md)."""

    def __init__(self, *, repository: MealPlanRepository, product_service: ProductSearchService) -> None:
        self.repository = repository
        self.product_service = product_service

    def prepare(self, plan_id: int, shopping_trip: TripNumber | None) -> FairPriceCartPrepareResponse:
        plan = self._plan(plan_id)
        lines = trip_lines(self._lines(plan), shopping_trip)
        # A fixture plan has no FairPrice products to check, and asks FairPrice nothing.
        live = plan.pricing_mode != "fixture"
        checkable = [
            line
            for line in lines
            if live and line.packages_required > 0 and line.product is not None and line.product.source == "fairprice"
        ]
        rechecked_by_key = {}
        if checkable:
            rechecked_by_key = dict(
                zip(map(line_key, checkable), self.product_service.refresh_selected(checkable), strict=True)
            )
        self.repository.session.commit()  # the checked prices join the cache
        planned_cents = sum(_cents(line.purchase_cost_sgd) for line in lines)
        projected_cents, ready_cents = planned_cents, 0
        prepared = []
        for line in lines:
            rechecked = rechecked_by_key.get(line_key(line))
            status = self._status(line, rechecked, live)
            live_price = (
                rechecked.product.price_sgd
                if rechecked is not None and rechecked.evidence.lookup_status in {"success", "out_of_stock"}
                else None
            )
            if live_price is not None:
                projected_cents += _cents(live_price) * line.packages_required - _cents(line.purchase_cost_sgd)
            if status == "ready":
                ready_cents += _cents(live_price) * line.packages_required
            product = line.product
            prepared.append(
                FairPriceCartLine(
                    line_key=line_key(line),
                    ingredient_name=line.ingredient_name,
                    ingredient_display_name=line.ingredient_display_name,
                    product_name=product.name if product else None,
                    client_item_id=product.external_id if product else None,
                    cart_item_id=rechecked.product.cart_item_id if status in {"ready", "out_of_stock"} else None,
                    quantity=line.packages_required,
                    planned_price_sgd=product.price_sgd if product else None,
                    live_price_sgd=live_price,
                    product_url=product.product_url if product else None,
                    status=status,
                )
            )
        budget = float(plan.weekly_budget_sgd) if plan.weekly_budget_sgd is not None else None
        return FairPriceCartPrepareResponse(
            plan_id=plan.id,
            shopping_trip=shopping_trip,
            fingerprint=fingerprint(lines),
            lines=prepared,
            ready_total_sgd=ready_cents / 100,
            planned_total_sgd=planned_cents / 100,
            projected_total_sgd=projected_cents / 100,
            budget_sgd=budget,
            over_budget=budget is not None and projected_cents > _cents(budget),
        )

    def report(self, plan_id: int, body: FairPriceCartReport) -> FairPriceCartState:
        plan = self._plan(plan_id)
        if not any(result.status in {"added", "reduced"} and result.quantity > 0 for result in body.results):
            return self._state(plan)  # nothing went into the cart: keep what is stored
        trip = {
            "status": "in_cart",
            "sent_at": datetime.now(UTC).isoformat(),
            "fingerprint": body.fingerprint,
            "results": [result.model_dump(mode="json") for result in body.results],
        }
        self.repository.save_fairprice_cart(plan, {**(plan.fairprice_cart or {}), str(body.shopping_trip or 1): trip})
        return self._state(plan)

    def mark_ordered(self, plan_id: int, shopping_trip: TripNumber | None) -> FairPriceCartState:
        plan = self._plan(plan_id)
        key = str(shopping_trip or 1)
        stored = (plan.fairprice_cart or {}).get(key)
        if stored is None:
            raise FairPriceCartConflictError("This shopping trip was never sent to the FairPrice cart")
        stored = {**stored, "status": "ordered", "ordered_at": datetime.now(UTC).isoformat()}
        self.repository.save_fairprice_cart(plan, {**plan.fairprice_cart, key: stored})
        return self._state(plan)

    def _plan(self, plan_id: int) -> MealPlan:
        plan = self.repository.get(plan_id)
        if plan is None:
            raise FairPriceCartNotFoundError("Meal plan not found")
        return plan

    @staticmethod
    def _lines(plan: MealPlan) -> list[GroceryLineEstimate]:
        return [WeeklyMealPlanService._grocery_line(item) for item in plan.grocery_items]

    def _state(self, plan: MealPlan) -> FairPriceCartState:
        return cart_state(plan.fairprice_cart, self._lines(plan)) or {}

    @staticmethod
    def _status(line: GroceryLineEstimate, rechecked: GroceryLineEstimate | None, live: bool) -> LineStatus:
        if not live:
            return "no_product"
        if line.packages_required == 0:
            return "not_bought"
        if rechecked is None:
            return "no_product"
        # A lookup that failed or timed out is not "out of stock"; the extension needs a live id, so it is not_found.
        lookup = rechecked.evidence.lookup_status
        if lookup == "out_of_stock":
            return "out_of_stock"
        if lookup == "success" and rechecked.product.cart_item_id:
            return "ready"
        return "not_found"
