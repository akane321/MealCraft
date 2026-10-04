"""Product boundary for the fixed-product Planning v2 path.

This adapter consumes recorded recommendation observations. It never retrieves
prices after validation, and never promotes a bounded miss into a global proof.
"""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from fractions import Fraction
from math import ceil, isfinite

from app.data.allergens import checked_allergens
from app.data.ingredient_hierarchy import expand_exclusions
from app.data.units import UNIT_BASE
from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.capability import PlanningCapabilityError, require_composition_enabled
from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.grocery_estimator import not_purchased
from app.planning.meal_beam import (
    EMPTY_OPTIONAL_ROLE_LOSS,
    MealBeamLimits,
    MealBeamPlanner,
    MealBeamResult,
    assignments_of,
    empty_roles,
)
from app.planning.meal_composition import dish_servings
from app.planning.nutrition_scope import compile_nutrition_targets, nutrition_guard_loss
from app.planning.product_input import product_input
from app.planning.recipe_input import recipe_input
from app.planning.recipe_quality import dish_family, dish_kind
from app.planning.recommendation_engine import CANDIDATE_LIMIT
from app.planning.vegetable_led import catalog_vegetable_led, vegetable_role
from app.planning.weekly_planner import WeeklyPlanSelectionError, WeeklyPlanSelector
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningConstraintCheck,
    PlanningNutritionBand,
    PlanningPantryItem,
    PlanningRecipeCount,
    PlanningRepetitionRules,
    PlanningSlot,
)
from app.schemas.product import GroceryLineEstimate
from app.schemas.recipe import RecipeListItemResponse
from app.services.recipe import RecipeService

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def normalized(quantity, unit):
    base, multiplier = UNIT_BASE.get(unit, (unit, 1))
    if quantity is not None and not isfinite(quantity):
        return quantity, base
    return (float(Fraction(str(quantity)) * Fraction(str(multiplier))) if quantity is not None else None), base


# Fallback searches for a stated budget: how strongly a dish's cost, relative to the
# budget for one dinner, is added to its rank loss (which lies in 0..1).
COST_WEIGHTS = (1.0, 4.0, 16.0)
# The cheapest-week search (see `plan`): the first budget it tries, how close it bisects the least budget it
# completes a week within (a share of that budget), and the beam it searches with. Lighter than the ranked
# search's beam: on the release catalog it finds as cheap a week in a third of the time (PR #211); 32 meals a
# slot find no week at all for three meals with no dish twice. Bisecting under the cheapest week found so far
# rather than under the budget it was found within takes 3 to 7 probes instead of 6 to 9 there (48 shapes,
# sizes and caps on uses), and finds the same week in 35 of them and one within 5% in 44 (PR #211 round 1).
CHEAPEST_START_SGD = 64
CHEAPEST_PRECISION = 0.05
CHEAPEST_MEAL_OPTIONS = 64
# Meals of at most this many dishes: the planner's searches answer within a chat reply. On the release catalog
# a week of them is checked in at most 6.7 s and its cheapest week found in at most 4.5 s (1 or 4 people, up to
# three meals a day, any cap on uses); for a meal of four to six dishes either takes 5 to 26 s, and the cheapest
# week minutes with no dish twice (ADR-0046 section 3: a plan answers within 10 s). A plan of such meals that
# no week fits under its budget ends without the cheapest-week search.
QUICK_MEAL_DISHES = 3


def meals_of_the_day(constraints) -> list[tuple[str, list]] | None:
    """(meal type, dish roles) for each planned meal of a day, in day order; None for the one-dish dinner MVP.

    A plan shape (ADR-0046) names the meals; an older dinner composition (ADR-0036) is a dinner-only shape.
    """
    shape = getattr(constraints, "plan_shape", None)
    if shape is not None:
        return shape.ordered()
    composition = getattr(constraints, "meal_composition", None)
    return [("dinner", composition)] if composition is not None else None


def meal_affinity(recipe) -> tuple[str, ...]:
    """A release recipe states its meal types (ADR-0038); a curated one's meal_type
    may name one; otherwise it is a lunch or dinner dish."""
    stated = tuple(m for m in getattr(recipe, "meal_types", None) or () if m in MEAL_TYPES)
    meal_type = getattr(recipe, "meal_type", None)
    return stated or ((meal_type,) if meal_type in MEAL_TYPES else ("lunch", "dinner"))


def dish_cost(recommendation) -> float:
    """What the dish's ingredients cost as used, or as bought when that is all we know."""
    estimate = recommendation.grocery_estimate
    if estimate is None:
        return 0.0
    if estimate.consumed_total_sgd is not None:
        return estimate.consumed_total_sgd
    return estimate.purchase_total_sgd


class ProductPlanningError(WeeklyPlanSelectionError):
    def __init__(self, status, message, trace, *, problem=None):
        super().__init__(message)
        self.status = status
        trace["status"] = status
        self.trace = trace
        self.problem = problem


@dataclass
class ProductPlan:
    selected: list
    grocery: WeeklyGroceryEstimateResponse
    trace: dict
    # One per selected recommendation: (slot index, meal type, role, portion share).
    placements: list[tuple[int, str, str, Fraction]] | None = None


# Recommendations kept for each course a composed meal's roles admit.
COMPOSED_CANDIDATES_PER_COURSE = 24
# How many of the most varied weeks found, and of the cheapest, spend their room on variety.
VARIED_STARTS = 8


def families_first(recommendations, seen=()) -> list:
    """The first of each dish family in order, then the rest: "Chinese Fried Rice" and "Basic Fried Rice" are
    one dinner twice, so a packet holds as many different dishes as the catalog has before it holds both."""
    seen = set(seen)
    first, again = [], []
    for recommendation in recommendations:
        family = dish_family(recommendation.recipe.title)
        (again if family in seen else first).append(recommendation)
        seen.add(family)
    return first + again


def composed_packet(
    composition, day_count: int, budget, recommendations, recipes, *, keep=()
) -> tuple[list, dict[str, int]]:
    """The recommendations a composed week is planned from, and how many each kind of dish keeps.

    The meal beam ranks each role's dishes itself; keep the best of every course it may fill, enough of each
    for every slot that uses it to get a different dish (a lunch-and-dinner week needs fourteen mains, not the
    24 a dinner week kept).
    """
    uses: dict[str, int] = {}
    for _, roles in composition:
        for role in roles:
            for course in role.courses:
                # The vegetable role keeps the best vegetable-led dishes, which the best sides are not.
                key = f"vegetable {course}" if vegetable_role(role.role_id) else course
                uses[key] = uses.get(key, 0) + day_count
    limits = {key: max(COMPOSED_CANDIDATES_PER_COURSE, 3 * count) for key, count in uses.items()}
    by_id = {r.id: r for r in recipes}
    ranked_by_key: dict[str, list] = {}
    for recommendation in recommendations:
        recipe = by_id.get(recommendation.recipe.id)
        course = getattr(recipe, "course", None) or "main"
        led = f"vegetable {course}"
        for key in (course, led):
            if key in limits and (key != led or (recipe is not None and catalog_vegetable_led(recipe))):
                ranked_by_key.setdefault(key, []).append(recommendation)
    chosen: set[int] = set()
    for key, ranked in ranked_by_key.items():
        best = ranked[: limits[key]]
        if budget is not None:
            # As the one-dish packet does: the best-ranked dishes are rarely the cheap ones, so with a budget
            # half of each kind's places go to the cheapest of the rest. Kept by rank alone, the 2026-10-02
            # walkthrough's soups cost S$12 to S$37 in whole packages each and one came five times in a week.
            # The cheapest are often one dish many times ("Chinese Fried Rice", "Basic Fried Rice"): one of
            # each family comes first. (Without a budget the packet stays as ranked: reordered by family, a
            # week of per-day bands, mdw-dev-007, kept 17 distinct dishes of 28 instead of 24.)
            ranked = families_first(ranked)
            best = ranked[: limits[key] // 2]
            kept = {dish_family(r.recipe.title) for r in best}
            best += families_first(sorted(ranked[len(best) :], key=dish_cost), kept)[: limits[key] - len(best)]
        chosen |= {r.recipe.id for r in best}
    return [r for r in recommendations if r.recipe.id in chosen or (keep and r.recipe.slug in keep)], limits


class ProductPlanningEngine:
    def __init__(self, *, limits=None, validator=None):
        self.limits = limits or BeamLimits()
        self.validator = validator or FinalPlanningValidator()

    def _packet_limit(self, day_count: int) -> int:
        """How many candidates the beam search can visit on every day within its expansion budget.

        Each day expands every kept state against every candidate, so a packet
        larger than max_expansions / (width x days) exhausts the budget before one
        full week is built. The recommendation limit is far larger on the full
        catalog; the best-scored candidates are the ones kept.
        """
        return min(CANDIDATE_LIMIT, max(1, self.limits.max_expansions // (self.limits.width * day_count)))

    def plan(
        self,
        constraints,
        recommendations,
        recipes,
        *,
        selector=None,
        profile_version=None,
        cheapest=False,
        cheapest_last=True,
        budget_is_hard=True,
        locked=None,
        used=None,
    ):
        """A validated week, or ProductPlanningError saying why there is none.

        `locked` keeps a meal's present dishes while one is added to it: (day offset, meal) -> {role id:
        recipe slug}. `budget_is_hard=False` plans a change the household may take over the budget (owner,
        2026-10-02): every other rule holds, the budget is only reported, and of the weeks found (cost-led
        searches among them) one costing least at the checkout is chosen (see `over_budget_pick`). `used` (recipe
        slug -> uses) is what the rest of a week already serves when part of it is planned: those uses count
        towards the household's cap on uses.
        """
        locked = locked or {}
        kept_dishes = {slug for roles in locked.values() for slug in roles.values()}
        trace = {
            "trace_version": "planning-product-v1",
            "status": "needs_data",
            "evidence": "needs_data",
            "algorithm": constraints.planner_strategy,
            "settings": asdict(self.limits),
            "seed": 0,
            "timeout_seconds": None,
            "dominance_rule": "per-day-recipe-multiset-and-last-recipe-v1",
            "candidate_limit": self._packet_limit(constraints.day_count),
            "requested_pricing_mode": constraints.pricing_mode,
            "profile_version": profile_version,
            "input_digest": digest(constraints.model_dump(mode="json")),
            "policy_version": (
                "product-scoped-nutrition-v1" if constraints.nutrition_constraints else "product-fixed-shopping-v1"
            ),
            "validation": None,
        }
        trace["request"] = constraints.model_dump(mode="json")
        # The meals of each day and their dish roles (ADR-0046). None is the MVP: one dish a dinner.
        shape = meals_of_the_day(constraints)
        composition = shape  # kept as the name for "planned with the meal beam" below
        try:
            for _, roles in shape or []:
                require_composition_enabled(roles)
        except PlanningCapabilityError as error:
            raise ProductPlanningError("needs_clarification", str(error), trace) from error
        if composition is not None and constraints.planner_strategy != "beam":
            raise ProductPlanningError(
                "needs_clarification", "The baseline plans one dish a meal; use the beam planner for several.", trace
            )
        for budget in (constraints.weekly_budget_sgd, constraints.budget_per_meal_sgd):
            if budget is not None and (Fraction(str(budget)) * 100).denominator != 1:
                raise ProductPlanningError("needs_clarification", "Enter a budget in whole cents and try again.", trace)
        pantry_ids = [p.normalized_name for p in constraints.available_ingredients]
        if len(set(pantry_ids)) != len(pantry_ids):
            raise ProductPlanningError(
                "needs_clarification", "Combine duplicate pantry entries before trying again.", trace
            )
        if any(p.quantity is not None and not isfinite(p.quantity) for p in constraints.available_ingredients):
            raise ProductPlanningError("needs_clarification", "Enter finite pantry quantities and try again.", trace)
        if set(constraints.allergens) - set(checked_allergens()):
            raise ProductPlanningError(
                "needs_data",
                "Recipe coverage for a requested allergen is missing; update the allergen data before planning.",
                trace,
            )
        # Recommendations arrive best first; keep as many as the search can visit.
        if composition is None:
            # "Chinese Fried Rice" and "Basic Fried Rice" read as the same dinner twice; keep the
            # better-ranked one of each dish family.
            seen: set[str] = set()
            ranked = []
            for recommendation in recommendations:
                family = dish_family(recommendation.recipe.title)
                if family not in seen:
                    seen.add(family)
                    ranked.append(recommendation)
            limit = self._packet_limit(constraints.day_count)
            # A dinner slot takes dinner dishes whenever there are enough for the week;
            # meal affinity stays only a soft score when it would otherwise run short.
            meal_types = {r.id: meal_affinity(r) for r in recipes}
            dinners = [r for r in ranked if "dinner" in meal_types.get(r.recipe.id, ("dinner",))]
            if constraints.day_count <= len(dinners) < len(ranked):
                trace["meal_type_filtered"] = len(ranked) - len(dinners)
                ranked = dinners
            if constraints.weekly_budget_sgd is not None and len(ranked) > limit:
                # The best-ranked dishes are rarely the cheap ones; with a budget, half
                # the packet is the cheapest of the rest so a week within it can exist.
                best = ranked[: limit // 2]
                cheapest = sorted(ranked[limit // 2 :], key=dish_cost)[: limit - len(best)]
                trace["budget_packet"] = {"ranked": len(best), "cheapest": len(cheapest)}
                ranked = best + cheapest
            recommendations = ranked[:limit]
        else:
            recommendations, limits = composed_packet(
                composition,
                constraints.day_count,
                constraints.weekly_budget_sgd,
                recommendations,
                recipes,
                keep=kept_dishes,
            )
            trace["candidate_limit"] = limits
        if not recommendations:
            trace.update(status="candidate_rejected", evidence="bounded_search_exhausted")
            raise ProductPlanningError(
                "candidate_rejected", "No candidate plan was found; try a different recipe selection.", trace
            )
        by_id = {r.id: r for r in recipes}
        candidates, options, observations, display_names = [], {}, {}, {}
        provenance = {}  # product id -> the PriceEvidence of the observation the planner prices with
        recipe_snapshots = {}
        diagnostics = []
        for recommendation in sorted(recommendations, key=lambda r: r.recipe.slug):
            if recommendation.recipe.id not in by_id:
                diagnostics.append("recipe_snapshot_missing")
                continue
            source = RecipeService._to_detail(by_id[recommendation.recipe.id], constraints)
            recipe_snapshots[source.slug] = RecipeListItemResponse.model_validate(source.model_dump())
            # Tap water and ice are never bought, so they are not shopping requirements.
            source.ingredients = [item for item in source.ingredients if not not_purchased(item.normalized_name)]
            for ingredient in source.ingredients:
                display_names[ingredient.normalized_name] = ingredient.name
                ingredient.quantity, ingredient.unit = normalized(ingredient.quantity, ingredient.unit)
            converted = recipe_input(source, allowed_meal_types=meal_affinity(source), nutrition_basis="per_serving")
            if converted.candidate is None:
                diagnostics.extend(converted.issues)
                continue
            candidate = converted.candidate
            if composition is not None and candidate.course is None:
                # The curated catalog predates course labels and holds only dinner mains.
                candidate = candidate.model_copy(update={"course": "main"})
            candidates.append(candidate)
            estimate = recommendation.grocery_estimate
            for line in estimate.items if estimate else []:
                if line.product is None:
                    continue
                product = line.product.model_copy(deep=True)
                product.package_size, product.package_unit = normalized(product.package_size, product.package_unit)
                _, unit = normalized(line.required_quantity, line.unit)
                if not unit:
                    continue
                projected = product_input(product, ingredient_id=line.ingredient_name, required_unit=unit)
                if projected.option is None:
                    diagnostics.extend(projected.issues)
                    continue
                option = projected.option
                prior = options.get(option.product_id)
                if prior is not None and prior.ingredient_id != option.ingredient_id:
                    # One product bought for two ingredients (eggs for egg and egg yolk)
                    # is planned as a separate purchase for each.
                    option = option.model_copy(update={"product_id": f"{option.product_id}@{option.ingredient_id}"})
                    prior = options.get(option.product_id)
                if prior is not None and prior != option:
                    diagnostics.append("conflicting_product_observation")
                options[option.product_id] = option
                observations[option.product_id] = projected.observation
                provenance[option.product_id] = line.evidence
        trace["input_issues"] = sorted(set(diagnostics))
        trace["observed_sources"] = sorted({p.source for p in observations.values()})
        if not candidates or "conflicting_product_observation" in diagnostics:
            raise ProductPlanningError(
                "needs_data", "Recipe or price details could not be verified; refresh them and try again.", trace
            )
        slots = [
            PlanningSlot(
                slot_id=f"slot-{i}" if meal == "dinner" else f"slot-{i}-{meal}",
                planned_date=constraints.start_date + timedelta(days=i),
                meal_type=meal,
                servings=constraints.household_size,
                max_time_minutes=constraints.max_cooking_time_minutes,
                composition=roles,
                locked_roles=locked.get((i, meal)),
            )
            for i in range(constraints.day_count)
            for meal, roles in (composition or [("dinner", None)])
        ]
        slot_day = {
            slot.slot_id: (index // len(composition or [0]), slot.meal_type) for index, slot in enumerate(slots)
        }
        pantry = []
        for item in constraints.available_ingredients:
            quantity, unit = normalized(item.quantity, item.unit)
            pantry.append(PlanningPantryItem(ingredient_id=item.normalized_name, quantity=quantity, unit=unit))
        bands = compile_nutrition_targets(
            constraints.nutrition_constraints, constraints.nutrition_guard_band, meals_per_day=len(composition or [0])
        )
        trace["nutrition_scope"] = [b.model_dump(exclude={"lower", "upper"}) for b in bands]
        trace["settings"]["nutrition_guard_band"] = constraints.nutrition_guard_band
        if constraints.max_sodium_mg_per_meal is not None:
            bands.append(
                PlanningNutritionBand(metric="sodium_mg", scope="per_slot", upper=constraints.max_sodium_mg_per_meal)
            )
        cap = constraints.max_uses_per_recipe
        problem = FinalPlanningProblem(
            problem_id="product-request",
            slots=slots,
            recipes=candidates,
            pantry=pantry,
            products=[options[k] for k in sorted(options)],
            allergens=constraints.allergens,
            allergen_vocabulary=sorted(checked_allergens()),
            # "No pork" also removes bacon: the checks downstream match ids exactly, so they get the expanded list.
            excluded_ingredients=expand_exclusions(constraints.excluded_ingredients),
            dietary_requirements=constraints.dietary_preferences,
            health_preferences=constraints.health_preferences,
            nutrition_bands=bands,
            purchase_budget_sgd=constraints.weekly_budget_sgd,
            budget_is_hard=budget_is_hard,
            # Only a stated cap is a rule; the search and the validator both hold it (ADR-0046 variety), and a dish
            # the rest of the week serves has only what its uses there leave of it.
            repetition_rules=(
                PlanningRepetitionRules(
                    max_uses_per_recipe=cap,
                    recipe_counts=[
                        PlanningRecipeCount(recipe_id=slug, max_uses=max(0, cap - count))
                        for slug, count in sorted((used or {}).items())
                    ],
                )
                if cap is not None
                else None
            ),
            catalog_version=digest([r.model_dump(mode="json") for r in candidates]),
            product_snapshot_version=digest([observations[k].model_dump(mode="json") for k in sorted(options)]),
            policy_version=trace["policy_version"],
        )
        trace.update(
            packet_digest=digest(problem.model_dump(mode="json")),
            catalog_version=problem.catalog_version,
            product_snapshot_version=problem.product_snapshot_version,
        )
        # Slot-local eligibility is one-dish arithmetic; composed meals are checked by the meal beam.
        compiled = compile_search_domains(problem) if composition is None else None
        trace["compiled"] = asdict(compiled) if compiled is not None else None
        trace["proof_scope"] = "supplied_candidate_packet_only"
        trace["validation_attempts"] = []
        builder = FinalScopeReferencePlanner()
        fallback = None  # cost-led searches, run only when every ranked week fails (see below)
        last_resort = None  # the cheapest-week search, after every other week failed (see below)
        if cheapest and (composition is None or constraints.weekly_budget_sgd is not None):
            raise ProductPlanningError(
                "needs_clarification", "The cheapest week is searched for a composed week with no budget.", trace
            )
        if constraints.planner_strategy == "greedy-baseline":
            try:
                chosen, _ = (selector or WeeklyPlanSelector()).select(recommendations, constraints)
            except WeeklyPlanSelectionError as error:
                trace.update(evidence="bounded_search_exhausted")
                raise ProductPlanningError(
                    "candidate_rejected", "No baseline plan was found; try another recipe selection.", trace
                ) from error
            assignments_list = [
                [
                    PlanningAssignment(slot_id=s.slot_id, recipe_id=r.recipe.slug)
                    for s, r in zip(slots, chosen, strict=True)
                ]
            ]
            trace["search"] = {"baseline": True, "complete_proof": False}
        else:
            # Preserve the product's existing nutrition, pantry and time ranking.
            # These scores only order candidates; the validator never reads them.
            losses = {r.recipe.slug: 1 - r.total_score / 100 for r in recommendations}
            trace["ranking"] = {"policy": "recommendation-score-v1", "digest": digest(losses)}
            titles = {r.recipe.slug: r.recipe.title for r in recommendations}

            def sameness(dishes) -> tuple[int, int]:
                """Repeated dishes, then dishes of one kind ("fried rice"), in a week."""
                kinds = [dish_kind(titles[recipe]) for recipe in dishes]
                return len(dishes) - len(set(dishes)), len(kinds) - len(set(kinds))

            if composition is None:
                search = BeamPlanner(self.limits, local_losses=losses).search_candidates(problem.model_copy(deep=True))
                # Among the weeks the search kept, the most varied is tried first; a search loss
                # term for "same kind" would prune the cheap weeks a budget needs instead.
                choices = [
                    state.choices
                    for state in sorted(
                        search.states, key=lambda s: (sameness([r for _, r in s.choices]), s.loss, s.choices)
                    )
                ]
                budget = constraints.weekly_budget_sgd
                if budget is not None:
                    # The ranking never sees prices, so a tight budget can fail on every
                    # retained week. Only then do fallback searches blend each dish's
                    # grocery cost into its rank, from lightly to strongly.
                    per_slot = budget / constraints.day_count
                    cost = {r.recipe.slug: dish_cost(r) / per_slot for r in recommendations}

                    def cost_fallback() -> list[list[PlanningAssignment]]:
                        found_states: list = []
                        for weight in COST_WEIGHTS:
                            blended = {slug: loss + weight * cost[slug] for slug, loss in losses.items()}
                            found = BeamPlanner(self.limits, local_losses=blended).search_candidates(
                                problem.model_copy(deep=True)
                            )
                            found_states += [
                                (weight, state)
                                for state in found.states
                                if state.choices not in choices
                                and all(state.choices != seen.choices for _, seen in found_states)
                            ]
                        # A strongly cost-led search happily repeats a cheap dish; its weeks are tried
                        # only after every week without repeats, then with fewest dishes of one kind.
                        found_states.sort(
                            key=lambda item: (sameness([r for _, r in item[1].choices]), item[0], item[1].loss)
                        )
                        extra = [state.choices for _, state in found_states]
                        trace["cost_fallback"] = {"weights": list(COST_WEIGHTS), "candidates": len(extra)}
                        return [[PlanningAssignment(slot_id=s, recipe_id=r) for s, r in picked] for picked in extra]

                    fallback = cost_fallback
                assignments_list = [
                    [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in picked] for picked in choices
                ]
            else:
                # The search budget grows with the slots, so a three-meal week is searched as
                # fully as a dinner week (ADR-0046 section 3).
                meal_beam = MealBeamPlanner(
                    MealBeamLimits(
                        # 256 meals a slot keep the rotated dishes a 64-meal cut dropped; the budget
                        # covers the beam's 32 states times those meals, slot by slot.
                        meal_options_per_slot=256,
                        max_expansions=max(MealBeamLimits().max_expansions, 32 * 256 * len(slots) + 256),
                        repeat_cost=1.0,
                        flat_repeat=True,
                        max_meal_combinations=16384,
                        distinct_kinds=True,
                        rotate_candidates=True,
                    ),
                    local_losses=losses,
                )
                # The cheapest week is searched by the cost-led search alone (below).
                search = (
                    MealBeamResult((), 0, False, False, ())
                    if cheapest
                    else meal_beam.search_candidates(problem.model_copy(deep=True))
                )
                trace["settings"] = asdict(meal_beam.limits)
                trace["dominance_rule"] = None
                budget = constraints.weekly_budget_sgd
                banded = any(band.hard and band.scope == "per_day" for band in problem.nutrition_bands)

                roles_of = {s.slot_id: len(s.composition or [None]) for s in problem.slots}

                def variety(state) -> tuple[int, int, int, int]:
                    """Sorts the fewest empty optional dishes, then the most distinct dishes, then the fewest
                    times one dish comes, then kinds, first.

                    The owner's order (2026-10-02, amending ADR-0045 for composed weeks): a week with its
                    optional dishes filled comes before one with a dish or two more of variety. Of two weeks
                    as varied, one dish twice and another twice beats one dish three times ("菜很单调")."""
                    dishes = [recipe for _, meal in state.choices for _, recipe in meal]
                    repeats, same_kind = sameness(dishes)
                    most = max(Counter(dishes).values(), default=0)
                    return empty_roles(state, roles_of), repeats - len(dishes), most, same_kind - len(dishes)

                def order(item) -> tuple:
                    """The fullest, then most varied week first (ADR-0045 as amended), then the lighter search, loss."""
                    return variety(item[1]), item[0], item[1].loss, item[1].choices

                def most_varied_first(found) -> list[list[PlanningAssignment]]:
                    return [assignments_of(state) for _, state in sorted(found, key=order)]

                def limit_led() -> list:
                    """Searches that blend what binds into each dish's rank, from lightly to strongly.

                    A hard budget or day band prunes the beam, and what survives is whatever squeezed
                    in, or nothing. A dish's grocery cost (against the budget for one meal) and its
                    distance from the day's per-meal guide steer these searches towards weeks that fit.
                    """
                    cost = (
                        {r.recipe.slug: dish_cost(r) * len(slots) / budget for r in recommendations} if budget else {}
                    )
                    guard = {c.recipe_id: nutrition_guard_loss(problem, c) for c in candidates} if banded else {}
                    seen = {state.choices for state in search.states}
                    extra = []
                    for weight in COST_WEIGHTS:
                        blended = {
                            slug: loss + weight * (cost.get(slug, 0.0) + guard.get(slug, 0.0))
                            for slug, loss in losses.items()
                        }
                        # Under a budget a repeat stays dearer than the cost it saves (ADR-0044); a narrow
                        # day band leaves few dishes that fit, and there repeats are what fits.
                        repeat_cost = meal_beam.limits.repeat_cost + (0.0 if banded else weight)
                        found = MealBeamPlanner(
                            replace(meal_beam.limits, repeat_cost=repeat_cost), local_losses=blended
                        ).search_candidates(problem.model_copy(deep=True))
                        extra += [(weight, state) for state in found.states if state.choices not in seen]
                        seen |= {state.choices for state in found.states}
                    trace["limit_led"] = {"weights": list(COST_WEIGHTS), "candidates": len(extra)}
                    return extra

                def cheapest_weeks() -> list[list[PlanningAssignment]]:
                    """The cost-led search: the strongest budget-led search, under the least budget it completes.

                    It never reads the household's budget, so what it finds is the same under any budget:
                    a week it finds at S$C is tried again under a budget of S$C or more, which is what makes
                    a budget offered as "S$C" one that plans. The cheapest week a search found, not a proof
                    that none is cheaper.
                    """
                    cost = {r.recipe.slug: dish_cost(r) for r in recommendations}
                    weight = COST_WEIGHTS[-1]
                    led = replace(
                        meal_beam.limits,
                        repeat_cost=meal_beam.limits.repeat_cost + weight,
                        meal_options_per_slot=CHEAPEST_MEAL_OPTIONS,
                    )

                    def within(limit: int) -> tuple:
                        share = len(slots) / limit
                        blended = {slug: loss + weight * cost.get(slug, 0.0) * share for slug, loss in losses.items()}
                        bounded = problem.model_copy(deep=True, update={"purchase_budget_sgd": float(limit)})
                        return MealBeamPlanner(led, local_losses=blended).search_candidates(bounded).states

                    def bought(state) -> float:
                        """What the week buys in whole packages, as the validator totals it."""
                        return sum(
                            row.purchase_cost_sgd for row in builder._build_shopping(problem, assignments_of(state))
                        )

                    # Up from a first guess until a week completes, then halve the gap between the last budget
                    # that completed none and the cheapest week found so far: whole dollars, to within
                    # CHEAPEST_PRECISION. Every week found is kept, so the cheapest of any probe is tried.
                    kept: dict = {}
                    low, limit = 0, CHEAPEST_START_SGD
                    states = within(limit)
                    while not states and limit < 7000:
                        low, limit = limit, min(7000, limit * 4)
                        states = within(limit)
                    high = limit
                    while states:
                        kept.update((state.choices, state) for state in states)
                        high = min(limit, ceil(min(map(bought, states))))
                        states = ()
                        while not states and high - low > max(1, high * CHEAPEST_PRECISION):
                            limit = (low + high) // 2
                            states = within(limit)
                            low = low if states else limit
                    trace["cheapest_search"] = {"budget_sgd": high, "candidates": len(kept)}
                    return most_varied_first([(weight, state) for state in kept.values()])

                found = [(0.0, state) for state in search.states]
                full_and_repeat_free = any(
                    variety(state)[0] == 0 and sameness([r for _, meal in state.choices for _, r in meal]) == (0, 0)
                    for state in search.states
                )
                if budget is not None and (not full_and_repeat_free or not budget_is_hard):
                    # A budget-pruned search keeps the cheap repeats or leaves optional dishes out; the first
                    # week in that order within the budget may come from a cost-led search, so all are tried.
                    # Over the budget anyway, the cost-led searches hold the cheapest weeks.
                    found += limit_led()
                    # A search keeps partial weeks and cannot see the room a finished one leaves: unless a week
                    # found is filled with no dish twice, the most varied weeks found and the cheapest spend theirs
                    # on dishes not yet in the week.
                    seen = {state.choices for _, state in found}
                    cheapest_starts = sorted(found, key=lambda item: (item[1].cost, item[1].choices))
                    starts = sorted(found, key=order)[:VARIED_STARTS] + cheapest_starts[:VARIED_STARTS]
                    if any(variety(state)[0] == 0 and variety(state)[2] <= 1 for _, state in found):
                        starts = []
                    for weight, state in starts:
                        varied = meal_beam.vary_within_budget(problem, state)
                        if varied.choices not in seen:
                            seen.add(varied.choices)
                            found.append((weight, varied))
                elif banded:
                    fallback = lambda: most_varied_first(limit_led())  # noqa: E731
                assignments_list = most_varied_first(found)
                if cheapest:
                    assignments_list, fallback, last_resort = [], None, cheapest_weeks
                elif (
                    cheapest_last
                    and budget is not None
                    and max(len(roles) for _, roles in composition) <= QUICK_MEAL_DISHES
                ):
                    # Every week above failed: the cheapest week the search can find, if it is within budget.
                    last_resort = cheapest_weeks
            trace["search"] = {k: v for k, v in asdict(search).items() if k != "states"}
            trace["search"]["completed_candidates"] = len(search.states)
        result = None
        passed = []  # with the budget only reported: every week that holds the rest, to compare
        uncertain = bool(diagnostics)
        only_budget_failures = bool(assignments_list)
        # The validator only reads the problem, so one copy serves every week it checks (over the budget it
        # checks them all, and a copy each took about a second of a whole-week change); the builder it checks
        # still gets its own each time, so a builder that changed the problem could not change the check.
        checked = problem.model_copy(deep=True)
        index, cheapest_from = 0, None
        while True:
            if index == len(assignments_list):
                if fallback is not None:
                    assignments_list.extend(fallback())
                    fallback = None
                elif last_resort is not None:
                    cheapest_from = index
                    assignments_list.extend(last_resort())
                    last_resort = None
                else:
                    break
                continue
            assignments = assignments_list[index]
            index += 1
            shopping = builder._build_shopping(
                problem.model_copy(deep=True), [a.model_copy(deep=True) for a in assignments]
            )
            report = self.validator.validate(checked, assignments, shopping)
            if constraints.budget_per_meal_sgd is not None:
                extra = per_meal_budget_checks(problem, assignments, constraints.budget_per_meal_sgd)
                report.checks.extend(extra)
                report.hard_failure_count += sum(c.status == "failed" for c in extra)
                report.indeterminate_count += sum(c.status == "indeterminate" for c in extra)
                report.status = (
                    "failed"
                    if report.hard_failure_count
                    else "indeterminate"
                    if report.indeterminate_count
                    else "passed"
                )
            # Operations may expose verdicts, but never plaintext health inputs.
            redacted = report.model_dump(mode="json", exclude={"checks"})
            redacted["checks"] = [
                {"code": c.code, "status": c.status, "hard": c.hard, "scope_id": c.scope_id} for c in report.checks
            ]
            if cheapest_from is not None:
                # A week of the cheapest-week search: its total is a budget that plans it (agent/limits.py).
                redacted["cheapest_search"] = True
            trace["validation"] = redacted
            trace["validation_attempts"].append(redacted)
            uncertain |= report.status == "indeterminate"
            failed_codes = {c.code for c in report.checks if c.hard and c.status == "failed"}
            only_budget_failures &= bool(failed_codes) and failed_codes <= {"purchase_budget", "per_meal_budget"}
            if report.status == "passed":
                if budget_is_hard:
                    if not cheapest:
                        result = (assignments, shopping, report)
                        break
                    if result is None or report.purchase_total_sgd < result[2].purchase_total_sgd:
                        result = (assignments, shopping, report)
                else:
                    passed.append((assignments, shopping, report))
        if passed:
            result = over_budget_pick(passed, problem.slots, constraints.weekly_budget_sgd)
        if result is None:
            evidence = "needs_data" if uncertain else "bounded_search_exhausted"
            status = "needs_data" if uncertain else "candidate_rejected"
            if (
                not uncertain
                and only_budget_failures
                and constraints.planner_strategy == "beam"
                and composition is None  # the meal beam keeps only the best dishes per role
                and not search.pruned
                and not search.exhausted
            ):
                evidence, status = "exhaustively_infeasible", "infeasible"
            if compiled is not None and compiled.blocked_slot_ids:
                if set(problem.allergens) - set(problem.allergen_vocabulary):
                    evidence, status = "needs_data", "needs_data"
                else:
                    evidence, status = "exactly_infeasible", "infeasible"
            trace.update(status=status, evidence=evidence)
            totals = [attempt["purchase_total_sgd"] for attempt in trace["validation_attempts"]]
            if status == "needs_data":
                message = "Some recipe or price details are missing. Try again in a moment."
            elif only_budget_failures and totals and constraints.weekly_budget_sgd is not None:
                message = (
                    f"I couldn't fit seven dinners into S${constraints.weekly_budget_sgd:.2f}. The cheapest week "
                    f"I found costs S${min(totals):.2f}. Try a higher budget or fewer limits."
                )
            elif trace.get("search", {}).get("exhausted"):
                # A search that ran out of steps proves nothing about the limits themselves.
                message = "Planning took longer than it should this time. Please try again."
            else:
                message = "I couldn't find a week that meets every limit. Try relaxing one of them."
            raise ProductPlanningError(status, message, trace, problem=problem.model_copy(deep=True))
        assignments, shopping, report = result
        lines = []
        for row in shopping:
            product = observations.get(row.selected_product_id)
            consumed = (row.remaining_quantity * product.price_sgd / product.package_size) if product else 0.0
            lines.append(
                GroceryLineEstimate(
                    ingredient_name=row.ingredient_id,
                    ingredient_display_name=display_names[row.ingredient_id],
                    required_quantity=row.required_quantity,
                    unit=row.unit,
                    pantry_deduction=row.pantry_deduction,
                    remaining_quantity=row.remaining_quantity,
                    product=product,
                    match_score=None,
                    packages_required=row.packages,
                    purchase_cost_sgd=row.purchase_cost_sgd,
                    consumed_cost_sgd=round(consumed, 2),
                    excess_quantity=row.surplus_quantity,
                    note=row.note,
                    evidence=provenance.get(row.selected_product_id),
                )
            )
        budget_check = next((c for c in report.checks if c.code == "purchase_budget"), None)
        grocery = WeeklyGroceryEstimateResponse(
            pricing_mode=constraints.pricing_mode,
            complete=True,
            purchase_total_sgd=report.purchase_total_sgd,
            consumed_total_sgd=round(sum(line.consumed_cost_sgd for line in lines), 2),
            weekly_budget_sgd=constraints.weekly_budget_sgd,
            # A week planned over its budget (budget_is_hard=False) says so.
            within_weekly_budget=budget_check.status == "passed" if budget_check else None,
            items=lines,
            unmapped_ingredients=[],
            warnings=list(
                dict.fromkeys(
                    warning for r in recommendations if r.grocery_estimate for warning in r.grocery_estimate.warnings
                )
            ),
        )
        trace.update(status="feasible", evidence="validated", assignments=[a.model_dump() for a in assignments])
        trace["shopping_digest"] = digest([row.model_dump(mode="json") for row in shopping])
        by_slug = {r.recipe.slug: r for r in recommendations}
        selected = [
            by_slug[a.recipe_id].model_copy(deep=True, update={"recipe": recipe_snapshots[a.recipe_id]})
            for a in assignments
        ]
        servings = dish_servings(problem, assignments)
        placements = [
            (*slot_day[a.slot_id], a.role_id or "main", servings[i] / constraints.household_size)
            for i, a in enumerate(assignments)
        ]
        return ProductPlan(selected, grocery, trace, placements)


def over_budget_pick(passed, slots, budget):
    """The week offered over the budget, of `passed` (weeks holding every other rule, in the order the
    in-budget path tries them: fewest empty optional dishes, then most distinct dishes, first; ADR-0052).

    The price is the cheapest week's, a repeat charged one meal's share of the budget and an empty optional
    dish twice that, as the meal beam's cheap room charges them (ADR-0044, ADR-0050). The week is the one the
    in-budget path would choose were its budget that price, so going over never offers a week emptier or
    more repetitive than one that costs no more.
    """
    share = (budget or 0) / len(slots)

    def charged(item) -> float:
        assignments, _, report = item
        filled = Counter(a.slot_id for a in assignments)
        dishes = [a.recipe_id for a in assignments]
        empty = sum(len(slot.composition or [None]) - filled[slot.slot_id] for slot in slots)
        return report.purchase_total_sgd + share * (len(dishes) - len(set(dishes)) + EMPTY_OPTIONAL_ROLE_LOSS * empty)

    price = min(passed, key=charged)[2].purchase_total_sgd
    return next(item for item in passed if item[2].purchase_total_sgd <= price)


def per_meal_budget_checks(problem, assignments, budget):
    """Recompute the legacy per-meal ingredient-use ceiling from source quantities.

    Pantry is excluded, matching recommendation admission. The horizon budget
    separately checks whole-package checkout cost in FinalPlanningValidator.
    """
    recipes = {r.recipe_id: r for r in problem.recipes}
    slots = {s.slot_id: s for s in problem.slots}
    servings = dish_servings(problem, assignments)
    # A meal's dishes share one ceiling, reported once per slot in first-dish order.
    meals: dict[str, list[tuple[int, int] | None]] = {}
    for index, assignment in enumerate(assignments):
        recipe, slot = recipes.get(assignment.recipe_id), slots.get(assignment.slot_id)
        if recipe is None or slot is None or index not in servings:
            continue  # The core validator reports the invalid assignment.
        total_cents, missing = 0, False
        for item in recipe.ingredients:
            products = [
                p
                for p in problem.products
                if p.available and p.ingredient_id == item.ingredient_id and p.package_unit == item.unit
            ]
            if item.quantity is None or not products:
                missing = True
                continue
            demand = Fraction(str(item.quantity)) * servings[index] / recipe.servings
            total_cents += min(
                round(demand * Fraction(str(p.price_sgd)) * 100 / Fraction(str(p.package_quantity))) for p in products
            )
        meals.setdefault(assignment.slot_id, []).append((total_cents, missing))
    checks = []
    for slot_id, dishes in meals.items():
        missing = any(dish_missing for _, dish_missing in dishes)
        total_cents = sum(cents for cents, _ in dishes)
        status = "indeterminate" if missing else "passed" if total_cents <= Fraction(str(budget)) * 100 else "failed"
        checks.append(
            PlanningConstraintCheck(
                code="per_meal_budget",
                status=status,
                scope_id=slot_id,
                detail="Recomputed ingredient-use cost without pantry deduction.",
            )
        )
    return checks
