import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError

from app.core.code_version import code_commit
from app.core.config import get_settings
from app.data import meal_structure
from app.models.meal_plan import MealPlan
from app.models.platform import OperationRun
from app.models.recipe import Recipe
from app.planning import alternatives
from app.planning.conflict_explanation import explain_infeasibility, product_explanation
from app.planning.dish_reasons import cost_per_serving, dish_reasons
from app.planning.household_slots import limit_targets, slot_members, widest_time_limit
from app.planning.meal_beam import EMPTY_OPTIONAL_ROLE_LOSS
from app.planning.member_coverage import catalog_can_eat
from app.planning.nutrition_scope import nutrition_scope_notes
from app.planning.product_path import (
    ProductPlanningEngine,
    ProductPlanningError,
    meals_of_the_day,
    pool_courses,
    pool_for,
)
from app.planning.replan_pantry import remaining_stock
from app.planning.week_floor import WeekFloor, week_floor
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.planning.weekly_planner import WeeklyPlanSelector
from app.repositories.meal_plan import MealPlanRepository, ScheduledDish, replaced_by
from app.repositories.recipe import FOUND_WEEKS_KEPT, RecipeRepository, found_weeks
from app.repositories.recipe_feedback import RecipeFeedbackRepository, with_never_again
from app.schemas.fairprice_cart import cart_state
from app.schemas.meal_plan import (
    MEAL_ORDER,
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


def _meal_rank(meal_type: str) -> int:
    """Breakfast, lunch, dinner, then anything else (a snack)."""
    return MEAL_ORDER.index(meal_type) if meal_type in MEAL_ORDER else len(MEAL_ORDER)


def pool_constraints(constraints: WeeklyMealPlanRequest) -> WeeklyMealPlanRequest:
    """The request the recipe pool is recommended for: with cooking-time rules, the loosest limit any meal has,
    so each meal's own limit is held by the planner (layer 08); the request itself without them."""
    widest = widest_time_limit(constraints.household, constraints.max_cooking_time_minutes)
    if widest == constraints.max_cooking_time_minutes:
        return constraints
    return constraints.model_copy(update={"max_cooking_time_minutes": widest})


def _distinct(result) -> int:
    """How many different recipes a planned week serves."""
    return len({item.recipe.id for item in result.selected})


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
        live_feedback: bool = False,
    ) -> None:
        self.repository = repository
        self.recipe_repository = recipe_repository
        self.recommendation_service = recommendation_service
        self.grocery_aggregator = grocery_aggregator
        self.selector = selector or WeeklyPlanSelector()
        self.planning_engine = planning_engine or ProductPlanningEngine()
        self.actor_user_id = actor_user_id
        # Product requests plan without the household's "Never again" dishes, read live (ADR-0087). Evaluations
        # and the console's replays leave it off: they plan their stored requests as stored.
        self.live_feedback = live_feedback
        self._checked: dict[str, tuple] = {}

    def _live(self, constraints: WeeklyMealPlanRequest) -> WeeklyMealPlanRequest:
        if not self.live_feedback:
            return constraints
        return with_never_again(constraints, self.repository.session, self.repository.household_id)

    def generate(
        self,
        constraints: WeeklyMealPlanRequest,
        *,
        household_profile_id: int | None = None,
        household_profile_version: int | None = None,
        replaces_plan_id: int | None = None,
    ) -> WeeklyMealPlanResponse:
        """Plan a week and save it: the week `check` found for these constraints while it is kept, else a new one."""
        constraints = self._live(constraints)
        started_at = datetime.now(UTC)
        found = found_weeks.pop(self._found_key(constraints, household_profile_version), None)
        fresh = found is not None and time.monotonic() - found[0] < get_settings().planning_pool_cache_seconds
        searched = found[1] if fresh else None
        if searched is not None:
            # `check` searched this week before the reply and Plan only saves it: the run is timed as that search
            # and this save, not the 1 ms of the save alone (the console's planning time read 0 s on 2026-10-05).
            searched[1].trace["reused_checked_week"] = True
            started_at -= timedelta(seconds=searched[1].trace["search_seconds"])
        try:
            recommendation_result, result = searched or self._search(
                constraints, self._candidates(constraints), profile_version=household_profile_version
            )
        except ProductPlanningError as error:
            error.trace["profile_id"] = household_profile_id
            self._priced_as_asked(error.trace, constraints)
            self.repository.session.add(self._operation_run(error.trace, started_at, error=str(error)))
            self.repository.session.commit()
            raise
        selected, grocery = result.selected, result.grocery
        self._priced_as_asked(result.trace, constraints)
        if constraints.pricing_mode == "live":
            grocery = self.grocery_aggregator.refresh(grocery)
            # Only the saved list is checked at FairPrice (ADR-0058): what it came to, as the household sees it.
            result.trace["final_list"] = {
                "pricing_mode": grocery.pricing_mode,
                "purchase_total_sgd": grocery.purchase_total_sgd,
                "price_sources": sorted({line.evidence.source for line in grocery.items if line.evidence}),
            }
        result.trace["profile_id"] = household_profile_id

        recommendation_warnings = recommendation_result.warnings
        if constraints.pricing_mode == "live":
            # Candidate selection used fixtures, but the saved basket has just been checked.
            recommendation_warnings = [
                warning for warning in recommendation_warnings if not warning.startswith("Stable fixture prices")
            ]
        meals = [meal for meal, _ in meals_of_the_day(constraints) or [("dinner", None)]]
        warnings = self._deduplicate(
            recommendation_warnings
            + grocery.warnings
            + nutrition_scope_notes([*constraints.nutrition_constraints, *limit_targets(constraints.household, meals)])
        )
        eligible_count = len({item.recipe.id for item in recommendation_result.recommendations})
        if eligible_count == 1:
            warnings.append("Only one eligible recipe was available, so consecutive repetition could not be avoided.")
        if eligible_count < constraints.day_count:
            recipe_label = "recipe" if eligible_count == 1 else "recipes"
            days = "seven" if constraints.day_count == 7 else str(constraints.day_count)
            warnings.append(
                f"The current eligible catalog contains {eligible_count} {recipe_label}; "
                f"recipes are rotated across the {days} days."
            )
        warnings = self._deduplicate(warnings)
        placements = result.placements or [(index, "dinner", "main", 1, None) for index in range(len(selected))]
        scheduled = [
            ScheduledDish(
                planned_date=constraints.start_date + timedelta(days=slot_index),
                day_index=slot_index + 1,
                meal_type=meal_type,
                role_id=role_id,
                portion_share=portion_share,
                recommendation=recommendation,
                servings=servings,
                household_size=constraints.household_size,
            )
            for (slot_index, meal_type, role_id, portion_share, servings), recommendation in zip(
                placements, selected, strict=True
            )
        ]
        plan = self.repository.create(
            constraints=constraints,
            scheduled=scheduled,
            grocery=grocery,
            warnings=warnings,
            household_profile_id=household_profile_id,
            household_profile_version=household_profile_version,
            replaces_plan_id=replaces_plan_id,
            operation_run=self._operation_run(result.trace, started_at, warnings=warnings),
        )
        return self._to_response(plan)

    @staticmethod
    def _priced_as_asked(trace: dict, constraints: WeeklyMealPlanRequest) -> None:
        """A search's trace with the pricing its request asked for. Every week is chosen at snapshot prices
        (ADR-0058), so the planner's trace says fixture; that stays as the planning basis, but a live plan is no
        fixture plan to the console, its replays ("as stored") or its FairPrice count."""
        trace.setdefault("planning_pricing_mode", trace["requested_pricing_mode"])
        trace["requested_pricing_mode"] = trace["request"]["pricing_mode"] = constraints.pricing_mode

    def _search(
        self,
        constraints: WeeklyMealPlanRequest,
        candidates,
        *,
        profile_version: int | None = None,
        minimum_distinct_dishes: int = 0,
    ):
        """The week `generate` plans from these candidates (recipes, recommendations), nothing saved."""
        constraints = constraints.model_copy(update={"pricing_mode": "fixture"})
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
                    minimum_distinct_dishes=minimum_distinct_dishes,
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

    def check(
        self, constraints: WeeklyMealPlanRequest, *, minimum_distinct_dishes: int = 0
    ) -> ProductPlanningError | None:
        """What `generate` would answer for these constraints, nothing saved: None for a week, else its error.

        The week found is kept for `generate` with the same constraints, while the planner's pools are kept; a check
        of constraints whose week is kept answers from it. A check for at least `minimum_distinct_dishes` different
        dishes searches past a kept week with fewer, and the week it finds is the one kept: Plan saves the varied week
        (ADR-0067)."""
        constraints = self._live(constraints)
        seconds = get_settings().planning_pool_cache_seconds
        kept = found_weeks.get(self._found_key(constraints)) if seconds else None
        fresh = kept is not None and time.monotonic() - kept[0] < seconds
        if fresh and _distinct(kept[1][1]) >= minimum_distinct_dishes:
            # The same search over the same pool finds the same week, and it stays kept for Plan: a budget refusal
            # checks the amount it offers, and tapping that offer asked for the very same week (WP1 1b, 2026-10-08).
            return None
        started = time.monotonic()
        try:
            searched = self._search(
                constraints,
                self._checked_candidates(constraints),
                minimum_distinct_dishes=minimum_distinct_dishes,
            )
        except ProductPlanningError as error:
            return error
        # Kept for the Plan that follows this check (`found_weeks`): the 2026-10-04 walkthrough's reply that took
        # the last detail planned the week in 8 s, then Plan planned it again in 5 s.
        if seconds:
            now = time.monotonic()
            # pop, not del: requests run on several threads (a sync route) and may expire the same entry.
            for key in [key for key, (at, _) in list(found_weeks.items()) if now - at >= seconds]:
                found_weeks.pop(key, None)
            while len(found_weeks) >= FOUND_WEEKS_KEPT:
                found_weeks.pop(next(iter(found_weeks), None), None)
            # What the search took, for the run of the Plan that saves this week without searching (`generate`).
            searched[1].trace["search_seconds"] = round(now - started, 3)
            found_weeks[self._found_key(constraints)] = (now, searched)
        return None

    def checked_distinct_dishes(self, constraints: WeeklyMealPlanRequest) -> int | None:
        """Distinct recipes in the week most recently checked for these constraints, if still cached."""
        found = found_weeks.get(self._found_key(self._live(constraints)))
        if found is None or time.monotonic() - found[0] >= get_settings().planning_pool_cache_seconds:
            return None
        return _distinct(found[1][1])

    def _found_key(self, constraints: WeeklyMealPlanRequest, profile_version: int | None = None) -> tuple:
        return (
            id(self.recipe_repository.session.get_bind()),  # the database, as the pool is keyed
            self.repository.household_id,
            repr(self.planning_engine.limits),
            profile_version,
            # Validated again: an amount set by `model_copy` (an offered S$53) stays an int, as typed it is 53.0.
            type(constraints).model_validate(constraints.model_dump()).model_dump_json(),
        )

    def _candidates(self, constraints: WeeklyMealPlanRequest):
        """The recipes a week may use and the recommendations `generate` plans from first."""
        constraints = constraints.model_copy(update={"pricing_mode": "fixture"})
        # Every course a planned meal's roles may take enters the pool (ADR-0046), not only dinner's.
        meals = meals_of_the_day(constraints)
        recipes = pool_for(meals, self.recipe_repository.list_for_planning(courses=pool_courses(meals)))
        result = self.recommendation_service.recommend(
            pool_constraints(constraints),
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
        constraints = self._live(constraints)
        recipes, candidates = self._checked_candidates(constraints)
        return week_floor(constraints, candidates.recommendations, recipes)

    def cheapest_week(self, constraints: WeeklyMealPlanRequest, *, minimum_distinct_dishes: int = 0) -> float:
        """What a cost-led week with the requested variety costs at checkout, nothing saved.

        Every limit but the weekly budget holds. Adding a budget can change the bounded candidate
        packet, so a suggestion must check that amount through the budgeted path before offering it.
        With `minimum_distinct_dishes` the search bisects for the cheapest week it finds of that many different
        dishes. Raises ProductPlanningError when the search finds no week at all.
        """
        unbudgeted = self._live(constraints).model_copy(update={"weekly_budget_sgd": None})
        recipes, candidates = self._checked_candidates(unbudgeted)
        result = self.planning_engine.plan(
            unbudgeted.model_copy(update={"pricing_mode": "fixture"}),
            candidates.recommendations,
            recipes,
            selector=self.selector,
            cheapest=True,
            minimum_distinct_dishes=minimum_distinct_dishes,
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
        day_indices: list[int] | None = None,
        rest_days: list[int] | None = None,
        over_budget_by_trip: dict[int, float] | None = None,
        _used_elsewhere: Iterable[Recipe] = (),
        _check_whole_plan=None,
    ) -> list[ScheduledDish]:
        """Dishes for selected days from a saved week, nothing saved (ADR-0046 section 2).

        `constraints` carries the shape to plan and the budget left. `rest` is the rest of the week, each dish
        with its share of a household-size batch (`grocery_share`): its dishes are avoided while enough others
        remain, and in every attempt their uses there count towards the household's cap on uses. `keep` ((day
        index, meal) -> {role id: recipe id}) holds each meal's present dishes in their roles while a new one is
        added. `over_budget` plans the dishes over the budget when none fit it (none can when it is 0 or less), as
        cheaply as the planner finds, weighing costs against this amount (see `over_budget_pick` and `charge`
        below). `by_weight` is what the week's list buys by weight, so `charge` prices the week as its list will be.
        For two trips, `constraints` instead carries the full per-week budget and `rest_days` locates each
        unchanged dish. Each trip computes its own remaining budget before entering the single-trip search.
        """
        constraints = self._live(constraints).model_copy(update={"pricing_mode": "fixture"})
        _used_elsewhere = tuple(_used_elsewhere)
        planned_days = day_indices or list(range(first_day, first_day + day_count))
        if (
            len(planned_days) != day_count
            or planned_days != sorted(set(planned_days))
            or not planned_days
            or planned_days[0] != first_day
            or planned_days[0] < 1
            or planned_days[-1] > constraints.day_count
        ):
            raise ValueError("day_indices must contain day_count distinct, ordered days from the week")
        if constraints.day_count > meal_structure.trip_days():
            return self._plan_dishes_by_trip(
                constraints, planned_days, rest, rest_days, keep, over_budget, tuple(by_weight), over_budget_by_trip
            )
        start = constraints.start_date + timedelta(days=first_day - 1)
        # Compress selected calendar days for the planner, then map its placements back to the saved week.
        partial = constraints.model_copy(update={"start_date": start, "day_count": day_count})
        by_weight = tuple(by_weight)
        reserved = self.grocery_aggregator.estimate(
            [recipe for recipe, _ in rest],
            constraints,
            shares=[share for _, share in rest],
            by_weight=by_weight,
        )
        partial = partial.model_copy(
            update={"available_ingredients": remaining_stock(constraints.available_ingredients, reserved)}
        )
        meals = meals_of_the_day(partial)
        recipes = pool_for(meals, self.recipe_repository.list_for_planning(courses=pool_courses(meals)))
        recommendations = self.recommendation_service.recommend(
            pool_constraints(partial), deduct_pantry_from_cost=False, recipes=recipes, priced_release_only=True
        ).recommendations
        slugs = {recipe.id: recipe.slug for recipe in recipes}
        keep_ids = {recipe_id for roles in (keep or {}).values() for recipe_id in roles.values()}
        # A kept dish the planner no longer offers cannot stay: the meal is planned from every candidate.
        slot_by_day = {day: slot for slot, day in enumerate(planned_days)}
        kept = {
            (slot_by_day[day], meal): {role: slugs[recipe_id] for role, recipe_id in roles.items()}
            for (day, meal), roles in (keep or {}).items()
            if day in slot_by_day
            if keep_ids <= slugs.keys()
        }
        used = Counter(recipe.id for recipe, _ in rest) + Counter(recipe.id for recipe in _used_elsewhere)
        fresh = [item for item in recommendations if item.recipe.id in keep_ids or item.recipe.id not in used]
        budget = partial.weekly_budget_sgd
        within = budget is None or budget > 0 or budget == 0 or over_budget is None
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

        def basket(planned):
            week = [recipe for recipe, _ in rest] + [by_id[item.recipe.id] for item in planned.selected]
            shares = [share for _, share in rest] + [
                float(place[3] if place[4] is None else place[4] / partial.household_size)
                for place in planned.placements
            ]
            # Recompute against the original pantry, not the temporary package surplus.
            return self.grocery_aggregator.estimate(week, constraints, shares=shares, by_weight=by_weight)

        def charge(planned) -> float:
            """A plan over the budget as the week pays for it: the checkout with the rest of the week (a package
            both use is bought once), and a repeat of any dish in the week at one meal's share of `over_budget`
            and an empty optional dish at twice that, as `over_budget_pick` charges them among the meals it plans.
            Within those meals alone, a dinner's salad served again at lunch was no repeat (the 2026-10-02
            review: every lunch of mdw-dev-013 was one of its dinners)."""
            week = [recipe for recipe, _ in rest] + [by_id[item.recipe.id] for item in planned.selected]
            week += list(_used_elsewhere)
            total = basket(planned).purchase_total_sgd
            repeats = len(week) - len({recipe.id for recipe in week})
            empty = day_count * sum(len(roles) for _, roles in meals) - len(planned.selected)
            return total + over_budget / (day_count * len(meals)) * (repeats + EMPTY_OPTIONAL_ROLE_LOSS * empty)

        slots = day_count * sum(len(roles) for _, roles in meals)
        unfilled = None  # an addition the budget left empty, used only if no later step adds the dish
        for step in steps:
            found = []
            for pool, locked, request, hard in step:
                try:
                    candidate = self.planning_engine.plan(
                        request,
                        pool,
                        recipes,
                        selector=self.selector,
                        cheapest_last=False,
                        budget_is_hard=hard,
                        locked=locked,
                        used=Counter(recipe.slug for recipe, _ in rest)
                        + Counter(recipe.slug for recipe in _used_elsewhere),
                        dates=[constraints.start_date + timedelta(days=day - 1) for day in planned_days],
                        plan_days=planned_days,
                        plan_day_count=constraints.day_count,
                    )
                    if hard and budget is not None:
                        whole = basket(candidate)
                        ceiling = round(reserved.purchase_total_sgd * 100) + round(budget * 100)
                        if (
                            not reserved.complete
                            or not whole.complete
                            or round(whole.purchase_total_sgd * 100) > ceiling
                        ):
                            raise ProductPlanningError(
                                "no_feasible_plan",
                                "The changed dishes do not fit the whole week's checkout budget.",
                                {},
                            )
                    if hard and _check_whole_plan is not None and not _check_whole_plan(candidate):
                        raise ProductPlanningError(
                            "no_feasible_plan", "The change increases another shopping week beyond its budget.", {}
                        )
                    found.append(candidate)
                except ProductPlanningError as error:
                    failure = error
            if found:
                result = min(found, key=charge) if len(found) > 1 else found[0]
                # An empty optional dish is no addition: it does not "fit the budget", so the over-budget steps
                # get their turn, and the preview says what the dish costs (T30).
                if kept and step[0][3] and len(result.selected) < slots:
                    unfilled = unfilled or result
                    continue
                break
        else:
            if unfilled is None:
                raise failure
            result = unfilled
        placements = result.placements or [(index, "dinner", "main", 1, None) for index in range(len(result.selected))]
        return [
            ScheduledDish(
                planned_date=constraints.start_date + timedelta(days=planned_days[slot_index] - 1),
                day_index=planned_days[slot_index],
                meal_type=meal_type,
                role_id=role_id,
                portion_share=share,
                recommendation=recommendation,
                servings=servings,
                household_size=constraints.household_size,
            )
            for (slot_index, meal_type, role_id, share, servings), recommendation in zip(
                placements, result.selected, strict=True
            )
        ]

    def _plan_dishes_by_trip(
        self, constraints, days, rest, rest_days, keep, over_budget, by_weight, over_budget_by_trip
    ):
        """Search each shopping week with its own budget and the original pantry left by earlier meals.

        Package surplus is temporary stock within its own trip. As in the canonical
        two-trip basket, only unspent original pantry passes to the next trip.
        """
        if rest_days is None:
            if rest:
                raise ValueError("rest_days is required for a two-trip replan")
            rest_days = []
        if len(rest_days) != len(rest) or any(day < 1 or day > constraints.day_count for day in rest_days):
            raise ValueError("rest_days must locate every unchanged dish in the plan")
        interval = meal_structure.trip_days()
        pantry = constraints.available_ingredients
        output = []
        prior_recipes = []
        for offset in range(0, constraints.day_count, interval):
            end = min(offset + interval, constraints.day_count)
            changed = [day - offset for day in days if offset < day <= end]
            retained = [pair for pair, day in zip(rest, rest_days, strict=True) if offset < day <= end]
            request = constraints.model_copy(
                update={
                    "start_date": constraints.start_date + timedelta(days=offset),
                    "day_count": end - offset,
                    "available_ingredients": pantry,
                }
            )
            reserved = self.grocery_aggregator.estimate(
                [r for r, _ in retained], request, shares=[s for _, s in retained], by_weight=by_weight
            )
            selected = []
            if changed:
                budget = request.weekly_budget_sgd
                left = (
                    None if budget is None else (round(budget * 100) - round(reserved.purchase_total_sgd * 100)) / 100
                )
                if left is not None and left < 0 and over_budget is None:
                    raise ProductPlanningError("no_feasible_plan", "This shopping week already exceeds its budget.", {})
                elsewhere = prior_recipes + [r for (r, _), day in zip(rest, rest_days, strict=True) if day > end]

                def estimate_whole(candidate=None, *, changed=tuple(changed), offset=offset):
                    ids = [dish.recommendation.recipe.id for dish in output]
                    if candidate is not None:
                        ids += [item.recipe.id for item in candidate.selected]
                    catalog = {r.id: r for r in self.recipe_repository.list_by_ids(ids)}
                    all_recipes = [r for r, _ in rest] + [catalog[d.recommendation.recipe.id] for d in output]
                    all_shares = [share for _, share in rest] + [
                        float(d.portion_share if d.servings is None else d.servings / constraints.household_size)
                        for d in output
                    ]
                    all_days = list(rest_days) + [d.day_index for d in output]
                    if candidate is not None:
                        all_recipes += [catalog[item.recipe.id] for item in candidate.selected]
                        all_shares += [
                            float(p[3] if p[4] is None else p[4] / constraints.household_size)
                            for p in candidate.placements
                        ]
                        all_days += [changed[p[0]] + offset for p in candidate.placements]
                    return self.grocery_aggregator.estimate(
                        all_recipes,
                        constraints,
                        shares=all_shares,
                        by_weight=by_weight,
                        trips=[1 + (day - 1) // interval for day in all_days],
                    )

                def trip_costs(basket):
                    costs = Counter()
                    for line in basket.items:
                        costs[line.shopping_trip or 1] += round(line.purchase_cost_sgd * 100)
                    return costs

                baseline = trip_costs(estimate_whole())

                def check_whole_plan(
                    candidate, *, budget=budget, offset=offset, baseline=baseline, estimate_whole=estimate_whole
                ):
                    if budget is None:
                        return True
                    basket = estimate_whole(candidate)
                    costs = trip_costs(basket)
                    # Do not blame an untouched pre-existing overrun. But an indirect increase
                    # caused by spending its stock must pass the same budget check as an edit.
                    affected = {1 + offset // interval} | {t for t in costs if costs[t] > baseline[t]}
                    return basket.complete and all(costs[t] <= round(budget * 100) for t in affected)

                selected = self.plan_dishes(
                    request.model_copy(update={"weekly_budget_sgd": left}),
                    first_day=min(changed),
                    day_count=len(changed),
                    day_indices=changed,
                    rest=retained,
                    keep={
                        (day - offset, meal): roles
                        for (day, meal), roles in (keep or {}).items()
                        if offset < day <= end
                    },
                    over_budget=(
                        over_budget_by_trip[1 + offset // interval]
                        if over_budget_by_trip is not None
                        else None
                        if over_budget is None
                        else round(over_budget * len(changed) / len(days), 2)
                    ),
                    by_weight=by_weight,
                    _used_elsewhere=elsewhere,
                    _check_whole_plan=check_whole_plan,
                )
                output.extend(replace(dish, day_index=dish.day_index + offset) for dish in selected)
            added = self.recipe_repository.list_by_ids([dish.recommendation.recipe.id for dish in selected])
            by_id = {recipe.id: recipe for recipe in added}
            recipes = [r for r, _ in retained] + [by_id[dish.recommendation.recipe.id] for dish in selected]
            shares = [s for _, s in retained] + [
                float(dish.portion_share if dish.servings is None else dish.servings / constraints.household_size)
                for dish in selected
            ]
            full = self.grocery_aggregator.estimate(recipes, request, shares=shares, by_weight=by_weight)
            if changed and over_budget is None and request.weekly_budget_sgd is not None:
                if not full.complete or round(full.purchase_total_sgd * 100) > round(request.weekly_budget_sgd * 100):
                    raise ProductPlanningError(
                        "no_feasible_plan", "The changed plan does not fit each shopping week's checkout budget.", {}
                    )
            pantry = remaining_stock(pantry, full, include_surplus=False)
            prior_recipes.extend(recipes)
        return output

    def _operation_run(
        self, trace: dict, started_at: datetime, *, error: str | None = None, warnings: Iterable[str] = ()
    ) -> OperationRun:
        # The sources the planner priced with, and FairPrice where it priced the saved list (`final_list`). Only the
        # provider is added: a line FairPrice did not confirm keeps its evidence label (release_snapshot), which is
        # no provider, and with it "fairprice,fixture,release_snapshot" overflows provider_mode's String(30).
        checked = {"fairprice"} & set(trace.get("final_list", {}).get("price_sources", []))
        sources = {*trace.get("observed_sources", []), *checked}
        return OperationRun(
            trace_id=f"planning-{uuid4().hex}",
            run_type="planning",
            status="failed" if error else "succeeded",
            triggered_by_user_id=self.actor_user_id,
            household_id=self.repository.household_id,
            input_digest=trace["input_digest"],
            code_commit=code_commit(),
            catalog_version=trace.get("catalog_version"),
            product_snapshot_version=trace.get("product_snapshot_version"),
            policy_version=trace["policy_version"],
            algorithm_version=f"{trace['algorithm']}-product-v1",
            provider_mode=",".join(sorted(sources)) or None,
            artifact_references=[{"kind": "planning_trace", "data": trace}],
            warnings=list(warnings),
            error_code=trace["status"] if error else None,
            error_detail=error,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    def delete(self, plan_id: int) -> bool:
        return self.repository.delete(plan_id)

    def get(self, plan_id: int) -> WeeklyMealPlanResponse | None:
        plan = self.repository.get(plan_id)
        if plan is None:
            return None
        return self._to_response(plan).model_copy(update={"current": self.repository.is_current(plan)})

    def list_recent(self, *, limit: int) -> WeeklyMealPlanCollectionResponse:
        # Newest first, so every plan newer than one is listed before it (the limit cuts only older ones).
        plans = self.repository.list_recent(limit=limit)
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
                    day_count=plan.day_count,
                    household_size=plan.household_size,
                    purchase_total_sgd=float(plan.purchase_total_sgd),
                    consumed_total_sgd=(
                        float(plan.consumed_total_sgd) if plan.consumed_total_sgd is not None else None
                    ),
                    within_weekly_budget=plan.within_weekly_budget,
                    created_at=plan.created_at,
                    current=not replaced_by(plan, plans[:index]),
                )
                for index, plan in enumerate(plans)
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
        return self.get(plan.id) if plan is not None else None

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
        return self.get(plan.id) if plan is not None else None

    def dashboard(self, plan_id: int) -> WeeklyNutritionDashboardResponse | None:
        plan = self.repository.get(plan_id)
        if plan is None:
            return None

        planned_totals = self._empty_nutrition_totals()
        completed_totals = self._empty_nutrition_totals()
        counts = {"planned": 0, "completed": 0, "skipped": 0}
        days: list[NutritionDashboardDayResponse] = []

        # In the order they are eaten: by day, then breakfast, lunch, dinner. Entries are stored by day and
        # id, so a lunch added to a dinner week would otherwise come after that day's dinner.
        eaten = sorted(plan.entries, key=lambda entry: (entry.day_index, _meal_rank(entry.meal_type), entry.id))
        not_for = self._not_for(plan)
        # Each dish's Like, Dislike or Never again, so its buttons show pressed (ADR-0087).
        feedback = RecipeFeedbackRepository(self.repository.session, household_id=self.repository.household_id).states()
        constraints = plan.constraints if isinstance(plan.constraints, dict) else {}
        # Facts true of each dish, from what the week saved (layer 08 section 7.2).
        reasons = dish_reasons(
            eaten, household_size=plan.household_size, health_preferences=constraints.get("health_preferences") or []
        )
        for entry in eaten:
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
                    not_for=not_for(entry),
                    feedback=feedback.get(entry.recipe.id),
                    reasons=reasons.get(entry.id, []),
                    cost_per_serving_sgd=cost_per_serving(entry, plan.household_size),
                )
            )

        completed_count = counts["completed"]
        return WeeklyNutritionDashboardResponse(
            plan_id=plan.id,
            revision=plan.revision,
            start_date=plan.start_date,
            end_date=plan.end_date,
            day_count=plan.day_count,
            household_size=plan.household_size,
            completion_rate=round(completed_count / max(len(plan.entries), 1) * 100, 1),
            status_counts=MealPlanStatusCounts(**counts),
            nutrition_targets=constraints.get("nutrition_targets", {}),
            planned_nutrition_per_person=self._nutrition_summary(planned_totals),
            completed_nutrition_per_person=self._nutrition_summary(completed_totals),
            days=days,
        )

    @staticmethod
    def _not_for(plan: MealPlan):
        """`not_for(entry)`: the members home for that entry's meal who cannot eat its dish, by name, read from the
        week's own household block (ADR-0071 section 1). Nobody for a week planned without one.

        An "A or B" line is judged by the option this household cooks (`alternatives.lines`), as the planner judged
        it: a dish made with turkey for a member who avoids beef is counted in that member's servings, so it is not
        labelled "Not for" them."""
        try:
            request = WeeklyMealPlanRequest.model_validate(plan.constraints)
        except ValidationError:
            return lambda entry: []
        household = request.household
        if household is None or household.members is None:
            return lambda entry: []
        keys = {(entry.planned_date, entry.meal_type) for entry in plan.entries}
        at_meal = {key: slot_members(household, *key, None) for key in keys}
        cooked: dict[int, list] = {}

        def not_for(entry) -> list[str]:
            members = at_meal.get((entry.planned_date, entry.meal_type), ())
            if members and entry.recipe.id not in cooked:
                cooked[entry.recipe.id] = alternatives.lines(entry.recipe, request)
            return [m.name for m in members if not catalog_can_eat(m, entry.recipe, cooked[entry.recipe.id])]

        return not_for

    @staticmethod
    def _to_response(plan: MealPlan) -> WeeklyMealPlanResponse:
        days: list[WeeklyPlanDayResponse] = []
        not_for = WeeklyMealPlanService._not_for(plan)
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
                    servings=float(entry.servings) if entry.servings is not None else None,
                    recipe=RecipeListItemResponse.model_validate(entry.recipe),
                    recommendation_score=float(entry.recommendation_score),
                    nutrition_per_person=nutrition,
                    consumed_cost_sgd=float(entry.consumed_cost_sgd),
                    purchase_cost_sgd=float(entry.purchase_cost_sgd),
                    status=entry.status,
                    is_locked=entry.is_locked,
                    consumed_at=WeeklyMealPlanService._as_utc(entry.consumed_at),
                    not_for=not_for(entry),
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
            fairprice_cart=cart_state(plan.fairprice_cart, grocery_lines),
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
                in_stock=not (item.price_evidence and item.price_evidence.get("lookup_status") == "out_of_stock"),
                source=item.product_source,
                halal_certified=item.product_halal_certified,
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
            shopping_trip=item.shopping_trip,
            perishable=item.perishable,
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
