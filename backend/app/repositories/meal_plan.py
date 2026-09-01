from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanEvent, MealPlanGroceryItem
from app.models.recipe import Recipe
from app.schemas.meal_plan import (
    MealPlanEntryStatus,
    MealPlanEventType,
    WeeklyGroceryEstimateResponse,
    WeeklyMealPlanRequest,
)
from app.schemas.recommendation import RecipeRecommendationResponse


class MealPlanRevisionConflictError(RuntimeError):
    pass


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

        self._replace_grocery_items(plan, grocery)

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
                selectinload(MealPlan.events),
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

    def create_replan_preview(
        self,
        *,
        plan: MealPlan,
        entry: MealPlanEntry,
        proposed_recipe_id: int | None,
        event_type: MealPlanEventType,
        reason: str | None,
        unavailable_ingredient: str | None,
        before_entry: dict,
        after_entry: dict,
        after_grocery: WeeklyGroceryEstimateResponse,
        after_warnings: list[str],
        nutrition_delta: dict,
        grocery_delta: list[dict],
        purchase_total_delta_sgd: float,
    ) -> MealPlanEvent:
        event = MealPlanEvent(
            plan_id=plan.id,
            entry_id=entry.id,
            proposed_recipe_id=proposed_recipe_id,
            event_type=event_type,
            base_revision=plan.revision,
            reason=reason,
            unavailable_ingredient=unavailable_ingredient,
            before_entry=before_entry,
            after_entry=after_entry,
            after_grocery=after_grocery.model_dump(mode="json"),
            after_warnings=after_warnings,
            nutrition_delta=nutrition_delta,
            grocery_delta=grocery_delta,
            purchase_total_delta_sgd=purchase_total_delta_sgd,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def get_event(self, *, plan_id: int, event_id: int) -> MealPlanEvent | None:
        statement = select(MealPlanEvent).where(
            MealPlanEvent.id == event_id,
            MealPlanEvent.plan_id == plan_id,
        )
        return self.session.scalars(statement).one_or_none()

    def list_events(self, *, plan_id: int, limit: int) -> list[MealPlanEvent]:
        statement = (
            select(MealPlanEvent)
            .where(MealPlanEvent.plan_id == plan_id)
            .order_by(MealPlanEvent.created_at.desc(), MealPlanEvent.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def apply_event(
        self,
        *,
        plan: MealPlan,
        event: MealPlanEvent,
        proposed_recipe: Recipe | None,
        grocery: WeeklyGroceryEstimateResponse,
    ) -> tuple[MealPlan, MealPlanEvent]:
        if event.status != "previewed" or event.base_revision != plan.revision:
            raise MealPlanRevisionConflictError

        entry = next((item for item in plan.entries if item.id == event.entry_id), None)
        if entry is None:
            raise LookupError

        after = event.after_entry
        if event.event_type in {"REPLACE_MEAL", "ITEM_UNAVAILABLE"}:
            if proposed_recipe is None:
                raise LookupError
            entry.recipe = proposed_recipe
            entry.recipe_id = proposed_recipe.id
            entry.recommendation_score = after["recommendation_score"]
            entry.consumed_cost_sgd = after["consumed_cost_sgd"]
            entry.purchase_cost_sgd = after["purchase_cost_sgd"]
            nutrition = after["nutrition_per_person"]
            entry.calories_kcal = nutrition["calories_kcal"]
            entry.protein_g = nutrition["protein_g"]
            entry.carbohydrate_g = nutrition["carbohydrate_g"]
            entry.fat_g = nutrition["fat_g"]
            entry.sodium_mg = nutrition["sodium_mg"]
            entry.sugar_g = nutrition["sugar_g"]
        elif event.event_type == "CANCEL_MEAL":
            entry.status = "skipped"
            entry.consumed_at = None
        elif event.event_type == "LOCK_MEAL":
            entry.is_locked = True

        if event.event_type != "LOCK_MEAL":
            self._replace_grocery_items(plan, grocery)
            plan.purchase_total_sgd = grocery.purchase_total_sgd
            plan.consumed_total_sgd = grocery.consumed_total_sgd
            plan.within_weekly_budget = grocery.within_weekly_budget
            plan.warnings = event.after_warnings

        plan.revision += 1
        event.status = "applied"
        event.applied_revision = plan.revision
        event.applied_at = datetime.now(UTC)
        self.session.commit()
        applied_event_id = event.id
        refreshed_plan = self.get(plan.id)
        refreshed_event = self.get_event(plan_id=plan.id, event_id=applied_event_id)
        if refreshed_plan is None or refreshed_event is None:
            raise LookupError
        return refreshed_plan, refreshed_event

    def _replace_grocery_items(self, plan: MealPlan, grocery: WeeklyGroceryEstimateResponse) -> None:
        plan.grocery_items.clear()
        if plan.id is not None:
            self.session.flush()
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
