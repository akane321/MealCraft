from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.meal_plan import MealPlan
from app.models.platform import OperationRun
from app.models.recipe import Recipe
from app.planning.conflict_explanation import explain_infeasibility, product_explanation
from app.planning.meal_beam import EMPTY_OPTIONAL_ROLE_LOSS
from app.planning.nutrition_scope import nutrition_scope_notes
from app.planning.product_path import ProductPlanningEngine, ProductPlanningError, meals_of_the_day
from app.planning.week_floor import WeekFloor, week_floor
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelector
from app.repositories.meal_plan import MealPlanRepository, ScheduledDish
from app.repositories.recipe import RecipeRepository
from app.schemas.meal_plan import (
    MealPlanEntryStatus,
    MealPlanStatusCounts,
    NutritionDashboardDayResponse,
    WeeklyGroceryEstimateResponse,
    WeeklyMealPlanCollectionResponse,
    WeeklyMealPlanListItem,
    WeeklyMealPlanRequest,
    WeeklyMealPlanResponse,
    WeeklyNutritionDashboardResponse,
    WeeklyNutritionSummaryResponse,
    WeeklyPlanDayResponse,
    week_shape,
)
from app.schemas.product import GroceryLineEstimate, PriceEvidence, ProductResponse
from app.schemas.recipe import RecipeListItemResponse, RecipeNutritionResponse
from app.services.recommendation import RecipeRecommendationService


class WeeklyMealPlanService:
    def __init__(
        self,
        *,
        repository: MealPlanRepository,
        recipe_repository: RecipeRepository,
        recommendation_service: RecipeRecommendationService,
        grocery_aggregator: WeeklyGroceryAggregator,
        selector: WeeklyPlanSelector | None = None,
        planning_engine: ProductPlanningEngine | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        self.repository = repository
        self.recipe_repository = recipe_repository
        self.recommendation_service = recommendation_service
        self.grocery_aggregator = grocery_aggregator
        self.selector = selector or WeeklyPlanSelector()
        self.planning_engine = planning_engine or ProductPlanningEngine()
        self.actor_user_id = actor_user_id
        self._checked: dict[str, tuple] = {}

    def generate(
        self,
        constraints: WeeklyMealPlanRequest,
        *,
        household_profile_id: int | None = None,
        household_profile_version: int | None = None,
        replaces_plan_id: int | None = None,
        searched: tuple | None = None,
    ) -> WeeklyMealPlanResponse:
        """Plan a week and save it; `searched` is a week `search` already found for these constraints."""
        started_at = datetime.now(UTC)
        try:
            recommendation_result, result = searched or self._search(
                constraints, self._candidates(constraints), profile_version=household_profile_version
            )
        except ProductPlanningError as error:
            error.trace["profile_id"] = household_profile_id
            self.repository.session.add(self._operation_run(error.trace, started_at, error=str(error)))
            self.repository.session.commit()
            raise
        selected, grocery = result.selected, result.grocery
        result.trace["profile_id"] = household_profile_id

        warnings = self._deduplicate(
            recommendation_result.warnings + grocery.warnings + nutrition_scope_notes(constraints.nutrition_constraints)
        )
        eligible_count = len({item.recipe.id for item in recommendation_result.recommendations})
        if eligible_count == 1:
            warnings.append("Only one eligible recipe was available, so consecutive repetition could not be avoided.")
        if eligible_count < constraints.day_count:
            recipe_label = "recipe" if eligible_count == 1 else "recipes"
            warnings.append(
                f"The current eligible catalog contains {eligible_count} {recipe_label}; "
                "recipes are rotated across the seven days."
            )
        placements = result.placements or [(index, "dinner", "main", 1) for index in range(len(selected))]
        scheduled = [
            ScheduledDish(
                planned_date=constraints.start_date + timedelta(days=slot_index),
                day_index=slot_index + 1,
                meal_type=meal_type,
                role_id=role_id,
                portion_share=portion_share,
                recommendation=recommendation,
            )
            for (slot_index, meal_type, role_id, portion_share), recommendation in zip(
                placements, selected, strict=True
            )
        ]
        plan = self.repository.create(
            constraints=constraints,
            scheduled=scheduled,
            grocery=grocery,
            warnings=self._deduplicate(warnings),
            household_profile_id=household_profile_id,
            household_profile_version=household_profile_version,
            replaces_plan_id=replaces_plan_id,
            operation_run=self._operation_run(result.trace, started_at),
        )
        return self._to_response(plan)

    def _search(self, constraints: WeeklyMealPlanRequest, candidates, *, profile_version: int | None = None):
        """The week `generate` plans from these candidates (recipes, recommendations), nothing saved."""
        recipes, recommendation_result = candidates
        broadened = not recommendation_result.recommendations
        if broadened:
            # Broaden only the diagnostic candidate pool; the original request
            # still goes to the compiler and validator. Safety filters stay fixed.
            recommendation_result = self.recommendation_service.recommend(
                constraints.model_copy(update={"max_cooking_time_minutes": 240, "dietary_preferences": []}),
                deduct_pantry_from_cost=False,
                recipes=recipes,
                priced_release_only=True,
            )
        prior_trace = None
        for attempt in range(2):
            try:
                result = self.planning_engine.plan(
                    constraints,
                    recommendation_result.recommendations,
                    recipes,
                    selector=self.selector,
                    profile_version=profile_version,
                )
                if prior_trace is not None:
                    result.trace["prior_candidate_attempt"] = prior_trace
                return recommendation_result, result
            except ProductPlanningError as error:
                if error.status == "infeasible" and not broadened and attempt == 0:
                    # A time/diet-filtered pool cannot establish which of those
                    # constraints conflicts with budget. Retain original quotes
                    # and add diagnostic candidates, then establish evidence again.
                    previous = {r.recipe.id: r for r in recommendation_result.recommendations}
                    recommendation_result = self.recommendation_service.recommend(
                        constraints.model_copy(update={"max_cooking_time_minutes": 240, "dietary_preferences": []}),
                        deduct_pantry_from_cost=False,
                        recipes=recipes,
                        priced_release_only=True,
                    )
                    recommendation_result.recommendations = [
                        previous.get(r.recipe.id, r) for r in recommendation_result.recommendations
                    ]
                    prior_trace = error.trace
                    broadened = True
                    continue
                if prior_trace is not None:
                    error.trace["prior_candidate_attempt"] = prior_trace
                if error.problem is not None and error.status == "infeasible":
                    explanation = explain_infeasibility(
                        error.problem,
                        evidence=error.trace["evidence"],
                        per_meal_budget=constraints.budget_per_meal_sgd,
                    )
                    error.trace["explanation"] = explanation
                    message = product_explanation(explanation)
                    if message:
                        error.args = (message,)
                raise
        raise AssertionError("unreachable")

    def search(self, constraints: WeeklyMealPlanRequest) -> tuple:
        """The week `generate` would plan for these constraints, nothing saved; ProductPlanningError for none.

        `generate(constraints, searched=...)` saves it."""
        return self._search(constraints, self._checked_candidates(constraints))

    def check(self, constraints: WeeklyMealPlanRequest) -> ProductPlanningError | None:
        """What `generate` would answer for these constraints, nothing saved: None for a week, else its error."""
        try:
            self.search(constraints)
        except ProductPlanningError as error:
            return error
        return None

    def _candidates(self, constraints: WeeklyMealPlanRequest):
        """The recipes a week may use and the recommendations `generate` plans from first."""
        # Every course a planned meal's roles may take enters the pool (ADR-0046), not only dinner's.
        meals = meals_of_the_day(constraints)
        courses = sorted({c for _, roles in meals for role in roles for c in role.courses}) if meals else None
        recipes = self.recipe_repository.list_for_planning(courses=courses)
        result = self.recommendation_service.recommend(
            constraints,
            deduct_pantry_from_cost=False,
            recipes=recipes,
            priced_release_only=True,
        )
        avoid = set(constraints.avoid_recipe_ids)
        if avoid:
            # Each course drops the avoided dishes only while a week's worth of its others remain.
            course = {recipe.id: getattr(recipe, "course", None) or "main" for recipe in recipes}
            kept = Counter(course.get(r.recipe.id) for r in result.recommendations if r.recipe.id not in avoid)
            result.recommendations = [
                r
                for r in result.recommendations
                if r.recipe.id not in avoid or kept[course.get(r.recipe.id)] < constraints.day_count
            ]
        return recipes, result

    def _checked_candidates(self, constraints: WeeklyMealPlanRequest):
        """`_candidates`, worked out once per request for the checks a chat turn makes before it answers.

        The weekly budget is not a recommendation input, so the floor and the cheapest week share one pass.
        """
        key = constraints.model_dump_json(exclude={"weekly_budget_sgd"})
        if key not in self._checked:
            self._checked[key] = self._candidates(constraints)
        return self._checked[key]

    def week_floor(self, constraints: WeeklyMealPlanRequest) -> WeekFloor:
        """What any week `generate` could plan for these constraints costs at least, without a search."""
        recipes, candidates = self._checked_candidates(constraints)
        return week_floor(constraints, candidates.recommendations, recipes)

    def cheapest_week(self, constraints: WeeklyMealPlanRequest) -> float:
        """What the cheapest week the planner's cost-led search finds costs at the checkout, nothing saved.

        Every limit but the weekly budget holds. `generate` tries the same search's weeks last under a
        budget, so any budget of at least this plans (with the same prices). Raises ProductPlanningError
        when the search finds no week at all.
        """
        unbudgeted = constraints.model_copy(update={"weekly_budget_sgd": None})
        recipes, candidates = self._checked_candidates(unbudgeted)
        result = self.planning_engine.plan(
            unbudgeted, candidates.recommendations, recipes, selector=self.selector, cheapest=True
        )
        return result.grocery.purchase_total_sgd

    def plan_dishes(
        self,
        constraints: WeeklyMealPlanRequest,
        *,
        first_day: int,
        day_count: int,
        rest: list[tuple[Recipe, float]],
        keep: dict[tuple[int, str], dict[str, int]] | None = None,
        over_budget: float | None = None,
        by_weight: Iterable[str] = (),
    ) -> list[ScheduledDish]:
        """Dishes for `day_count` days from day `first_day` of a saved week, nothing saved (ADR-0046 section 2).

        `constraints` carries the shape to plan and the budget left. `rest` is the rest of the week, each dish
        with its portion share: its dishes are avoided while enough others remain, and in every attempt their
        uses there count towards the household's cap on uses. `keep` ((day index, meal) -> {role id: recipe
        id}) holds each meal's present dishes in their roles while a new one is added. `over_budget` plans the
        dishes over the budget when none fit it (none can when it is 0 or less), as cheaply as the planner finds,
        weighing costs against this amount (see `over_budget_pick` and `charge` below). `by_weight` is what the
        week's list buys by weight, so `charge` prices the week as its list will be.
        """
        start = constraints.start_date + timedelta(days=first_day - 1)
        # day_count is fixed at 7 for a whole week; a part of one is planned the same way.
        partial = constraints.model_copy(update={"start_date": start, "day_count": day_count})
        meals = meals_of_the_day(partial)
        courses = sorted({c for _, roles in meals for role in roles for c in role.courses}) if meals else None
        recipes = self.recipe_repository.list_for_planning(courses=courses)
        recommendations = self.recommendation_service.recommend(
            partial, deduct_pantry_from_cost=False, recipes=recipes, priced_release_only=True
        ).recommendations
        slugs = {recipe.id: recipe.slug for recipe in recipes}
        keep_ids = {recipe_id for roles in (keep or {}).values() for recipe_id in roles.values()}
        # A kept dish the planner no longer offers cannot stay: the meal is planned from every candidate.
        kept = {
            (day - first_day, meal): {role: slugs[recipe_id] for role, recipe_id in roles.items()}
            for (day, meal), roles in (keep or {}).items()
            if keep_ids <= slugs.keys()
        }
        used = Counter(recipe.id for recipe, _ in rest)
        fresh = [item for item in recommendations if item.recipe.id in keep_ids or item.recipe.id not in used]
        budget = partial.weekly_budget_sgd
        within = budget is None or budget > 0 or over_budget is None
        over = partial.model_copy(update={"weekly_budget_sgd": over_budget}) if over_budget is not None else None
        pools = [fresh] + ([recommendations] if len(fresh) < len(recommendations) else [])
        # Each step in turn; the first that finds a plan gives it. Within the budget, dishes the week does not
        # have yet, then any (too few are left). Over it, both at once: a dish the week has may cost less than
        # a new one, and `charge` weighs the two. When the kept dishes fit nothing at all, the meal is planned
        # from every candidate rather than fail.
        steps = []
        for locked, choices in ((kept, pools), (None, [recommendations])) if kept else ((None, pools),):
            steps += [[(pool, locked, partial, True)] for pool in choices] if within else []
            steps += [[(pool, locked, over, False) for pool in pools]] if over is not None else []
        by_id = {recipe.id: recipe for recipe in recipes}

        def charge(planned) -> float:
            """A plan over the budget as the week pays for it: the checkout with the rest of the week (a package
            both use is bought once), and a repeat of any dish in the week at one meal's share of `over_budget`
            and an empty optional dish at twice that, as `over_budget_pick` charges them among the meals it plans.
            Within those meals alone, a dinner's salad served again at lunch was no repeat (the 2026-10-02
            review: every lunch of mdw-dev-013 was one of its dinners)."""
            week = [recipe for recipe, _ in rest] + [by_id[item.recipe.id] for item in planned.selected]
            shares = [share for _, share in rest] + [float(place[3]) for place in planned.placements]
            total = self.grocery_aggregator.estimate(
                week, partial, shares=shares, by_weight=by_weight
            ).purchase_total_sgd
            repeats = len(week) - len({recipe.id for recipe in week})
            empty = day_count * sum(len(roles) for _, roles in meals) - len(planned.selected)
            return total + over_budget / (day_count * len(meals)) * (repeats + EMPTY_OPTIONAL_ROLE_LOSS * empty)

        for step in steps:
            found = []
            for pool, locked, request, hard in step:
                try:
                    found.append(
                        self.planning_engine.plan(
                            request,
                            pool,
                            recipes,
                            selector=self.selector,
                            cheapest_last=False,
                            budget_is_hard=hard,
                            locked=locked,
                            used=Counter(recipe.slug for recipe, _ in rest),
                        )
                    )
                except ProductPlanningError as error:
                    failure = error
            if found:
                result = min(found, key=charge) if len(found) > 1 else found[0]
                break
        else:
            raise failure
        placements = result.placements or [(index, "dinner", "main", 1) for index in range(len(result.selected))]
        return [
            ScheduledDish(
                planned_date=start + timedelta(days=slot_index),
                day_index=first_day + slot_index,
                meal_type=meal_type,
                role_id=role_id,
                portion_share=share,
                recommendation=recommendation,
            )
            for (slot_index, meal_type, role_id, share), recommendation in zip(placements, result.selected, strict=True)
        ]

    def _operation_run(self, trace: dict, started_at: datetime, *, error: str | None = None) -> OperationRun:
        return OperationRun(
            trace_id=f"planning-{uuid4().hex}",
            run_type="planning",
            status="failed" if error else "succeeded",
            triggered_by_user_id=self.actor_user_id,
            household_id=self.repository.household_id,
            input_digest=trace["input_digest"],
            catalog_version=trace.get("catalog_version"),
            product_snapshot_version=trace.get("product_snapshot_version"),
            policy_version=trace["policy_version"],
            algorithm_version=f"{trace['algorithm']}-product-v1",
            provider_mode=",".join(trace.get("observed_sources", [])) or None,
            artifact_references=[{"kind": "planning_trace", "data": trace}],
            warnings=[],
            error_code=trace["status"] if error else None,
            error_detail=error,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    def get(self, plan_id: int) -> WeeklyMealPlanResponse | None:
        plan = self.repository.get(plan_id)
        return self._to_response(plan) if plan is not None else None

    def list_recent(self, *, limit: int) -> WeeklyMealPlanCollectionResponse:
        return WeeklyMealPlanCollectionResponse(
            items=[
                WeeklyMealPlanListItem(
                    id=plan.id,
                    revision=plan.revision,
                    household_profile_id=plan.household_profile_id,
                    household_profile_version=plan.household_profile_version,
                    replaces_plan_id=plan.replaces_plan_id,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                    household_size=plan.household_size,
                    purchase_total_sgd=float(plan.purchase_total_sgd),
                    consumed_total_sgd=(
                        float(plan.consumed_total_sgd) if plan.consumed_total_sgd is not None else None
                    ),
                    within_weekly_budget=plan.within_weekly_budget,
                    created_at=plan.created_at,
                )
                for plan in self.repository.list_recent(limit=limit)
            ]
        )

    def update_entry_status(
        self,
        *,
        plan_id: int,
        entry_id: int,
        status: MealPlanEntryStatus,
    ) -> WeeklyMealPlanResponse | None:
        plan = self.repository.update_entry_status(
            plan_id=plan_id,
            entry_id=entry_id,
            status=status,
        )
        return self._to_response(plan) if plan is not None else None

    def update_meal_status(
        self,
        *,
        plan_id: int,
        day_index: int,
        meal_type: str,
        status: MealPlanEntryStatus,
    ) -> WeeklyMealPlanResponse | None:
        plan = self.repository.update_meal_status(
            plan_id=plan_id, day_index=day_index, meal_type=meal_type, status=status
        )
        return self._to_response(plan) if plan is not None else None

    def dashboard(self, plan_id: int) -> WeeklyNutritionDashboardResponse | None:
        plan = self.repository.get(plan_id)
        if plan is None:
            return None

        planned_totals = self._empty_nutrition_totals()
        completed_totals = self._empty_nutrition_totals()
        counts = {"planned": 0, "completed": 0, "skipped": 0}
        days: list[NutritionDashboardDayResponse] = []

        for entry in plan.entries:
            nutrition = self._entry_nutrition(entry)
            counts[entry.status] += 1
            for key in planned_totals:
                if entry.status != "skipped":
                    planned_totals[key] += getattr(nutrition, key)
                if entry.status == "completed":
                    completed_totals[key] += getattr(nutrition, key)
            days.append(
                NutritionDashboardDayResponse(
                    entry_id=entry.id,
                    day_index=entry.day_index,
                    planned_date=entry.planned_date,
                    recipe=RecipeListItemResponse.model_validate(entry.recipe),
                    status=entry.status,
                    is_locked=entry.is_locked,
                    consumed_at=self._as_utc(entry.consumed_at),
                    nutrition_per_person=nutrition,
                    meal_type=entry.meal_type,
                    role_id=entry.role_id,
                    portion_share=float(entry.portion_share),
                )
            )

        constraints = plan.constraints if isinstance(plan.constraints, dict) else {}
        completed_count = counts["completed"]
        return WeeklyNutritionDashboardResponse(
            plan_id=plan.id,
            revision=plan.revision,
            start_date=plan.start_date,
            end_date=plan.end_date,
            household_size=plan.household_size,
            completion_rate=round(completed_count / max(len(plan.entries), 1) * 100, 1),
            status_counts=MealPlanStatusCounts(**counts),
            nutrition_targets=constraints.get("nutrition_targets", {}),
            planned_nutrition_per_person=self._nutrition_summary(planned_totals),
            completed_nutrition_per_person=self._nutrition_summary(completed_totals),
            days=days,
        )

    @staticmethod
    def _to_response(plan: MealPlan) -> WeeklyMealPlanResponse:
        days: list[WeeklyPlanDayResponse] = []
        totals = {
            "calories_kcal": 0.0,
            "protein_g": 0.0,
            "carbohydrate_g": 0.0,
            "fat_g": 0.0,
            "sodium_mg": 0.0,
            "sugar_g": 0.0,
        }
        for entry in plan.entries:
            nutrition = WeeklyMealPlanService._entry_nutrition(entry)
            if entry.status != "skipped":
                for key in totals:
                    totals[key] += getattr(nutrition, key)
            days.append(
                WeeklyPlanDayResponse(
                    entry_id=entry.id,
                    day_index=entry.day_index,
                    planned_date=entry.planned_date,
                    meal_type=entry.meal_type,
                    role_id=entry.role_id,
                    portion_share=float(entry.portion_share),
                    recipe=RecipeListItemResponse.model_validate(entry.recipe),
                    recommendation_score=float(entry.recommendation_score),
                    nutrition_per_person=nutrition,
                    consumed_cost_sgd=float(entry.consumed_cost_sgd),
                    purchase_cost_sgd=float(entry.purchase_cost_sgd),
                    status=entry.status,
                    is_locked=entry.is_locked,
                    consumed_at=WeeklyMealPlanService._as_utc(entry.consumed_at),
                )
            )

        grocery_lines = [WeeklyMealPlanService._grocery_line(item) for item in plan.grocery_items]
        unmapped = sorted(
            line.ingredient_name
            for line in grocery_lines
            if line.product is None and line.remaining_quantity != 0 and line.consumed_cost_sgd is None
        )
        grocery = WeeklyGroceryEstimateResponse(
            pricing_mode=plan.pricing_mode,
            complete=not unmapped and all(line.consumed_cost_sgd is not None for line in grocery_lines),
            purchase_total_sgd=float(plan.purchase_total_sgd),
            consumed_total_sgd=(float(plan.consumed_total_sgd) if plan.consumed_total_sgd is not None else None),
            weekly_budget_sgd=(float(plan.weekly_budget_sgd) if plan.weekly_budget_sgd is not None else None),
            within_weekly_budget=plan.within_weekly_budget,
            items=grocery_lines,
            unmapped_ingredients=unmapped,
            warnings=plan.warnings,
        )
        return WeeklyMealPlanResponse(
            id=plan.id,
            revision=plan.revision,
            household_profile_id=plan.household_profile_id,
            household_profile_version=plan.household_profile_version,
            replaces_plan_id=plan.replaces_plan_id,
            start_date=plan.start_date,
            end_date=plan.end_date,
            day_count=plan.day_count,
            household_size=plan.household_size,
            days=days,
            nutrition_summary_per_person=WeeklyNutritionSummaryResponse(
                **{key: round(value, 2) for key, value in totals.items()}
            ),
            grocery_estimate=grocery,
            warnings=plan.warnings,
            created_at=plan.created_at,
            plan_shape=week_shape(plan.constraints),
        )

    @staticmethod
    def _grocery_line(item) -> GroceryLineEstimate:
        product = None
        if item.product_external_id is not None:
            product = ProductResponse(
                external_id=item.product_external_id,
                name=item.product_name,
                brand=item.product_brand,
                category=item.product_category,
                package_size=(float(item.product_package_size) if item.product_package_size is not None else None),
                package_unit=item.product_package_unit,
                price_sgd=float(item.product_price_sgd),
                product_url=item.product_url,
                image_url=item.product_image_url,
                in_stock=True,
                source=item.product_source,
                fetched_at=(
                    item.product_fetched_at.replace(tzinfo=UTC)
                    if item.product_fetched_at.tzinfo is None
                    else item.product_fetched_at
                ),
            )
        return GroceryLineEstimate(
            ingredient_name=item.ingredient_name,
            ingredient_display_name=item.ingredient_display_name,
            required_quantity=(float(item.required_quantity) if item.required_quantity is not None else None),
            unit=item.unit,
            pantry_deduction=float(item.pantry_deduction),
            remaining_quantity=(float(item.remaining_quantity) if item.remaining_quantity is not None else None),
            product=product,
            match_score=float(item.match_score) if item.match_score is not None else None,
            packages_required=item.packages_required,
            purchase_cost_sgd=float(item.purchase_cost_sgd),
            consumed_cost_sgd=(float(item.consumed_cost_sgd) if item.consumed_cost_sgd is not None else None),
            excess_quantity=(float(item.excess_quantity) if item.excess_quantity is not None else None),
            note=item.note,
            evidence=PriceEvidence.model_validate(item.price_evidence) if item.price_evidence else None,
        )

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _entry_nutrition(entry) -> RecipeNutritionResponse:
        return RecipeNutritionResponse(
            calories_kcal=float(entry.calories_kcal),
            protein_g=float(entry.protein_g),
            carbohydrate_g=float(entry.carbohydrate_g),
            fat_g=float(entry.fat_g),
            sodium_mg=float(entry.sodium_mg),
            sugar_g=float(entry.sugar_g),
        )

    @staticmethod
    def _empty_nutrition_totals() -> dict[str, float]:
        return {
            "calories_kcal": 0.0,
            "protein_g": 0.0,
            "carbohydrate_g": 0.0,
            "fat_g": 0.0,
            "sodium_mg": 0.0,
            "sugar_g": 0.0,
        }

    @staticmethod
    def _nutrition_summary(totals: dict[str, float]) -> WeeklyNutritionSummaryResponse:
        return WeeklyNutritionSummaryResponse(**{key: round(value, 2) for key, value in totals.items()})

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
