from collections import Counter
from datetime import date, timedelta

from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanEvent
from app.models.recipe import Recipe
from app.planning import alternatives
from app.planning.meal_composition import meal_minutes, portion_shares
from app.planning.product_path import ProductPlanningError
from app.planning.recipe_similarity import RecipeSimilarity
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.repositories.meal_plan import MealPlanRepository, MealPlanRevisionConflictError, entry_values
from app.repositories.recipe import RecipeRepository
from app.schemas.meal_plan import (
    MealPlanEntrySnapshot,
    MealPlanGroceryDeltaLine,
    MealPlanNutritionDelta,
    MealPlanReplanConfirmationResponse,
    MealPlanReplanEventCollectionResponse,
    MealPlanReplanEventResponse,
    MealPlanReplanPreviewRequest,
    MealPlanShape,
    MealPlanShapeChange,
    MealPlanShapeChangeRequest,
    WeeklyGroceryEstimateResponse,
    WeeklyMealPlanRequest,
    week_shape,
)
from app.schemas.planning_v2 import PlanningCompositionPolicy
from app.schemas.recommendation import RecipeRecommendationResponse
from app.services.meal_plan import WeeklyMealPlanService
from app.services.recommendation import RecipeRecommendationService


def _at_share(value, share: float):
    """A dish's value at its portion share; a whole-meal dish keeps the value exactly."""
    return value if share == 1 else round(float(value) * share, 2)


class TimedDish:
    """The time fields `meal_minutes` reads, from a stored recipe (passive time is not cooking time)."""

    def __init__(self, prep: int, cook: int):
        self.prep_minutes, self.cook_minutes, self.passive_minutes = prep, cook, 0
        self.total_time_minutes = prep + cook

    @classmethod
    def of(cls, recipe: Recipe) -> "TimedDish":
        return cls(recipe.prep_time_minutes, recipe.cook_time_minutes)


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
        request_similarity: RecipeSimilarity | None = None,
        meal_plan_service: WeeklyMealPlanService | None = None,
    ) -> None:
        self.repository = repository
        self.recipe_repository = recipe_repository
        self.recommendation_service = recommendation_service
        self.grocery_aggregator = grocery_aggregator
        # Orders the candidates a swap may choose by what the household said they want instead.
        self.request_similarity = request_similarity
        # Plans the dishes of a shape change (ADR-0046 section 2).
        self.meal_plan_service = meal_plan_service

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
        role = self._role(constraints, entry)
        recipes = self.recipe_repository.list_for_planning(courses=list(role.courses) if role is not None else None)
        recipes_by_id = {recipe.id: recipe for recipe in recipes}
        # A planned recipe may sit outside today's candidate pool; fetch it directly.
        missing = [item.recipe_id for item in plan.entries if item.recipe_id not in recipes_by_id]
        recipes_by_id.update((recipe.id, recipe) for recipe in self.recipe_repository.list_by_ids(missing))
        recommendation: RecipeRecommendationResponse | None = None

        if request.event_type in {"REPLACE_MEAL", "ITEM_UNAVAILABLE"}:
            recommendation = self._select_replacement(
                plan=plan,
                entry=entry,
                request=request,
                constraints=constraints,
                recipes=recipes,
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
            after_grocery = self.grocery_aggregator.estimate(
                [recipe for recipe, _ in future_recipes], constraints, shares=[share for _, share in future_recipes]
            )
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

    def preview_shape(
        self, *, plan_id: int, request: MealPlanShapeChangeRequest, today: date | None = None
    ) -> MealPlanReplanEventResponse:
        """Add, drop or recompose one meal on the days still ahead; only those meals are planned again."""
        plan = self.repository.get(plan_id)
        if plan is None:
            raise MealPlanReplanNotFoundError("Meal plan not found")
        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints)
        meal = request.meal_type
        today = today or date.today()
        ahead = [day for day in range(1, 8) if plan.start_date + timedelta(days=day - 1) >= today]
        # A meal already cooked, or one the household locked, is left as it is.
        held = {
            item.day_index
            for item in plan.entries
            if item.meal_type == meal and (item.status == "completed" or item.is_locked)
        }
        days = [day for day in (request.day_indexes or ahead) if day in ahead and day not in held]
        if not days:
            raise MealPlanReplanValidationError(f"There is no {meal} left to change on those days.")
        removed = [item for item in plan.entries if item.meal_type == meal and item.day_index in days]
        if request.roles is None and not removed:
            raise MealPlanReplanValidationError(f"{meal.capitalize()} is not planned on those days.")

        new_shape = None
        if request.day_indexes is None:
            meals = dict(week_shape(plan.constraints).meals)
            if request.roles is None:
                meals.pop(meal, None)
            else:
                meals[meal] = request.roles
            if not meals:
                raise MealPlanReplanValidationError("A week plans at least one meal a day.")
            new_shape = MealPlanShape(meals=meals)

        kept = [item for item in plan.entries if item not in removed and item.status != "skipped"]
        # Taking a dish away keeps the others (at their larger share); anything else plans the meal again.
        staying = self._dishes_staying(removed, request.roles)
        if staying is not None:
            added = staying
        elif request.roles:
            added = self._plan_meal(constraints, meal, request.roles, days, kept, removed)
        else:
            added = []
        stays = {values["recipe_id"] for values, _ in added} if staying is not None else set()

        wanted_ids = {item.recipe_id for item in kept} | {values["recipe_id"] for values, _ in added}
        recipes_by_id = {recipe.id: recipe for recipe in self.recipe_repository.list_by_ids(list(wanted_ids))}
        eaten = [(recipes_by_id[item.recipe_id], float(item.portion_share)) for item in kept]
        eaten += [(recipes_by_id[values["recipe_id"]], values["portion_share"]) for values, _ in added]
        after_grocery = self.grocery_aggregator.estimate(
            [recipe for recipe, _ in eaten], constraints, shares=[share for _, share in eaten]
        )
        after_warnings = list(dict.fromkeys(after_grocery.warnings))
        if after_grocery.within_weekly_budget is False:
            after_warnings.append(
                f"The revised ingredient-use cost S${after_grocery.consumed_total_sgd:.2f} exceeds the "
                f"S${constraints.weekly_budget_sgd:.2f} weekly budget."
            )
        before_grocery = self._current_grocery(plan)
        fields = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
        eaten_before = [item for item in removed if item.status != "skipped"]
        nutrition_delta = {
            field: round(
                sum(values[field] for values, _ in added) - sum(float(getattr(item, field)) for item in eaten_before),
                2,
            )
            for field in fields
        }
        change = MealPlanShapeChange(
            meal_type=meal,
            scope="meal" if request.day_indexes else "week",
            day_indexes=days,
            roles=request.roles,
            removed=[
                MealPlanEntrySnapshot.model_validate(self._entry_snapshot(item))
                for item in removed
                if item.recipe_id not in stays
            ],
            added=[snapshot for _, snapshot in added if staying is None],
            plan_shape=new_shape,
        )
        event = self.repository.create_shape_preview(
            plan=plan,
            reason=request.reason,
            shape_change={
                **change.model_dump(mode="json"),
                "removed_entry_ids": [item.id for item in removed],
                "new_entries": [values for values, _ in added],
            },
            after_grocery=after_grocery,
            after_warnings=after_warnings,
            nutrition_delta=nutrition_delta,
            grocery_delta=self._grocery_delta(before_grocery, after_grocery),
            purchase_total_delta_sgd=round(after_grocery.purchase_total_sgd - before_grocery.purchase_total_sgd, 2),
        )
        return self._event_response(event)

    @staticmethod
    def _dishes_staying(removed: list[MealPlanEntry], roles) -> list[tuple[dict, MealPlanEntrySnapshot]] | None:
        """When a change only takes dishes away, the ones left at their new shares; None otherwise."""
        if not roles or not removed:
            return None
        wanted = {role.role_id for role in roles}
        by_day: dict[int, list[MealPlanEntry]] = {}
        for item in removed:
            by_day.setdefault(item.day_index, []).append(item)
        if any(not wanted < {item.role_id for item in dishes} for dishes in by_day.values()):
            return None
        staying = []
        policy = PlanningCompositionPolicy()
        for dishes in by_day.values():
            left = [item for item in dishes if item.role_id in wanted]
            shares = portion_shares(policy, [item.role_id for item in left]) or {}
            for item in left:
                share = float(shares.get(item.role_id, 1))
                values = MealPlanReplanningService._rescaled(item, share)
                snapshot = MealPlanEntrySnapshot.model_validate(
                    {**MealPlanReplanningService._entry_snapshot(item), "portion_share": share}
                )
                staying.append((values, snapshot))
        return staying

    @staticmethod
    def _rescaled(item: MealPlanEntry, share: float) -> dict:
        """A kept dish's stored values at a new portion share."""
        ratio = share / float(item.portion_share)
        scaled = (
            "consumed_cost_sgd",
            "purchase_cost_sgd",
            "calories_kcal",
            "protein_g",
            "carbohydrate_g",
            "fat_g",
            "sodium_mg",
            "sugar_g",
        )
        return {
            "recipe_id": item.recipe_id,
            "day_index": item.day_index,
            "planned_date": item.planned_date.isoformat(),
            "meal_type": item.meal_type,
            "role_id": item.role_id,
            "portion_share": round(share, 3),
            "recommendation_score": float(item.recommendation_score),
            **{field: round(float(getattr(item, field)) * ratio, 2) for field in scaled},
        }

    @staticmethod
    def _dishes_kept_when_adding(roles, present: list[MealPlanEntry]) -> tuple[set[int], set[str]] | None:
        """Adding a dish to one meal keeps what it has: the present recipes, and the courses only they
        may fill. None when the change is not purely an addition."""
        present_roles = {item.role_id for item in present if item.status != "skipped"}
        if not present_roles or not present_roles < {role.role_id for role in roles}:
            return None
        held = {course for role in roles if role.role_id in present_roles for course in role.courses}
        new = {course for role in roles if role.role_id not in present_roles for course in role.courses}
        return {item.recipe_id for item in present}, held - new

    def _plan_meal(self, constraints, meal, roles, days, kept, removed) -> list[tuple[dict, MealPlanEntrySnapshot]]:
        """The new dishes of `meal` on `days`, planned with the budget the rest of the week leaves."""
        if self.meal_plan_service is None:
            raise MealPlanReplanValidationError("Changing meals is not available here.")
        budget = constraints.weekly_budget_sgd
        if budget is not None:
            budget = round(budget - sum(float(item.consumed_cost_sgd) for item in kept), 2)
            if budget <= 0:
                raise MealPlanReplanValidationError(
                    "The rest of the week already uses the whole weekly budget, so there is none left for this."
                )
        partial = constraints.model_copy(
            update={
                "plan_shape": MealPlanShape(meals={meal: roles}),
                "meal_composition": None,
                "weekly_budget_sgd": budget,
            }
        )
        first, last = min(days), max(days)
        try:
            dishes = self.meal_plan_service.plan_dishes(
                partial,
                first_day=first,
                day_count=last - first + 1,
                avoid_recipe_ids={item.recipe_id for item in kept},
                keep=self._dishes_kept_when_adding(roles, [item for item in removed if len(days) == 1]),
            )
        except ProductPlanningError as error:
            raise MealPlanReplanValidationError(f"I could not plan that: {error}") from error
        added = []
        for dish in dishes:
            if dish.day_index not in days:
                continue
            values = entry_values(dish)
            recipe = dish.recommendation.recipe
            snapshot = MealPlanEntrySnapshot(
                entry_id=0,  # not saved yet
                day_index=dish.day_index,
                meal_type=dish.meal_type,
                role_id=dish.role_id,
                portion_share=values["portion_share"],
                recipe_id=recipe.id,
                recipe_slug=recipe.slug,
                recipe_title=recipe.title,
                status="planned",
                is_locked=False,
                recommendation_score=values["recommendation_score"],
            )
            added.append((values, snapshot))
        return added

    def confirm(self, *, plan_id: int, event_id: int) -> MealPlanReplanConfirmationResponse:
        plan = self.repository.get(plan_id)
        event = self.repository.get_event(plan_id=plan_id, event_id=event_id)
        if plan is None or event is None:
            raise MealPlanReplanNotFoundError("Replanning preview not found")
        if event.status != "previewed" or event.base_revision != plan.revision:
            raise MealPlanReplanConflictError(
                "This preview is stale because the meal plan has changed. Generate a new preview."
            )

        proposed = self.recipe_repository.list_by_ids([event.proposed_recipe_id] if event.proposed_recipe_id else [])
        proposed_recipe = proposed[0] if proposed else None
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
        recipes: list[Recipe],
        recipes_by_id: dict[int, Recipe],
    ) -> RecipeRecommendationResponse:
        result = self.recommendation_service.recommend(
            constraints, deduct_pantry_from_cost=False, recipes=recipes, priced_release_only=True
        )
        candidates = [item for item in result.recommendations if item.recipe.id != entry.recipe_id]
        if request.unavailable_ingredient:
            candidates = [
                item
                for item in candidates
                if request.unavailable_ingredient
                not in {
                    ingredient.ingredient.normalized_name
                    for ingredient in alternatives.lines(recipes_by_id[item.recipe.id], constraints)
                }
            ]
        role = self._role(constraints, entry)
        if role is not None:
            # One dish of a composed meal: it fills the same role, and the meal must still hold
            # as a meal with the dishes that stay (ADR-0036; the owner chose to swap one dish).
            candidates = [
                item
                for item in candidates
                if (recipes_by_id[item.recipe.id].course or "main") in role.courses
                and self._meal_still_holds(plan, entry, recipes_by_id[item.recipe.id], constraints)
            ]
        if not candidates:
            raise MealPlanReplanValidationError("No alternative recipe satisfies the current hard constraints.")

        # The same dish position on the neighbouring days, so a swap does not repeat them.
        def neighbour(offset: int) -> int | None:
            return next(
                (
                    item.recipe_id
                    for item in plan.entries
                    if item.day_index == entry.day_index + offset
                    and item.meal_type == entry.meal_type
                    and item.role_id == entry.role_id
                ),
                None,
            )

        previous_recipe_id, next_recipe_id = neighbour(-1), neighbour(1)
        use_counts = Counter(
            item.recipe_id for item in plan.entries if item.id != entry.id and item.status != "skipped"
        )

        # "Can Wednesday be fish instead?": among the candidates that already hold every hard constraint,
        # what was asked for leads and the recommendation score only breaks near-ties. Nothing described,
        # no vectors or no key: the swap orders by score, as before.
        asked = (
            self.request_similarity.scores(request.reason, [recipes_by_id[c.recipe.id] for c in candidates])
            if self.request_similarity is not None and request.event_type == "REPLACE_MEAL"
            else {}
        )

        def score(candidate: RecipeRecommendationResponse) -> tuple[float, int]:
            neighbor_penalty = 20.0 * (
                int(candidate.recipe.id == previous_recipe_id) + int(candidate.recipe.id == next_recipe_id)
            )
            # A recipe with no stored vector (added after the vectors were made) competes on its score alone.
            fit = (
                100.0 * asked.get(candidate.recipe.id, 0.0) + 0.05 * candidate.total_score
                if asked
                else candidate.total_score
            )
            value = fit - use_counts[candidate.recipe.id] * 8.0 - neighbor_penalty
            return value, -candidate.recipe.id

        return max(candidates, key=score)

    @staticmethod
    def _role(constraints: WeeklyMealPlanRequest, entry: MealPlanEntry):
        """The dish role an entry fills in a composed plan, or None for a one-dish plan."""
        roles = (
            constraints.plan_shape.meals.get(entry.meal_type)
            if constraints.plan_shape is not None
            else constraints.meal_composition
        )
        return next((role for role in roles or [] if role.role_id == entry.role_id), None)

    @staticmethod
    def _meal_still_holds(plan: MealPlan, entry: MealPlanEntry, candidate: Recipe, constraints) -> bool:
        """A replacement keeps its meal's distinct dishes, one-cook time and per-meal sodium ceiling."""
        others = [
            item
            for item in plan.entries
            if item.day_index == entry.day_index
            and item.meal_type == entry.meal_type
            and item.id != entry.id
            and item.status != "skipped"
        ]
        if candidate.id in {item.recipe_id for item in others}:
            return False
        dishes = [TimedDish.of(item.recipe) for item in others] + [TimedDish.of(candidate)]
        limit = constraints.max_cooking_time_minutes
        if limit is not None and meal_minutes(dishes, PlanningCompositionPolicy()) > limit:
            return False
        ceiling = constraints.max_sodium_mg_per_meal
        if ceiling is not None and candidate.nutrition is not None:
            sodium = sum(float(item.sodium_mg) for item in others)
            sodium += float(candidate.nutrition.sodium_mg) * float(entry.portion_share)
            if sodium > ceiling + 1e-6:
                return False
        return True

    @staticmethod
    def _recipes_after_event(
        *,
        plan: MealPlan,
        target: MealPlanEntry,
        event_type: str,
        proposed_recipe_id: int | None,
        recipes_by_id: dict[int, Recipe],
    ) -> list[tuple[Recipe, float]]:
        """Each dish still eaten after the event, with its portion share."""
        recipes: list[tuple[Recipe, float]] = []
        for entry in plan.entries:
            if entry.status == "skipped" or (entry.id == target.id and event_type == "CANCEL_MEAL"):
                continue
            recipe_id = (
                proposed_recipe_id if entry.id == target.id and proposed_recipe_id is not None else entry.recipe_id
            )
            recipe = recipes_by_id.get(recipe_id)
            if recipe is None:
                raise MealPlanReplanNotFoundError("A recipe used by this plan no longer exists")
            recipes.append((recipe, float(entry.portion_share)))
        return recipes

    @staticmethod
    def _entry_snapshot(entry: MealPlanEntry) -> dict:
        nutrition = WeeklyMealPlanService._entry_nutrition(entry).model_dump(mode="json")
        return {
            "entry_id": entry.id,
            "day_index": entry.day_index,
            "meal_type": entry.meal_type,
            "role_id": entry.role_id,
            "portion_share": float(entry.portion_share),
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
            share = float(entry.portion_share)
            snapshot.update(
                {
                    "recipe_id": recommendation.recipe.id,
                    "recipe_slug": recommendation.recipe.slug,
                    "recipe_title": recommendation.recipe.title,
                    "recommendation_score": recommendation.total_score,
                    # The new dish is eaten at the replaced dish's share of the meal.
                    "consumed_cost_sgd": _at_share(estimate.consumed_total_sgd, share) if estimate else 0,
                    "purchase_cost_sgd": _at_share(estimate.purchase_total_sgd, share) if estimate else 0,
                    "nutrition_per_person": {
                        key: _at_share(value, share)
                        for key, value in recommendation.recipe.nutrition.model_dump(mode="json").items()
                    },
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
            share = float(entry.portion_share)
            after = {
                key: _at_share(value, share) for key, value in recommendation.recipe.nutrition.model_dump().items()
            }
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
            before_entry=MealPlanEntrySnapshot.model_validate(event.before_entry) if event.before_entry else None,
            after_entry=MealPlanEntrySnapshot.model_validate(event.after_entry) if event.after_entry else None,
            shape_change=MealPlanShapeChange.model_validate(event.shape_change) if event.shape_change else None,
            nutrition_delta=MealPlanNutritionDelta.model_validate(event.nutrition_delta),
            grocery_delta=[MealPlanGroceryDeltaLine.model_validate(item) for item in event.grocery_delta],
            purchase_total_delta_sgd=float(event.purchase_total_delta_sgd),
            created_at=event.created_at,
            applied_at=event.applied_at,
        )
