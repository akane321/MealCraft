from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanGroceryItem
from app.models.recipe import Recipe
from app.schemas.meal_plan import MealPlanEntryStatus, WeeklyGroceryEstimateResponse, WeeklyMealPlanRequest
from app.schemas.recommendation import RecipeRecommendationResponse


class MealPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        constraints: WeeklyMealPlanRequest,
        scheduled: list[tuple[date, RecipeRecommendationResponse]],
        grocery: WeeklyGroceryEstimateResponse,
        warnings: list[str],
    ) -> MealPlan:
        plan = MealPlan(
            start_date=constraints.start_date,
            end_date=scheduled[-1][0],
            day_count=constraints.day_count,
            household_size=constraints.household_size,
            pricing_mode=constraints.pricing_mode,
            budget_per_meal_sgd=constraints.budget_per_meal_sgd,
            weekly_budget_sgd=constraints.weekly_budget_sgd,
            purchase_total_sgd=grocery.purchase_total_sgd,
            consumed_total_sgd=grocery.consumed_total_sgd,
            within_weekly_budget=grocery.within_weekly_budget,
            constraints=constraints.model_dump(mode="json"),
            warnings=warnings,
        )
        for day_index, (planned_date, recommendation) in enumerate(scheduled, start=1):
            estimate = recommendation.grocery_estimate
            nutrition = recommendation.recipe.nutrition
            plan.entries.append(
                MealPlanEntry(
                    recipe_id=recommendation.recipe.id,
                    day_index=day_index,
                    planned_date=planned_date,
                    recommendation_score=recommendation.total_score,
                    consumed_cost_sgd=estimate.consumed_total_sgd if estimate else 0,
                    purchase_cost_sgd=estimate.purchase_total_sgd if estimate else 0,
                    calories_kcal=nutrition.calories_kcal,
                    protein_g=nutrition.protein_g,
                    carbohydrate_g=nutrition.carbohydrate_g,
                    fat_g=nutrition.fat_g,
                    sodium_mg=nutrition.sodium_mg,
                    sugar_g=nutrition.sugar_g,
                )
            )

        for line in grocery.items:
            product = line.product
            plan.grocery_items.append(
                MealPlanGroceryItem(
                    ingredient_name=line.ingredient_name,
                    ingredient_display_name=line.ingredient_display_name,
                    required_quantity=line.required_quantity,
                    unit=line.unit,
                    pantry_deduction=line.pantry_deduction,
                    remaining_quantity=line.remaining_quantity,
                    product_external_id=product.external_id if product else None,
                    product_name=product.name if product else None,
                    product_brand=product.brand if product else None,
                    product_category=product.category if product else None,
                    product_package_size=product.package_size if product else None,
                    product_package_unit=product.package_unit if product else None,
                    product_price_sgd=product.price_sgd if product else None,
                    product_url=product.product_url if product else None,
                    product_image_url=product.image_url if product else None,
                    product_source=product.source if product else None,
                    product_fetched_at=product.fetched_at if product else None,
                    match_score=line.match_score,
                    packages_required=line.packages_required,
                    purchase_cost_sgd=line.purchase_cost_sgd,
                    consumed_cost_sgd=line.consumed_cost_sgd,
                    excess_quantity=line.excess_quantity,
                    note=line.note,
                )
            )

        self.session.add(plan)
        self.session.commit()
        return self.get(plan.id) or plan

    def get(self, plan_id: int) -> MealPlan | None:
        statement = (
            select(MealPlan)
            .where(MealPlan.id == plan_id)
            .options(
                selectinload(MealPlan.entries).joinedload(MealPlanEntry.recipe).joinedload(Recipe.nutrition),
                selectinload(MealPlan.grocery_items),
            )
        )
        return self.session.scalars(statement).unique().one_or_none()

    def list_recent(self, *, limit: int) -> list[MealPlan]:
        statement = select(MealPlan).order_by(MealPlan.created_at.desc(), MealPlan.id.desc()).limit(limit)
        return list(self.session.scalars(statement).all())

    def update_entry_status(
        self,
        *,
        plan_id: int,
        entry_id: int,
        status: MealPlanEntryStatus,
    ) -> MealPlan | None:
        statement = select(MealPlanEntry).where(
            MealPlanEntry.id == entry_id,
            MealPlanEntry.plan_id == plan_id,
        )
        entry = self.session.scalars(statement).one_or_none()
        if entry is None:
            return None

        if entry.status != status:
            entry.status = status
            entry.consumed_at = datetime.now(UTC) if status == "completed" else None
            self.session.commit()

        return self.get(plan_id)
