"""A saved plan keeps FairPrice's Halal mark on each chosen product (docs/design/halal.md); unknown stays None."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse, WeeklyMealPlanRequest
from app.schemas.product import GroceryLineEstimate, ProductResponse
from app.services.meal_plan import WeeklyMealPlanService


def _line(name: str, halal_certified: bool | None) -> GroceryLineEstimate:
    return GroceryLineEstimate(
        ingredient_name=name,
        ingredient_display_name=name,
        required_quantity=500,
        unit="g",
        pantry_deduction=0,
        remaining_quantity=500,
        product=ProductResponse(
            external_id=f"fixture:{name}",
            name=name,
            brand=None,
            category=None,
            package_size=500,
            package_unit="g",
            price_sgd=5,
            product_url=f"https://example.test/{name}",
            image_url=None,
            in_stock=True,
            source="fixture",
            fetched_at=datetime(2026, 10, 31, tzinfo=UTC),
            halal_certified=halal_certified,
        ),
        match_score=1,
        packages_required=1,
        purchase_cost_sgd=5,
        consumed_cost_sgd=5,
        excess_quantity=0,
        note=None,
    )


def test_a_saved_plan_reads_back_the_certified_mark_and_unknown_stays_none():
    grocery = WeeklyGroceryEstimateResponse(
        pricing_mode="fixture",
        complete=True,
        purchase_total_sgd=15,
        consumed_total_sgd=15,
        weekly_budget_sgd=None,
        within_weekly_budget=None,
        items=[_line("chicken_breast", True), _line("beef", False), _line("lamb", None)],
        unmapped_ingredients=[],
        warnings=[],
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        plan = MealPlanRepository(session, household_id=1).create(
            constraints=WeeklyMealPlanRequest(), scheduled=[], grocery=grocery, warnings=[]
        )
        read_back = {
            item.ingredient_name: WeeklyMealPlanService._grocery_line(item).product.halal_certified
            for item in plan.grocery_items
        }
    assert read_back == {"chicken_breast": True, "beef": False, "lamb": None}
