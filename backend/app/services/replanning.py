from collections import Counter
from datetime import date, timedelta
from fractions import Fraction

from app.core.clock import today as local_today
from app.data import meal_structure
from app.data.household_reference import hpb
from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanEvent
from app.models.recipe import Recipe
from app.planning import alternatives
from app.planning.household_slots import limit_targets, rules_on, slot_members, slot_time_limit
from app.planning.meal_composition import (
    catalog_role_admits,
    equipment_met,
    fills_staple,
    meal_minutes,
    meal_role_of,
    portion_shares,
    role_base,
    structured_shares,
)
from app.planning.member_coverage import CoverageDish, catalog_can_eat, coverage_failures
from app.planning.product_path import ProductPlanningError, meal_affinity, meals_of_the_day, pool_courses, pool_for
from app.planning.recipe_quality import dish_family
from app.planning.recipe_similarity import RecipeSimilarity
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.repositories.meal_plan import (
    MealPlanRepository,
    MealPlanRevisionConflictError,
    ScheduledDish,
    entry_values,
    grocery_share,
)
from app.repositories.recipe import RecipeRepository
from app.schemas.display import shown_title
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
from app.schemas.planning_v2 import STAPLE_ROLE, PlanningCompositionPolicy, core_role, structured
from app.schemas.recommendation import RecipeRecommendationResponse
from app.services.meal_plan import WeeklyMealPlanService, pool_constraints
from app.services.recommendation import RecipeRecommendationService


def by_weight(grocery: WeeklyGroceryEstimateResponse) -> set[str]:
    """What the list buys by weight. A change keeps it so: the week was planned with a dish that measures
    milk in grams, and a swap keeps buying the milk the other dishes measure in millilitres by weight."""
    return {line.ingredient_name for line in grocery.items if line.unit == "g"}


def _at_share(value, share: float):
    """A dish's value at its portion share; a whole-meal dish keeps the value exactly."""
    return value if share == 1 else round(float(value) * share, 2)


def _values_share(values: dict, household_size: int) -> float:
    """An unsaved dish's share of a household-size batch (`grocery_share`), from its `entry_values`."""
    if values.get("servings") is None:
        return values["portion_share"]
    return values["servings"] / household_size


def _same_quantity(before: float | None, after: float | None) -> bool:
    """Equal to the saved list's precision (three decimals)."""
    if before is None or after is None:
        return before == after
    return abs(before - after) < 0.001


class TimedDish:
    """The time fields `meal_minutes` reads, from a stored recipe (passive time is not cooking time)."""

    def __init__(self, prep: int, cook: int, meal_role: str | None = None):
        self.prep_minutes, self.cook_minutes, self.passive_minutes = prep, cook, 0
        self.total_time_minutes = prep + cook
        self.meal_role = meal_role

    @classmethod
    def of(cls, recipe: Recipe) -> "TimedDish":
        return cls(recipe.prep_time_minutes, recipe.cook_time_minutes, getattr(recipe, "meal_role", None))


# A structured meal's time reads its staple as cooking unattended (meal-structure-v1 `staple_hands_off_cook`).
STRUCTURED_TIME = PlanningCompositionPolicy(staple_hands_off_cook=True)


def entry_trips(plan: MealPlan, entries) -> list[int | None] | None:
    """Each dish's shopping trip in a plan longer than a week (ADR-0072: day 8 on is the second); None for one."""
    if getattr(plan, "day_count", 7) <= meal_structure.trip_days():
        return None
    return [1 + (entry.day_index - 1) // meal_structure.trip_days() for entry in entries]


# A described swap ("something with fish") chooses, within the budget, among this many of the dishes most like
# what was asked for (ADR-0042 orders them).
ASKED_ALIKE = 10


class _Day:
    """A dish's day number, for `entry_trips`."""

    def __init__(self, day_index: int):
        self.day_index = day_index


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

        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints).model_copy(
            update={"pricing_mode": "fixture"}
        )
        role = self._role(constraints, entry)
        meals = [(entry.meal_type, [role])] if role is not None else None
        recipes = pool_for(meals, self.recipe_repository.list_for_planning(courses=pool_courses(meals)))
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
        if request.whole_meal:
            # Every dish of the meal still to cook is kept with it, in one preview.
            before_entry["meal_entries"] = [
                self._entry_snapshot(item)
                for item in plan.entries
                if item.day_index == entry.day_index
                and item.meal_type == entry.meal_type
                and (item.id == entry.id or not (item.is_locked or item.status in {"completed", "skipped"}))
            ]
        # The new dish is cooked for the members home for that meal who can eat it (ADR-0071 section 1).
        swapped = (
            self._swap_servings(constraints, entry, recipes_by_id[recommendation.recipe.id])
            if recommendation is not None
            else None
        )
        after_entry = self._after_entry_snapshot(entry, request, recommendation, plan.household_size, swapped)
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
                swapped_servings=swapped,
            )
            after_grocery = self._as_saved(
                plan,
                self.grocery_aggregator.estimate(
                    [recipe for recipe, _, _ in future_recipes],
                    constraints,
                    shares=[share for _, share, _ in future_recipes],
                    by_weight=by_weight(before_grocery),
                    trips=entry_trips(plan, [item for _, _, item in future_recipes]),
                ),
                self._drift_cents(plan, constraints, recipes_by_id),
            )
            after_warnings = list(dict.fromkeys(after_grocery.warnings))
            if after_grocery.within_weekly_budget is False:
                after_warnings.append(
                    f"The revised grocery total S${after_grocery.purchase_total_sgd:.2f} exceeds the "
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
        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints).model_copy(
            update={"pricing_mode": "fixture"}
        )
        meal = request.meal_type
        today = today or local_today()
        if any(day > plan.day_count for day in request.day_indexes or []):
            raise MealPlanReplanValidationError(f"This plan has {plan.day_count} days.")
        ahead = [day for day in range(1, plan.day_count + 1) if plan.start_date + timedelta(days=day - 1) >= today]
        # A meal already cooked, or one the household locked, is left as it is.
        held = {
            item.day_index
            for item in plan.entries
            if item.meal_type == meal and (item.status == "completed" or item.is_locked)
        }
        days = [day for day in (request.day_indexes or ahead) if day in ahead and day not in held]
        if not days:
            # Every day named has passed: say which, rather than that nothing is "left".
            past = [plan.start_date + timedelta(days=day - 1) for day in request.day_indexes or [] if day not in ahead]
            if past and len(past) == len(request.day_indexes or []):
                named = " and ".join(f"{day:%A} {day.day} {day:%b}" for day in past)
                verb = "have" if len(past) > 1 else "has"
                raise MealPlanReplanValidationError(f"{named} {verb} already passed, so its {meal} cannot change.")
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
        before_grocery = self._current_grocery(plan)
        # Taking a dish away keeps the others (at their larger share); anything else plans the meal again.
        staying = self._dishes_staying(removed, request.roles)
        if staying is not None:
            added = staying
        elif request.roles:
            added = self._plan_meal(constraints, meal, request.roles, days, kept, removed, by_weight(before_grocery))
        else:
            added = []
        # A dish that stays on its day, when a dish is taken away or added, is neither taken off nor new.
        planned = {(values["day_index"], values["recipe_id"]) for values, _ in added}
        stays = [item for item in removed if item.status != "skipped" and (item.day_index, item.recipe_id) in planned]
        kept_on = {(item.day_index, item.recipe_id) for item in stays}

        wanted_ids = {item.recipe_id for item in kept} | {values["recipe_id"] for values, _ in added}
        recipes_by_id = {recipe.id: recipe for recipe in self.recipe_repository.list_by_ids(list(wanted_ids))}
        eaten = [(recipes_by_id[item.recipe_id], grocery_share(item, plan.household_size)) for item in kept]
        eaten += [
            (recipes_by_id[values["recipe_id"]], _values_share(values, plan.household_size)) for values, _ in added
        ]
        days_of = [item.day_index for item in kept] + [values["day_index"] for values, _ in added]
        after_grocery = self.grocery_aggregator.estimate(
            [recipe for recipe, _ in eaten],
            constraints,
            shares=[share for _, share in eaten],
            by_weight=by_weight(before_grocery),
            trips=entry_trips(plan, [_Day(day) for day in days_of]),
        )
        after_warnings = list(dict.fromkeys(after_grocery.warnings))
        if after_grocery.within_weekly_budget is False:
            after_warnings.append(
                f"The revised grocery total S${after_grocery.purchase_total_sgd:.2f} exceeds the "
                f"S${constraints.weekly_budget_sgd:.2f} weekly budget."
            )
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
                if item not in stays
            ],
            added=[snap for values, snap in added if (values["day_index"], values["recipe_id"]) not in kept_on],
            kept=len(stays),
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

    def preview_variety(
        self, *, plan_id: int, reason: str | None = None
    ) -> tuple[MealPlanReplanEventResponse | None, int, float | None]:
        """The week's repeated dishes swapped for dishes it does not have, within its budget, as one preview.

        "The dishes are boring" (菜很单调) asks for this, not a new week (owner, 2026-10-04). Of each dish served
        more than once, one stays (a cooked or locked one first) and every other one not yet cooked or locked
        is swapped for the best-ranked dish of its role the week does not serve, each in turn while the week
        stays within its budget (`_fitting`). Returns the preview (None when no swap fits), how many repeats
        there were, and when some did not fit, the least any of them would take the week over what it can spend
        with a dish that exists (None when nothing fits at any price, or nothing was left over).
        """
        plan = self.repository.get(plan_id)
        if plan is None:
            raise MealPlanReplanNotFoundError("Meal plan not found")
        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints).model_copy(
            update={"pricing_mode": "fixture"}
        )
        eaten = sorted((item for item in plan.entries if item.status != "skipped"), key=lambda e: (e.day_index, e.id))
        same: dict[str, list[MealPlanEntry]] = {}
        for item in eaten:
            same.setdefault(dish_family(item.recipe.title), []).append(item)
        repeats = []
        for dishes in same.values():
            fixed = [item for item in dishes if item.status == "completed" or item.is_locked]
            stays = fixed or dishes[:1]
            repeats += [
                item for item in dishes if item not in stays and not item.is_locked and item.status == "planned"
            ]
        repeats.sort(key=lambda e: (e.day_index, e.id))
        if not repeats:
            return None, 0, None
        # The planner's own candidates for the week (services/meal_plan.py `_candidates`): the recipes it loaded
        # for the week's courses are kept for a while, and one ranking serves every role.
        meals = meals_of_the_day(constraints)
        recipes = pool_for(meals, self.recipe_repository.list_for_planning(courses=pool_courses(meals)))
        pool = self.recommendation_service.recommend(
            pool_constraints(constraints), deduct_pantry_from_cost=False, recipes=recipes, priced_release_only=True
        ).recommendations
        recipes_by_id = {recipe.id: recipe for recipe in recipes}
        missing = [item.recipe_id for item in eaten if item.recipe_id not in recipes_by_id]
        recipes_by_id.update((recipe.id, recipe) for recipe in self.recipe_repository.list_by_ids(missing))
        served = set(same)
        swaps: dict[int, RecipeRecommendationResponse] = {}
        short = None
        changed: set[tuple[int, str]] = set()
        # The dishes that took the week over in place of one repeat of a dish are not tried for its next: the
        # week differs only by the swaps made meanwhile, each within what it can spend.
        # ponytail: a swap that freed room could let one fit; trying every dish again for every repeat took a
        # week of seventeen repeats 15 s (ADR-0046 section 3: an answer within 10 s).
        misfits: dict[tuple, set[int]] = {}
        for entry in repeats:
            if (entry.day_index, entry.meal_type) in changed:
                continue  # one dish a meal: a meal is checked with the dishes it keeps (`_meal_still_holds`)
            candidates = self._replacements(plan, entry, constraints, pool, recipes_by_id, avoid=served)
            tried = misfits.setdefault((entry.meal_type, entry.role_id, dish_family(entry.recipe.title)), set())
            ranked = sorted(
                (c for c in candidates if c.recipe.id not in tried),
                key=lambda c: (c.total_score, -c.recipe.id),
                reverse=True,
            )
            if not ranked:
                continue
            made = {entry_id: choice.recipe.id for entry_id, choice in swaps.items()}
            choice, extra = self._fitting(plan, constraints, recipes_by_id, made, entry, ranked, tried)
            if extra is not None:
                short = extra if short is None else min(short, extra)
                continue
            swaps[entry.id] = choice
            served.add(dish_family(choice.recipe.title))
            changed.add((entry.day_index, entry.meal_type))
        if not swaps:
            return None, len(repeats), short
        removed = [item for item in repeats if item.id in swaps]
        added = []
        for item in removed:
            values = entry_values(
                ScheduledDish(
                    planned_date=item.planned_date,
                    day_index=item.day_index,
                    meal_type=item.meal_type,
                    role_id=item.role_id,
                    portion_share=Fraction(str(item.portion_share)),
                    recommendation=swaps[item.id],
                    # The new dish is cooked for the members who can eat it (ADR-0071 section 1).
                    servings=self._swap_servings(constraints, item, recipes_by_id[swaps[item.id].recipe.id]),
                    household_size=plan.household_size,
                )
            )
            recipe = swaps[item.id].recipe
            snapshot = MealPlanEntrySnapshot(
                entry_id=0,  # not saved yet
                day_index=item.day_index,
                meal_type=item.meal_type,
                role_id=item.role_id,
                portion_share=values["portion_share"],
                recipe_id=recipe.id,
                recipe_slug=recipe.slug,
                recipe_title=recipe.title,
                status="planned",
                is_locked=False,
                recommendation_score=values["recommendation_score"],
            )
            added.append((values, snapshot))
        after_grocery = self._as_saved(
            plan,
            self._week_grocery(
                plan, constraints, recipes_by_id, {entry_id: choice.recipe.id for entry_id, choice in swaps.items()}
            ),
            self._drift_cents(plan, constraints, recipes_by_id),
        )
        after_warnings = list(dict.fromkeys(after_grocery.warnings))
        if after_grocery.within_weekly_budget is False:
            # Over already (a change the household took over the budget), and no further over.
            after_warnings.append(
                f"The revised grocery total S${after_grocery.purchase_total_sgd:.2f} exceeds the "
                f"S${constraints.weekly_budget_sgd:.2f} weekly budget."
            )
        before_grocery = self._current_grocery(plan)
        fields = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")
        meal = removed[0].meal_type
        change = MealPlanShapeChange(
            # A swap changes no meal's dishes or roles: the meal of the first swap names it, with its roles.
            meal_type=meal,
            scope="meal",
            day_indexes=sorted({item.day_index for item in removed}),
            roles=week_shape(plan.constraints).meals.get(meal),
            removed=[MealPlanEntrySnapshot.model_validate(self._entry_snapshot(item)) for item in removed],
            added=[snapshot for _, snapshot in added],
        )
        event = self.repository.create_shape_preview(
            plan=plan,
            reason=reason,
            shape_change={
                **change.model_dump(mode="json"),
                "removed_entry_ids": [item.id for item in removed],
                "new_entries": [values for values, _ in added],
            },
            after_grocery=after_grocery,
            after_warnings=after_warnings,
            nutrition_delta={
                field: round(
                    sum(values[field] for values, _ in added) - sum(float(getattr(item, field)) for item in removed), 2
                )
                for field in fields
            },
            grocery_delta=self._grocery_delta(before_grocery, after_grocery),
            purchase_total_delta_sgd=round(after_grocery.purchase_total_sgd - before_grocery.purchase_total_sgd, 2),
        )
        return self._event_response(event), len(repeats), short

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
            if structured(roles):
                pairs = [(item.role_id, item.recipe) for item in left]
                ids = [role for role, _ in pairs]
                bowl = STAPLE_ROLE not in ids and any(role_base(r) == "main" and fills_staple(x) for r, x in pairs)
                mains, vegetables = (sum(role_base(r) == kind for r in ids) for kind in ("main", "vegetable"))
                shares = structured_shares(policy, ids, mains, vegetables, bowl, pairs)
            else:
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
            "servings": round(float(item.servings) * ratio, 3) if item.servings is not None else None,
            "recommendation_score": float(item.recommendation_score),
            **{field: round(float(getattr(item, field)) * ratio, 2) for field in scaled},
        }

    @staticmethod
    def _dishes_kept_when_adding(roles, present: list[MealPlanEntry]) -> dict[tuple[int, str], dict[str, int]] | None:
        """Adding a dish to a meal keeps what each day's meal has, each dish in its role: (day, meal) -> {role
        id: recipe id}. None when the change is not purely an addition."""
        wanted = {role.role_id for role in roles}
        kept: dict[tuple[int, str], dict[str, int]] = {}
        for item in present:
            if item.status != "skipped":
                kept.setdefault((item.day_index, item.meal_type), {})[item.role_id] = item.recipe_id
        if not kept or not all(set(dishes) <= wanted for dishes in kept.values()):
            return None
        if all(set(dishes) == wanted for dishes in kept.values()):
            return None  # nothing is added
        return kept

    def _plan_meal(
        self, constraints, meal, roles, days, kept, removed, weighed: set[str]
    ) -> list[tuple[dict, MealPlanEntrySnapshot]]:
        """The new dishes of `meal` on `days`, planned with the budget the rest of the week leaves.

        `weighed` is what the week's list buys by weight (`by_weight`); the rest of the week is priced so.

        When nothing fits what is left (with the meal's present dishes kept, when a dish is added), the change is
        still planned, as cheaply as the planner finds (see `plan_dishes`), and its preview says how far over
        the budget it goes; the household confirms or discards it, as with a swap (owner decision 2026-10-02).
        A new week keeps its budget as a hard limit.
        """
        if self.meal_plan_service is None:
            raise MealPlanReplanValidationError("Changing meals is not available here.")
        budget = constraints.weekly_budget_sgd
        recipes = {r.id: r for r in self.recipe_repository.list_by_ids(list({i.recipe_id for i in kept}))}
        rest = [(recipes[item.recipe_id], grocery_share(item, constraints.household_size)) for item in kept]
        left = None
        if budget is not None and constraints.day_count <= meal_structure.trip_days():
            # What is left is what the rest of the week does not spend at the checkout, in whole packages:
            # what its dishes use leaves room the week has already paid for, and a plan made to fit that
            # room would go over the budget without trying the cheapest plans first.
            paid = self.grocery_aggregator.estimate(
                [recipe for recipe, _ in rest], constraints, shares=[share for _, share in rest], by_weight=weighed
            ).purchase_total_sgd
            left = round(budget - paid, 2)
        partial = constraints.model_copy(
            update={
                "plan_shape": MealPlanShape(meals={meal: roles}),
                "meal_composition": None,
                "weekly_budget_sgd": budget if constraints.day_count > meal_structure.trip_days() else left,
            }
        )
        first = min(days)
        over_budget = None
        if budget is not None:
            # Over the budget, costs are weighed against one meal's share of the weekly budget (budget / the
            # week's meals, as the week was planned) for each meal planned here: each search divides this by those
            # meals, so a repeat costs one meal's share. A day's share, or what is left when cheap meals left more
            # of it, made a repeat up to twice as dear on two meals a day: dear varied changes beat the cheapest.
            meals = len({(item.day_index, item.meal_type) for item in kept} | {(day, meal) for day in days})
            over_budget = round(budget * len(days) / meals, 2)
        try:
            dishes = self.meal_plan_service.plan_dishes(
                partial,
                first_day=first,
                day_count=len(days),
                day_indices=sorted(days),
                rest=rest,
                rest_days=[item.day_index for item in kept],
                keep=self._dishes_kept_when_adding(roles, removed),
                over_budget=over_budget,
                by_weight=weighed,
            )
        except ProductPlanningError as error:
            raise MealPlanReplanValidationError(str(error)) from error
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
        present = self._dishes_kept_when_adding(roles, removed)
        if present is not None and all(
            values["role_id"] in present.get((values["day_index"], meal), {}) for values, _ in added
        ):
            # An addition that adds nothing is never a silent no-op (owner decision 2026-10-09).
            raise MealPlanReplanValidationError(
                f"Nothing could be added to {meal} on those days: no suitable dish was found, even over the budget."
            )
        return added

    def confirm(self, *, plan_id: int, event_id: int) -> MealPlanReplanConfirmationResponse:
        plan = self.repository.get(plan_id)
        event = self.repository.get_event(plan_id=plan_id, event_id=event_id)
        if plan is None or event is None:
            raise MealPlanReplanNotFoundError("Replanning preview not found")
        if not self.repository.is_current(plan):
            raise MealPlanReplanConflictError("This week was replaced. Open the current week to make changes.")
        if event.status != "previewed" or event.base_revision != plan.revision:
            raise MealPlanReplanConflictError(
                "This preview is stale because the meal plan has changed. Generate a new preview."
            )

        proposed = self.recipe_repository.list_by_ids([event.proposed_recipe_id] if event.proposed_recipe_id else [])
        proposed_recipe = proposed[0] if proposed else None
        grocery = WeeklyGroceryEstimateResponse.model_validate(event.after_grocery)
        if plan.pricing_mode == "live" and event.event_type != "LOCK_MEAL":
            grocery = self.grocery_aggregator.refresh(grocery)
            before = self._current_grocery(plan)
            event.after_grocery = grocery.model_dump(mode="json")
            event.grocery_delta = self._grocery_delta(before, grocery)
            event.purchase_total_delta_sgd = round(grocery.purchase_total_sgd - before.purchase_total_sgd, 2)
            event.after_warnings = list(
                dict.fromkeys(
                    [
                        *(
                            warning
                            for warning in event.after_warnings
                            if not warning.startswith("The revised grocery total")
                        ),
                        *grocery.warnings,
                    ]
                )
            )
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

    def dishes_using(self, *, plan_id: int, entry_id: int, ingredients: list[str]) -> dict[str, list[str]]:
        """For each of `ingredients`, the titles of the week's other dishes still eaten that use it, as cooked
        for this household: why skipping `entry_id` leaves its packages on the list."""
        used: dict[str, list[str]] = {name: [] for name in ingredients}
        plan = self.repository.get(plan_id) if ingredients else None
        if plan is None:
            return used
        constraints = WeeklyMealPlanRequest.model_validate(plan.constraints)
        for item in plan.entries:
            if item.id == entry_id or item.status == "skipped":
                continue
            names = {line.ingredient.normalized_name for line in alternatives.lines(item.recipe, constraints)}
            for name in names & used.keys():
                if item.recipe.title not in used[name]:
                    used[name].append(item.recipe.title)
        return used

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
            pool_constraints(constraints), deduct_pantry_from_cost=False, recipes=recipes, priced_release_only=True
        )
        candidates = self._replacements(
            plan, entry, constraints, result.recommendations, recipes_by_id, unavailable=request.unavailable_ingredient
        )
        if not candidates:
            raise MealPlanReplanValidationError(
                f"No dish other than {shown_title(entry.recipe.title)} satisfies the current hard constraints."
            )

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
            self.request_similarity.scores(
                request.reason,
                [recipes_by_id[c.recipe.id] for c in candidates],
                excluded_title=entry.recipe.title,
            )
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

        ranked = sorted(candidates, key=score, reverse=True)
        # What was asked for leads: the budget chooses among the dishes most like it, never one unlike it.
        # ponytail: the ten most alike; a held-out swap set with budgets would tune it.
        alike = [candidate for candidate in ranked if asked.get(candidate.recipe.id, 0.0) > 0][:ASKED_ALIKE]
        if alike:
            ranked = alike
        else:
            # Nothing described: a dish the week does not serve yet comes first, and one it does only when no other
            # fits the budget, as the planner fills a week (ADR-0044).
            served = {
                dish_family(item.recipe.title)
                for item in plan.entries
                if item.id != entry.id and item.status != "skipped"
            }
            ranked.sort(key=lambda candidate: dish_family(candidate.recipe.title) in served)
        return self._fitting(plan, constraints, recipes_by_id, {}, entry, ranked)[0]

    def _replacements(
        self,
        plan: MealPlan,
        entry: MealPlanEntry,
        constraints,
        recommendations,
        recipes_by_id,
        *,
        unavailable=None,
        avoid=(),
    ) -> list[RecipeRecommendationResponse]:
        """The dishes that may take `entry`'s place, in the order given: another dish (never this one again nor
        one its meal already has, nor a dish family in `avoid`), without `unavailable`, in the same role with
        the meal still holding, and a dish for that meal whenever one is."""
        # The catalog can hold one dish several times ("Singapore Noodles" is eleven recipes).
        meal_dishes = (
            {
                dish_family(item.recipe.title)
                for item in plan.entries
                if item.day_index == entry.day_index and item.meal_type == entry.meal_type and item.status != "skipped"
            }
            | {dish_family(entry.recipe.title)}
            | set(avoid)
        )
        candidates = [
            item
            for item in recommendations
            if item.recipe.id != entry.recipe_id and dish_family(item.recipe.title) not in meal_dishes
        ]
        household = constraints.household
        if household is not None and household.missing_equipment:
            # The kitchen's equipment holds for a swap as for the planner (section 4.3).
            candidates = [
                item
                for item in candidates
                if equipment_met(getattr(recipes_by_id[item.recipe.id], "equipment", None), household.missing_equipment)
            ]
        if unavailable:
            candidates = [
                item
                for item in candidates
                if unavailable
                not in {
                    ingredient.ingredient.normalized_name
                    for ingredient in alternatives.lines(recipes_by_id[item.recipe.id], constraints)
                }
            ]
        if self._slot_members(constraints, entry):
            # Every meal, composed or not: a swap may not leave a member at the table with nothing to eat
            # (ADR-0071 section 1). `_meal_still_holds` only runs for a dish of a composed meal, so a one-dish
            # dinner would otherwise be swapped with no coverage check at all, while the planner refuses the
            # same meal. Without members this is identity, so a request with no household block is untouched.
            candidates = [
                item
                for item in candidates
                if self._coverage_after_swap(constraints, entry, recipes_by_id[item.recipe.id], plan)
            ]
        role = self._role(constraints, entry)
        if role is not None:
            # One dish of a composed meal: it fills the same role, and the meal must still hold
            # as a meal with the dishes that stay (ADR-0036; the owner chose to swap one dish).
            candidates = [
                item
                for item in candidates
                if catalog_role_admits(role, recipes_by_id[item.recipe.id])
                and self._meal_still_holds(plan, entry, recipes_by_id[item.recipe.id], constraints)
            ]
        # A dinner takes a dinner dish whenever one fits, as the planner fills a slot (ADR-0044, every meal since
        # ADR-0046): the 2026-10-04 walkthrough swapped in "Fried Rice In A Mug" (a lunch or snack) for a dinner.
        fitting = [item for item in candidates if entry.meal_type in meal_affinity(recipes_by_id[item.recipe.id])]
        return fitting or candidates

    def _week_grocery(self, plan: MealPlan, constraints, recipes_by_id, swaps: dict[int, int]):
        """The week's shopping with `swaps` (entry id -> recipe id) made."""
        eaten = [item for item in plan.entries if item.status != "skipped"]
        return self.grocery_aggregator.estimate(
            [recipes_by_id[swaps.get(item.id, item.recipe_id)] for item in eaten],
            constraints,
            shares=[grocery_share(item, plan.household_size) for item in eaten],
            by_weight=by_weight(self._current_grocery(plan)),
            trips=entry_trips(plan, eaten),
        )

    def _fitting(self, plan, constraints, recipes_by_id, swaps, entry, ranked, misfits=None) -> tuple:
        """The first of `ranked` for `entry` that keeps the week within its budget, or no further over it than it
        is, with `swaps` also made, and None; else the one that takes it over least, and by how much. Each one
        that does not fit is added to `misfits`.

        Whole packages decide, given what the rest of the week buys: a dish sharing the week's cabbage costs
        less than its own estimate says (the walkthrough's swaps took the week S$9 to S$17 over its budget).
        """
        budget = constraints.weekly_budget_sgd
        if budget is None:
            return ranked[0], None
        ceiling = round(max(budget, float(plan.purchase_total_sgd)) * 100)
        drift = self._drift_cents(plan, constraints, recipes_by_id)
        least = None
        for candidate in ranked:
            swapped = {**swaps, entry.id: candidate.recipe.id}
            grocery = self._week_grocery(plan, constraints, recipes_by_id, swapped)
            cents = drift + round(grocery.purchase_total_sgd * 100)
            if cents <= ceiling:
                return candidate, None
            if misfits is not None:
                misfits.add(candidate.recipe.id)
            if least is None or cents < least[1]:
                least = (candidate, cents)
        return least[0], (least[1] - ceiling) / 100

    def _drift_cents(self, plan: MealPlan, constraints, recipes_by_id) -> int:
        """How far the saved week's total is from the same week at snapshot prices, in cents: 0 for a fixture week.

        A live week's saved total is its basket checked at FairPrice (ADR-0058), but a change is chosen and
        previewed at snapshot prices (ADR-0060). Compared with the saved total or its budget as they are, a swap
        that fit at snapshot prices took the 2026-10-09 rehearsal's week from S$97.26 to S$100.16 once its basket
        was checked again, and its preview never said so. A change moves the saved total by its snapshot
        difference instead.
        """
        if plan.pricing_mode != "live":
            return 0
        snapshot = self._week_grocery(plan, constraints, recipes_by_id, {}).purchase_total_sgd
        return round(float(plan.purchase_total_sgd) * 100) - round(snapshot * 100)

    @staticmethod
    def _as_saved(plan: MealPlan, grocery: WeeklyGroceryEstimateResponse, drift: int) -> WeeklyGroceryEstimateResponse:
        """A snapshot-priced week after a change, totalled as the saved week is (`_drift_cents`): what its preview
        says the week comes to and how far over its budget. Its lines stay snapshot-priced; a live week's confirm
        checks them again and totals them (`WeeklyGroceryAggregator.refresh`)."""
        if not drift:
            return grocery
        cents = round(grocery.purchase_total_sgd * 100) + drift
        budget = grocery.weekly_budget_sgd
        within = grocery.within_weekly_budget
        if budget is not None:
            within = False if cents > round(budget * 100) else True if grocery.complete else None
        return grocery.model_copy(update={"purchase_total_sgd": cents / 100, "within_weekly_budget": within})

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
        """A replacement keeps its meal's distinct dishes, one-cook time, per-meal sodium ceiling and daily limits."""
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
        # The meal's own limit: a cooking-time rule for its weekday and meal, else the household's (layer 08).
        limit = slot_time_limit(
            constraints.household, constraints.max_cooking_time_minutes, entry.planned_date, entry.meal_type
        )
        roles = MealPlanReplanningService._meal_roles(constraints, entry)
        policy = STRUCTURED_TIME if structured(roles) else PlanningCompositionPolicy()
        if limit is not None and meal_minutes(dishes, policy) > limit:
            return False
        at_table = bool(MealPlanReplanningService._slot_members(constraints, entry))
        if structured(roles) and not MealPlanReplanningService._real_meal_holds(
            entry, candidate, others, roles, at_table
        ):
            return False
        # The filling core and the vegetable dish are a lunch-and-dinner rule (`meal_composition.real_meal_issues`
        # returns before them for any other meal). A structured breakfast holds no protein main, staple or
        # one-bowl dish, so applying them there refused every breakfast swap; `_coverage_after_swap` holds it to
        # the weakest form instead, which is the one the planner uses for it.
        if MealPlanReplanningService._fully_covered(roles, entry) and not MealPlanReplanningService._coverage_holds(
            constraints, entry, candidate, others
        ):
            return False
        if rules_on(constraints) and MealPlanReplanningService._perishable_late(plan, entry, candidate):
            return False
        ceiling = constraints.max_sodium_mg_per_meal
        if ceiling is not None and candidate.nutrition is not None:
            sodium = sum(float(item.sodium_mg) for item in others)
            sodium += float(candidate.nutrition.sodium_mg) * float(entry.portion_share)
            if sodium > ceiling + 1e-6:
                return False
        # A daily limit the household switched on (layer 08) holds over the day's dishes, per person.
        meals = list(week_shape(plan.constraints).meals)
        for target in limit_targets(constraints.household, meals) if candidate.nutrition is not None else []:
            day = sum(
                float(getattr(item, target.metric))
                for item in plan.entries
                if item.day_index == entry.day_index and item.id != entry.id and item.status != "skipped"
            )
            day += float(getattr(candidate.nutrition, target.metric)) * float(entry.portion_share)
            if day > target.upper + 1e-6:
                return False
        return True

    @staticmethod
    def _slot_members(constraints: WeeklyMealPlanRequest, entry: MealPlanEntry) -> list:
        """The members home for the swapped dish's meal, with each one's own limits (ADR-0071 section 1)."""
        return slot_members(
            constraints.household,
            entry.planned_date,
            entry.meal_type,
            meal_structure.energy_floor_share(entry.meal_type),
        )

    @staticmethod
    def _swap_servings(constraints: WeeklyMealPlanRequest, entry: MealPlanEntry, candidate: Recipe) -> Fraction | None:
        """The servings the new dish is cooked for: the members home for that meal who can eat it, at the
        replaced dish's share of the meal (ADR-0071 section 1).

        Without members, the replaced dish's own servings, as before: a swap changed the dish, not the table.
        """
        kept = Fraction(str(entry.servings)) if entry.servings is not None else None
        members = MealPlanReplanningService._slot_members(constraints, entry)
        cooked = alternatives.lines(candidate, constraints)
        able = [member for member in members if catalog_can_eat(member, candidate, cooked)]
        if not able:
            return kept
        base = sum((Fraction(str(member.servings)) for member in able), Fraction(0))
        return base * Fraction(str(entry.portion_share))

    @staticmethod
    def _coverage_holds(
        constraints: WeeklyMealPlanRequest, entry: MealPlanEntry, candidate: Recipe, others: list[MealPlanEntry]
    ) -> bool:
        """Whether every member home for the meal is still covered after the swap (ADR-0071 section 1)."""
        members = MealPlanReplanningService._slot_members(constraints, entry)
        if not members:
            return True

        def dish(role_id: str, recipe: Recipe, share) -> CoverageDish:
            return CoverageDish(
                role_id=role_id or "main",
                protein_main=meal_role_of(recipe) == "protein_main",
                carries_staple=fills_staple(recipe),
                calories_kcal=float(recipe.nutrition.calories_kcal) if recipe.nutrition is not None else 0.0,
                share=float(share),
                eaten_by=frozenset(
                    m.name for m in members if catalog_can_eat(m, recipe, alternatives.lines(recipe, constraints))
                ),
            )

        dishes = [dish(item.role_id, item.recipe, item.portion_share) for item in others]
        dishes.append(dish(entry.role_id, candidate, entry.portion_share))
        return not coverage_failures(members, dishes)

    @staticmethod
    def _fully_covered(roles, entry: MealPlanEntry) -> bool:
        """Whether this meal is one the full coverage rules can judge: a structured lunch or dinner.

        The same line `meal_composition.real_meal_issues` draws, so a swap is held to exactly what the planner
        held the meal to when it made it.
        """
        return structured(roles) and entry.meal_type in ("lunch", "dinner")

    @staticmethod
    def _coverage_after_swap(
        constraints: WeeklyMealPlanRequest, entry: MealPlanEntry, candidate: Recipe, plan: MealPlan
    ) -> bool:
        """Whether every member home for the meal still has a dish to eat once `candidate` replaces the entry.

        A structured lunch or dinner is judged by the full rules in `_meal_still_holds`; this is the weakest
        form (`member_coverage.member_has_a_dish`), which holds everywhere, so a breakfast, a one-dish dinner or
        a meal of course roles cannot leave a member with an empty plate (ADR-0071 section 1).
        """
        members = MealPlanReplanningService._slot_members(constraints, entry)
        if not members:
            return True
        others = [
            item
            for item in plan.entries
            if item.day_index == entry.day_index
            and item.meal_type == entry.meal_type
            and item.id != entry.id
            and item.status != "skipped"
        ]
        served = [item.recipe for item in others] + [candidate]
        cooked = {recipe.id: alternatives.lines(recipe, constraints) for recipe in served}
        return all(any(catalog_can_eat(member, recipe, cooked[recipe.id]) for recipe in served) for member in members)

    @staticmethod
    def _meal_roles(constraints: WeeklyMealPlanRequest, entry: MealPlanEntry) -> list:
        roles = (
            constraints.plan_shape.meals.get(entry.meal_type)
            if constraints.plan_shape is not None
            else constraints.meal_composition
        )
        return list(roles or [])

    @staticmethod
    def _real_meal_holds(
        entry: MealPlanEntry, candidate: Recipe, others: list[MealPlanEntry], roles, members_present: bool = False
    ) -> bool:
        """A swap in a structured meal keeps it a real meal (ADR-0070): a core dish keeps whether it carries the
        staple, a protein main shares no protein source with the meal's other mains, and a lunch or dinner keeps
        its energy floor per serving. Tags hold by the role (`catalog_role_admits`)."""
        core = core_role(roles)
        if core is not None and entry.role_id == core.role_id and fills_staple(candidate) != fills_staple(entry.recipe):
            return False
        mains = [item.recipe for item in others if role_base(item.role_id) == "main"]
        if role_base(entry.role_id) == "main":
            mains.append(candidate)
        taken = set()
        for main in mains:
            sources = getattr(main, "protein_sources", None)
            if sources is None or taken.intersection(sources):
                return False
            taken.update(sources)
        # With members at the table each one's own floor is checked instead (`_coverage_holds`).
        share = None if members_present else meal_structure.energy_floor_share(entry.meal_type)
        if share and candidate.nutrition is not None:
            energy = sum(float(item.calories_kcal) for item in others)
            energy += float(candidate.nutrition.calories_kcal) * float(entry.portion_share)
            if energy < share * hpb()["adult_reference"]["energy_kcal"] - 1e-6:
                return False
        return True

    @staticmethod
    def _perishable_late(plan: MealPlan, entry: MealPlanEntry, candidate: Recipe) -> bool:
        """A perishable dish later than its days after its shopping trip (ADR-0072)."""
        since_trip = (entry.day_index - 1) % meal_structure.trip_days() + 1
        if since_trip <= meal_structure.perishable_days():
            return False
        return any(line.ingredient.perishable is True for line in getattr(candidate, "recipe_ingredients", None) or [])

    @staticmethod
    def _recipes_after_event(
        *,
        plan: MealPlan,
        target: MealPlanEntry,
        event_type: str,
        proposed_recipe_id: int | None,
        recipes_by_id: dict[int, Recipe],
        swapped_servings: Fraction | None = None,
    ) -> list[tuple[Recipe, float, MealPlanEntry]]:
        """Each dish still eaten after the event, with its portion share and its entry.

        `swapped_servings` are the new dish's own servings, which may differ from the replaced dish's when the
        members who can eat it differ (ADR-0071 section 1)."""
        recipes: list[tuple[Recipe, float, MealPlanEntry]] = []
        for entry in plan.entries:
            if entry.status == "skipped" or (entry.id == target.id and event_type == "CANCEL_MEAL"):
                continue
            recipe_id = (
                proposed_recipe_id if entry.id == target.id and proposed_recipe_id is not None else entry.recipe_id
            )
            recipe = recipes_by_id.get(recipe_id)
            if recipe is None:
                raise MealPlanReplanNotFoundError("A recipe used by this plan no longer exists")
            share = grocery_share(entry, plan.household_size)
            if entry.id == target.id and swapped_servings is not None and plan.household_size:
                share = float(swapped_servings) / plan.household_size
            recipes.append((recipe, share, entry))
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
        household_size: int | None = None,
        servings: Fraction | None = None,
    ) -> dict:
        snapshot = MealPlanReplanningService._entry_snapshot(entry)
        if request.event_type == "LOCK_MEAL":
            snapshot["is_locked"] = True
        elif request.event_type == "CANCEL_MEAL":
            snapshot["status"] = "skipped"
        elif recommendation is not None:
            estimate = recommendation.grocery_estimate
            share = float(entry.portion_share)
            # Its cost is for the servings it is cooked for: the estimate is for the household size.
            cost_share = grocery_share(entry, household_size) if household_size else share
            if servings is not None and household_size:
                cost_share = float(servings) / household_size
                snapshot["servings"] = round(float(servings), 3)
            snapshot.update(
                {
                    "recipe_id": recommendation.recipe.id,
                    "recipe_slug": recommendation.recipe.slug,
                    "recipe_title": recommendation.recipe.title,
                    "recommendation_score": recommendation.total_score,
                    # The new dish is eaten at the replaced dish's share of the meal.
                    "consumed_cost_sgd": _at_share(estimate.consumed_total_sgd, cost_share) if estimate else 0,
                    "purchase_cost_sgd": _at_share(estimate.purchase_total_sgd, cost_share) if estimate else 0,
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
        # One line per ingredient and unit, like the list itself: whole eggs and grams of egg.
        before_by_line = {(item.ingredient_name, item.unit or ""): item for item in before.items}
        after_by_line = {(item.ingredient_name, item.unit or ""): item for item in after.items}
        delta: list[dict] = []
        for name, unit in sorted(before_by_line.keys() | after_by_line.keys()):
            old = before_by_line.get((name, unit))
            new = after_by_line.get((name, unit))
            if old is not None and new is not None:
                # The saved list keeps three decimals (Numeric(12, 3)): a recomputed 0.9199999999999999 is the
                # saved 0.92, not a change.
                unchanged = (
                    _same_quantity(old.required_quantity, new.required_quantity)
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
        after, delta = event.after_grocery, float(event.purchase_total_delta_sgd)
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
            meal_entries=[
                MealPlanEntrySnapshot.model_validate(item)
                for item in (event.before_entry or {}).get("meal_entries", [])
            ],
            shape_change=MealPlanShapeChange.model_validate(event.shape_change) if event.shape_change else None,
            nutrition_delta=MealPlanNutritionDelta.model_validate(event.nutrition_delta),
            grocery_delta=[MealPlanGroceryDeltaLine.model_validate(item) for item in event.grocery_delta],
            purchase_total_delta_sgd=delta,
            # Only a change that costs more puts the week over: a keep or a skip on a week already over
            # its budget does not.
            over_budget_sgd=(
                round(after["purchase_total_sgd"] - after["weekly_budget_sgd"], 2)
                if after.get("within_weekly_budget") is False and delta > 0
                else None
            ),
            created_at=event.created_at,
            applied_at=event.applied_at,
        )
