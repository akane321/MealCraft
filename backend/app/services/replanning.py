from collections import Counter

from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanEvent
from app.models.recipe import Recipe
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.repositories.meal_plan import MealPlanRepository, MealPlanRevisionConflictError
from app.repositories.recipe import RecipeRepository
from app.schemas.meal_plan import (
    MealPlanEntrySnapshot,
    MealPlanGroceryDeltaLine,
    MealPlanNutritionDelta,
    MealPlanReplanConfirmationResponse,
    MealPlanReplanEventCollectionResponse,
    MealPlanReplanEventResponse,
    MealPlanReplanPreviewRequest,
    WeeklyGroceryEstimateResponse,
    WeeklyMealPlanRequest,
)
from app.schemas.recommendation import RecipeRecommendationResponse
from app.services.meal_plan import WeeklyMealPlanService
from app.services.recommendation import RecipeRecommendationService


class MealPlanReplanNotFoundError(LookupError):
    pass


class MealPlanReplanValidationError(ValueError):
    pass


class MealPlanReplanConflictError(RuntimeError):
    pass


class MealPlanReplanningService:
    def __init__(
        self,
        *,
        repository: MealPlanRepository,
        recipe_repository: RecipeRepository,
        recommendation_service: RecipeRecommendationService,
        grocery_aggregator: WeeklyGroceryAggregator,
    ) -> None:
        self.repository = repository
        self.recipe_repository = recipe_repository
        self.recommendation_service = recommendation_service
        self.grocery_aggregator = grocery_aggregator

    def preview(
        self,
        *,
        plan_id: int,
        request: MealPlanReplanPreviewRequest,
    ) -> MealPlanReplanEventResponse:
        plan = self.repository.get(plan_id)
        if plan is None:
            raise MealPlanReplanNotFoundError("Meal plan not found")
        entry = next((item for item in plan.entries if item.id == request.entry_id), None)
        if entry is None:
            raise MealPlanReplanNotFoundError("Meal-plan entry not found")
        self._validate_target(entry, request)

        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints)
        recipes = self.recipe_repository.list_for_recommendation()
        recipes_by_id = {recipe.id: recipe for recipe in recipes}
        recommendation: RecipeRecommendationResponse | None = None

        if request.event_type in {"REPLACE_MEAL", "ITEM_UNAVAILABLE"}:
            recommendation = self._select_replacement(
                plan=plan,
                entry=entry,
                request=request,
                constraints=constraints,
                recipes_by_id=recipes_by_id,
            )

        before_entry = self._entry_snapshot(entry)
        after_entry = self._after_entry_snapshot(entry, request, recommendation)
        before_grocery = self._current_grocery(plan)
        if request.event_type == "LOCK_MEAL":
            after_grocery = before_grocery
            after_warnings = list(plan.warnings)
        else:
            future_recipes = self._recipes_after_event(
                plan=plan,
                target=entry,
                event_type=request.event_type,
                proposed_recipe_id=recommendation.recipe.id if recommendation else None,
                recipes_by_id=recipes_by_id,
            )
            after_grocery = self.grocery_aggregator.estimate(future_recipes, constraints)
            after_warnings = list(dict.fromkeys(after_grocery.warnings))
            if after_grocery.within_weekly_budget is False:
                after_warnings.append(
                    f"The revised ingredient-use cost S${after_grocery.consumed_total_sgd:.2f} exceeds the "
                    f"S${constraints.weekly_budget_sgd:.2f} weekly budget."
                )

        nutrition_delta = self._nutrition_delta(entry, request, recommendation)
        grocery_delta = self._grocery_delta(before_grocery, after_grocery)
        purchase_delta = round(after_grocery.purchase_total_sgd - before_grocery.purchase_total_sgd, 2)
        event = self.repository.create_replan_preview(
            plan=plan,
            entry=entry,
            proposed_recipe_id=recommendation.recipe.id if recommendation else None,
            event_type=request.event_type,
            reason=request.reason,
            unavailable_ingredient=request.unavailable_ingredient,
            before_entry=before_entry,
            after_entry=after_entry,
            after_grocery=after_grocery,
            after_warnings=after_warnings,
            nutrition_delta=nutrition_delta,
            grocery_delta=grocery_delta,
            purchase_total_delta_sgd=purchase_delta,
        )
        return self._event_response(event)

    def confirm(self, *, plan_id: int, event_id: int) -> MealPlanReplanConfirmationResponse:
        plan = self.repository.get(plan_id)
        event = self.repository.get_event(plan_id=plan_id, event_id=event_id)
        if plan is None or event is None:
            raise MealPlanReplanNotFoundError("Replanning preview not found")
        if event.status != "previewed" or event.base_revision != plan.revision:
            raise MealPlanReplanConflictError(
                "This preview is stale because the meal plan has changed. Generate a new preview."
            )

        recipes_by_id = {recipe.id: recipe for recipe in self.recipe_repository.list_for_recommendation()}
        proposed_recipe = recipes_by_id.get(event.proposed_recipe_id) if event.proposed_recipe_id else None
        grocery = WeeklyGroceryEstimateResponse.model_validate(event.after_grocery)
        try:
            applied_plan, applied_event = self.repository.apply_event(
                plan=plan,
                event=event,
                proposed_recipe=proposed_recipe,
                grocery=grocery,
            )
        except MealPlanRevisionConflictError as error:
            raise MealPlanReplanConflictError(
                "This preview is stale because the meal plan has changed. Generate a new preview."
            ) from error
        except LookupError as error:
            raise MealPlanReplanNotFoundError("The target meal or proposed recipe no longer exists") from error
        return MealPlanReplanConfirmationResponse(
            event=self._event_response(applied_event),
            plan=WeeklyMealPlanService._to_response(applied_plan),
        )

    def list_events(self, *, plan_id: int, limit: int) -> MealPlanReplanEventCollectionResponse:
        if self.repository.get(plan_id) is None:
            raise MealPlanReplanNotFoundError("Meal plan not found")
        return MealPlanReplanEventCollectionResponse(
            items=[self._event_response(event) for event in self.repository.list_events(plan_id=plan_id, limit=limit)]
        )

    def get_event(self, *, plan_id: int, event_id: int) -> MealPlanReplanEventResponse | None:
        event = self.repository.get_event(plan_id=plan_id, event_id=event_id)
        return self._event_response(event) if event is not None else None

    @staticmethod
    def _validate_target(entry: MealPlanEntry, request: MealPlanReplanPreviewRequest) -> None:
        if entry.status == "completed":
            raise MealPlanReplanValidationError("Completed meals are historical records and cannot be replanned.")
        if entry.is_locked:
            raise MealPlanReplanValidationError("This meal is locked and cannot be replanned.")
        if entry.status == "skipped" and request.event_type == "CANCEL_MEAL":
            raise MealPlanReplanValidationError("This meal is already cancelled.")

    def _select_replacement(
        self,
        *,
        plan: MealPlan,
        entry: MealPlanEntry,
        request: MealPlanReplanPreviewRequest,
        constraints: WeeklyMealPlanRequest,
        recipes_by_id: dict[int, Recipe],
    ) -> RecipeRecommendationResponse:
        result = self.recommendation_service.recommend(constraints, deduct_pantry_from_cost=False)
        candidates = [item for item in result.recommendations if item.recipe.id != entry.recipe_id]
        if request.unavailable_ingredient:
            candidates = [
                item
                for item in candidates
                if request.unavailable_ingredient
                not in {
                    ingredient.ingredient.normalized_name
                    for ingredient in recipes_by_id[item.recipe.id].recipe_ingredients
                }
            ]
        if not candidates:
            raise MealPlanReplanValidationError("No alternative recipe satisfies the current hard constraints.")

        ordered_entries = sorted(plan.entries, key=lambda item: item.day_index)
        target_index = ordered_entries.index(entry)
        previous_recipe_id = ordered_entries[target_index - 1].recipe_id if target_index > 0 else None
        next_recipe_id = (
            ordered_entries[target_index + 1].recipe_id if target_index + 1 < len(ordered_entries) else None
        )
        use_counts = Counter(
            item.recipe_id for item in ordered_entries if item.id != entry.id and item.status != "skipped"
        )

        def score(candidate: RecipeRecommendationResponse) -> tuple[float, int]:
            neighbor_penalty = 20.0 * (
                int(candidate.recipe.id == previous_recipe_id) + int(candidate.recipe.id == next_recipe_id)
            )
            value = candidate.total_score - use_counts[candidate.recipe.id] * 8.0 - neighbor_penalty
            return value, -candidate.recipe.id

        return max(candidates, key=score)

    @staticmethod
    def _recipes_after_event(
        *,
        plan: MealPlan,
        target: MealPlanEntry,
        event_type: str,
        proposed_recipe_id: int | None,
        recipes_by_id: dict[int, Recipe],
    ) -> list[Recipe]:
        recipes: list[Recipe] = []
        for entry in plan.entries:
            if entry.status == "skipped" or (entry.id == target.id and event_type == "CANCEL_MEAL"):
                continue
            recipe_id = (
                proposed_recipe_id if entry.id == target.id and proposed_recipe_id is not None else entry.recipe_id
            )
            recipe = recipes_by_id.get(recipe_id)
            if recipe is None:
                raise MealPlanReplanNotFoundError("A recipe used by this plan no longer exists")
            recipes.append(recipe)
        return recipes

    @staticmethod
    def _entry_snapshot(entry: MealPlanEntry) -> dict:
        nutrition = WeeklyMealPlanService._entry_nutrition(entry).model_dump(mode="json")
        return {
            "entry_id": entry.id,
            "recipe_id": entry.recipe_id,
            "recipe_slug": entry.recipe.slug,
            "recipe_title": entry.recipe.title,
            "status": entry.status,
            "is_locked": entry.is_locked,
            "recommendation_score": float(entry.recommendation_score),
            "consumed_cost_sgd": float(entry.consumed_cost_sgd),
            "purchase_cost_sgd": float(entry.purchase_cost_sgd),
            "nutrition_per_person": nutrition,
        }

    @staticmethod
    def _after_entry_snapshot(
        entry: MealPlanEntry,
        request: MealPlanReplanPreviewRequest,
        recommendation: RecipeRecommendationResponse | None,
    ) -> dict:
        snapshot = MealPlanReplanningService._entry_snapshot(entry)
        if request.event_type == "LOCK_MEAL":
            snapshot["is_locked"] = True
        elif request.event_type == "CANCEL_MEAL":
            snapshot["status"] = "skipped"
        elif recommendation is not None:
            estimate = recommendation.grocery_estimate
            snapshot.update(
                {
                    "recipe_id": recommendation.recipe.id,
                    "recipe_slug": recommendation.recipe.slug,
                    "recipe_title": recommendation.recipe.title,
                    "recommendation_score": recommendation.total_score,
                    "consumed_cost_sgd": estimate.consumed_total_sgd if estimate else 0,
                    "purchase_cost_sgd": estimate.purchase_total_sgd if estimate else 0,
                    "nutrition_per_person": recommendation.recipe.nutrition.model_dump(mode="json"),
                }
            )
        return snapshot

    @staticmethod
    def _nutrition_delta(
        entry: MealPlanEntry,
        request: MealPlanReplanPreviewRequest,
        recommendation: RecipeRecommendationResponse | None,
    ) -> dict:
        before = WeeklyMealPlanService._entry_nutrition(entry)
        fields = before.__class__.model_fields
        if request.event_type == "CANCEL_MEAL":
            after = {key: 0.0 for key in fields}
        elif recommendation is not None:
            after = recommendation.recipe.nutrition.model_dump()
        else:
            after = before.model_dump()
        return {key: round(float(after[key]) - float(getattr(before, key)), 2) for key in fields}

    @staticmethod
    def _current_grocery(plan: MealPlan) -> WeeklyGroceryEstimateResponse:
        lines = [WeeklyMealPlanService._grocery_line(item) for item in plan.grocery_items]
        unmapped = sorted(
            line.ingredient_name
            for line in lines
            if line.product is None and line.remaining_quantity != 0 and line.consumed_cost_sgd is None
        )
        return WeeklyGroceryEstimateResponse(
            pricing_mode=plan.pricing_mode,
            complete=not unmapped and all(line.consumed_cost_sgd is not None for line in lines),
            purchase_total_sgd=float(plan.purchase_total_sgd),
            consumed_total_sgd=float(plan.consumed_total_sgd) if plan.consumed_total_sgd is not None else None,
            weekly_budget_sgd=float(plan.weekly_budget_sgd) if plan.weekly_budget_sgd is not None else None,
            within_weekly_budget=plan.within_weekly_budget,
            items=lines,
            unmapped_ingredients=unmapped,
            warnings=list(plan.warnings),
        )

    @staticmethod
    def _grocery_delta(
        before: WeeklyGroceryEstimateResponse,
        after: WeeklyGroceryEstimateResponse,
    ) -> list[dict]:
        before_by_name = {item.ingredient_name: item for item in before.items}
        after_by_name = {item.ingredient_name: item for item in after.items}
        delta: list[dict] = []
        for name in sorted(before_by_name.keys() | after_by_name.keys()):
            old = before_by_name.get(name)
            new = after_by_name.get(name)
            if old is not None and new is not None:
                unchanged = (
                    old.required_quantity == new.required_quantity
                    and old.packages_required == new.packages_required
                    and round(old.purchase_cost_sgd, 2) == round(new.purchase_cost_sgd, 2)
                )
                if unchanged:
                    continue
                change = "updated"
            else:
                change = "added" if new is not None else "removed"
            source = new or old
            if source is None:
                continue
            delta.append(
                {
                    "ingredient_name": name,
                    "ingredient_display_name": source.ingredient_display_name,
                    "change": change,
                    "before_required_quantity": old.required_quantity if old else None,
                    "after_required_quantity": new.required_quantity if new else None,
                    "unit": source.unit,
                    "before_packages_required": old.packages_required if old else 0,
                    "after_packages_required": new.packages_required if new else 0,
                    "purchase_cost_delta_sgd": round(
                        (new.purchase_cost_sgd if new else 0) - (old.purchase_cost_sgd if old else 0),
                        2,
                    ),
                }
            )
        return delta

    @staticmethod
    def _event_response(event: MealPlanEvent) -> MealPlanReplanEventResponse:
        return MealPlanReplanEventResponse(
            id=event.id,
            plan_id=event.plan_id,
            base_revision=event.base_revision,
            applied_revision=event.applied_revision,
            event_type=event.event_type,
            status=event.status,
            reason=event.reason,
            unavailable_ingredient=event.unavailable_ingredient,
            before_entry=MealPlanEntrySnapshot.model_validate(event.before_entry),
            after_entry=MealPlanEntrySnapshot.model_validate(event.after_entry),
            nutrition_delta=MealPlanNutritionDelta.model_validate(event.nutrition_delta),
            grocery_delta=[MealPlanGroceryDeltaLine.model_validate(item) for item in event.grocery_delta],
            purchase_total_delta_sgd=float(event.purchase_total_delta_sgd),
            created_at=event.created_at,
            applied_at=event.applied_at,
        )
