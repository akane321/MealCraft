"""Product boundary for the fixed-product Planning v2 path.

This adapter consumes recorded recommendation observations. It never retrieves
prices after validation, and never promotes a bounded miss into a global proof.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from fractions import Fraction
from math import isfinite

from app.data.allergens import checked_allergens
from app.data.ingredient_hierarchy import expand_exclusions
from app.data.units import UNIT_BASE
from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.capability import PlanningCapabilityError, require_composition_enabled
from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.grocery_estimator import not_purchased
from app.planning.meal_beam import MealBeamPlanner, assignments_of
from app.planning.meal_composition import dish_servings
from app.planning.nutrition_scope import compile_nutrition_targets
from app.planning.product_input import product_input
from app.planning.recipe_input import recipe_input
from app.planning.recommendation_engine import CANDIDATE_LIMIT
from app.planning.weekly_planner import WeeklyPlanSelectionError, WeeklyPlanSelector
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningConstraintCheck,
    PlanningNutritionBand,
    PlanningPantryItem,
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

    def plan(self, constraints, recommendations, recipes, *, selector=None, profile_version=None):
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
        composition = getattr(constraints, "meal_composition", None)
        try:
            require_composition_enabled(composition)
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
            recommendations = list(recommendations)[: self._packet_limit(constraints.day_count)]
        else:
            # The meal beam ranks each role's dishes itself; keep the best of every course it may fill.
            courses = {course for role in composition for course in role.courses}
            by_id = {r.id: r for r in recipes}
            kept: dict[str, int] = {}
            packet = []
            for recommendation in recommendations:
                course = getattr(by_id.get(recommendation.recipe.id), "course", None) or "main"
                if course in courses and kept.get(course, 0) < COMPOSED_CANDIDATES_PER_COURSE:
                    kept[course] = kept.get(course, 0) + 1
                    packet.append(recommendation)
            recommendations = packet
            trace["candidate_limit"] = COMPOSED_CANDIDATES_PER_COURSE
        if not recommendations:
            trace.update(status="candidate_rejected", evidence="bounded_search_exhausted")
            raise ProductPlanningError(
                "candidate_rejected", "No candidate plan was found; try a different recipe selection.", trace
            )
        by_id = {r.id: r for r in recipes}
        candidates, options, observations, display_names = [], {}, {}, {}
        recipe_snapshots = {}
        diagnostics = []
        for recommendation in sorted(recommendations, key=lambda r: r.recipe.slug):
            if recommendation.recipe.id not in by_id:
                diagnostics.append("recipe_snapshot_missing")
                continue
            source = RecipeService._to_detail(by_id[recommendation.recipe.id])
            recipe_snapshots[source.slug] = RecipeListItemResponse.model_validate(source.model_dump())
            # Tap water and ice are never bought, so they are not shopping requirements.
            source.ingredients = [item for item in source.ingredients if not not_purchased(item.normalized_name)]
            for ingredient in source.ingredients:
                display_names[ingredient.normalized_name] = ingredient.name
                ingredient.quantity, ingredient.unit = normalized(ingredient.quantity, ingredient.unit)
            # A release recipe states its meal types (ADR-0038); a curated one's
            # meal_type may name one; otherwise it is a lunch or dinner dish.
            stated = tuple(m for m in source.meal_types or () if m in MEAL_TYPES)
            affinity = stated or ((source.meal_type,) if source.meal_type in MEAL_TYPES else ("lunch", "dinner"))
            converted = recipe_input(source, allowed_meal_types=affinity, nutrition_basis="per_serving")
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
        trace["input_issues"] = sorted(set(diagnostics))
        trace["observed_sources"] = sorted({p.source for p in observations.values()})
        if not candidates or "conflicting_product_observation" in diagnostics:
            raise ProductPlanningError(
                "needs_data", "Recipe or price details could not be verified; refresh them and try again.", trace
            )
        slots = [
            PlanningSlot(
                slot_id=f"slot-{i}",
                planned_date=constraints.start_date + timedelta(days=i),
                meal_type="dinner",
                servings=constraints.household_size,
                max_time_minutes=constraints.max_cooking_time_minutes,
                composition=composition,
            )
            for i in range(constraints.day_count)
        ]
        pantry = []
        for item in constraints.available_ingredients:
            quantity, unit = normalized(item.quantity, item.unit)
            pantry.append(PlanningPantryItem(ingredient_id=item.normalized_name, quantity=quantity, unit=unit))
        bands = compile_nutrition_targets(constraints.nutrition_constraints, constraints.nutrition_guard_band)
        trace["nutrition_scope"] = [b.model_dump(exclude={"lower", "upper"}) for b in bands]
        trace["settings"]["nutrition_guard_band"] = constraints.nutrition_guard_band
        if constraints.max_sodium_mg_per_meal is not None:
            bands.append(
                PlanningNutritionBand(metric="sodium_mg", scope="per_slot", upper=constraints.max_sodium_mg_per_meal)
            )
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
            if composition is None:
                search = BeamPlanner(self.limits, local_losses=losses).search_candidates(problem.model_copy(deep=True))
                assignments_list = [
                    [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in state.choices]
                    for state in sorted(search.states, key=lambda s: (s.loss, s.choices))
                ]
            else:
                meal_beam = MealBeamPlanner(local_losses=losses)
                search = meal_beam.search_candidates(problem.model_copy(deep=True))
                trace["settings"] = asdict(meal_beam.limits)
                trace["dominance_rule"] = None
                assignments_list = [
                    assignments_of(state) for state in sorted(search.states, key=lambda s: (s.loss, s.choices))
                ]
            trace["search"] = {k: v for k, v in asdict(search).items() if k != "states"}
            trace["search"]["completed_candidates"] = len(search.states)
        result = None
        uncertain = bool(diagnostics)
        only_budget_failures = bool(assignments_list)
        for assignments in assignments_list:
            shopping = builder._build_shopping(
                problem.model_copy(deep=True), [a.model_copy(deep=True) for a in assignments]
            )
            report = self.validator.validate(problem.model_copy(deep=True), assignments, shopping)
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
            trace["validation"] = redacted
            trace["validation_attempts"].append(redacted)
            uncertain |= report.status == "indeterminate"
            failed_codes = {c.code for c in report.checks if c.hard and c.status == "failed"}
            only_budget_failures &= bool(failed_codes) and failed_codes <= {"purchase_budget", "per_meal_budget"}
            if report.status == "passed":
                result = (assignments, shopping, report)
                break
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
            message = (
                "Some required details are missing; refresh the recipe and price data before trying again."
                if status == "needs_data"
                else "No validated plan was found in this search; try another candidate selection."
            )
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
                )
            )
        grocery = WeeklyGroceryEstimateResponse(
            pricing_mode=constraints.pricing_mode,
            complete=True,
            purchase_total_sgd=report.purchase_total_sgd,
            consumed_total_sgd=round(sum(line.consumed_cost_sgd for line in lines), 2),
            weekly_budget_sgd=constraints.weekly_budget_sgd,
            within_weekly_budget=True if constraints.weekly_budget_sgd is not None else None,
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
        slot_index = {slot.slot_id: index for index, slot in enumerate(slots)}
        placements = [
            (slot_index[a.slot_id], "dinner", a.role_id or "main", servings[i] / constraints.household_size)
            for i, a in enumerate(assignments)
        ]
        return ProductPlan(selected, grocery, trace, placements)


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
