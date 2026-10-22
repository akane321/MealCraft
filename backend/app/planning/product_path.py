"""Product boundary for the fixed-product Planning v2 path.

This adapter consumes recorded recommendation observations. It never retrieves
prices after validation, and never promotes a bounded miss into a global proof.
"""

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from fractions import Fraction
from math import ceil, floor, isfinite
from typing import get_args

from app.data import meal_structure
from app.data.allergens import checked_allergens
from app.data.household_reference import hpb
from app.data.ingredient_hierarchy import expand_exclusions
from app.data.units import UNIT_BASE, in_grams, weighed
from app.planning import alternatives
from app.planning.beam_planner import BeamLimits, BeamPlanner
from app.planning.capability import PlanningCapabilityError, require_composition_enabled
from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.grocery_estimator import convert_quantity, not_purchased
from app.planning.household_slots import (
    assumed_basics,
    basics_note,
    limit_targets,
    slot_members,
    slot_people,
    slot_servings,
    slot_time_limit,
)
from app.planning.meal_beam import (
    EMPTY_OPTIONAL_ROLE_LOSS,
    MealBeamLimits,
    MealBeamPlanner,
    MealBeamResult,
    assignments_of,
    dish_eligible,
    empty_roles,
    staple_slots,
)
from app.planning.meal_composition import (
    dish_portions,
    dish_servings,
    fills_staple,
    meal_role_of,
    role_base,
    structured_slot,
    unreviewed,
)
from app.planning.member_coverage import (
    STAPLE_ROLE,
    catalog_can_eat,
    covering_groups,
    member_can_eat,
    member_limits,
)
from app.planning.nutrition_scope import compile_nutrition_targets, nutrition_guard_loss
from app.planning.product_input import product_input
from app.planning.recipe_input import recipe_input
from app.planning.recipe_quality import dish_family, dish_kind
from app.planning.recommendation_engine import CANDIDATE_LIMIT
from app.planning.vegetable_led import catalog_vegetable_led, vegetable_role
from app.planning.weekly_planner import WeeklyPlanSelectionError, WeeklyPlanSelector
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse
from app.schemas.planning_v2 import (
    DishCourse,
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningCompositionPolicy,
    PlanningConstraintCheck,
    PlanningNutritionBand,
    PlanningPantryItem,
    PlanningRecipeCount,
    PlanningRepetitionRules,
    PlanningSlot,
    structured,
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


# Fallback searches for a stated budget: how strongly a dish's cost, relative to the budget for
# one meal, is added to its rank loss (which lies in 0..1). One dish a dinner also weighs it against
# the packet's cheapest dish (ONE_DISH_COST_WEIGHTS).
COST_WEIGHTS = (1.0, 4.0, 16.0)
# One dish a dinner searches once more, with cost all but deciding: against its cheapest dish, x16 at most left
# the fixture catalog's 2-person week offering S$43.25 at every refused budget where a S$31.70 week plans (main's
# budget-scaled weights found it at budgets up to S$10); x64 finds it, and x256 or x1000 find none cheaper.
ONE_DISH_COST_WEIGHTS = (*COST_WEIGHTS, 64.0)
# The cheapest-week search (see `plan`): the first budget it tries. It searches with the ranked search's own meal
# options and bisects to the whole dollar, the unit a budget is offered in, so the least budget it completes a week
# within is exact to that dollar for the weeks it generates (owner, 2026-10-22; ADR-0080). Its earlier lighter beam
# (64 meals a slot) and 5% stop saved time only. Bisecting under the cheapest week found so far rather than under
# the budget it was found within takes fewer probes for the same week (PR #211 round 1).
CHEAPEST_START_SGD = 64
# Search breadth of a meal (`MealBeamLimits.max_meal_combinations`): the most dish combinations its first widening
# step builds, which sets how many dishes each of its roles keeps. A parameter of the search, set by plan quality: the
# smallest value at which no developer-set plan gets worse than at 16,384 (owner, 2026-10-22; ADR-0083;
# docs/evaluation/combination-cap-sweep). Removing it planned no better and took up to hours (task 15).
MEAL_COMBINATIONS = 16384
# A week of this many dish positions or more (and no locked dishes) is "heavy": its variety pass stops early at a
# week no later start can make more varied (`is_best`). No pass is cut by the clock: planning time has no hard
# limit and a slow plan never trades quality for speed (owner, 2026-10-21; ADR-0080).
HEAVY_COMPOSITION_DISH_POSITIONS = 35


def _vary_starts(meal_beam, problem, starts, seen, *, is_best):
    """Try every ordered variety start, or until one varies into a week `is_best` says none can beat."""
    added = []
    for weight, state in starts:
        varied = meal_beam.vary_within_budget(problem, state)
        if varied.choices not in seen:
            seen.add(varied.choices)
            added.append((weight, varied))
        if is_best(varied):
            break
    return added


def meals_of_the_day(constraints) -> list[tuple[str, list]] | None:
    """(meal type, dish roles) for each planned meal of a day, in day order; None for the one-dish dinner MVP.

    A plan shape (ADR-0046) names the meals; an older dinner composition (ADR-0036) is a dinner-only shape.
    """
    shape = getattr(constraints, "plan_shape", None)
    if shape is not None:
        return shape.ordered()
    composition = getattr(constraints, "meal_composition", None)
    return [("dinner", composition)] if composition is not None else None


def uncoverable_members(problem) -> list[str]:
    """Members no meal of the frozen candidates can cover, by name (ADR-0071 section 1)."""
    return [name for names in uncoverable_by_rule(problem).values() for name in names]


def uncoverable_by_rule(problem) -> dict[str, list[str]]:
    """Members no meal of the frozen candidates can cover, under `"core"` and under `"any"`.

    For each structured lunch or dinner and each member home for it: is there a filling core at all among the
    dishes eligible for that slot which the member can eat - a dish that carries its staple, or a protein main
    beside a staple. That is `"core"`. Every other meal is held to the weakest form instead, `"any"`: is there
    any eligible dish at all that member can eat. Keeping them apart lets the refusal say what the meal could
    not give, because a breakfast was never owed a main and a staple. It proves a member uncoverable; it does
    not prove the rest coverable together.
    """
    by_rule: dict[str, list[str]] = {"core": [], "any": []}
    for slot in problem.slots:
        if not slot.members:
            continue
        if not structured_slot(slot) or slot.meal_type not in ("lunch", "dinner"):
            eligible = [recipe for recipe in problem.recipes if dish_eligible(problem, slot, recipe)]
            for member in slot.members:
                if not any(member_can_eat(member, recipe) for recipe in eligible):
                    if member.name not in by_rule["any"]:
                        by_rule["any"].append(member.name)
            continue
        names = by_rule["core"]
        roles = slot.composition or []
        if not any(role.role_id == STAPLE_ROLE for role in roles):
            continue
        eligible = [recipe for recipe in problem.recipes if dish_eligible(problem, slot, recipe)]
        mains = [
            r
            for r in eligible
            if any(meal_role_of(r) in (role.meal_roles or ()) for role in roles if role_base(role.role_id) == "main")
        ]
        staples = [r for r in eligible if meal_role_of(r) == STAPLE_ROLE]
        for member in slot.members:
            mine = [r for r in mains if member_can_eat(member, r)]
            covered = any(fills_staple(r) for r in mine) or (
                any(member_can_eat(member, r) for r in staples) and any(meal_role_of(r) == "protein_main" for r in mine)
            )
            if not covered and member.name not in names:
                names.append(member.name)
    # A member both rules name is reported once, by the stronger one.
    by_rule["any"] = [name for name in by_rule["any"] if name not in by_rule["core"]]
    return by_rule


def names_in_words(names: list[str]) -> str:
    """ "Ann", "Ann and Ben", "Ann, Ben and Kai"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def uncovered_message(by_rule: dict[str, list[str]]) -> str:
    """The refusal for members no meal can cover (`uncoverable_by_rule`), in the household's words.

    Every member needs a plate of their own (ADR-0071 section 1), which ADR-0068 keeps outside idealization: the plan
    is refused rather than leaving someone uncovered. What the meal could not give differs by meal, so a member named
    under `"any"` (a breakfast, a one-dish meal) is not promised a main dish and a staple, which those meals were never
    owed.
    """
    parts = []
    core, other = by_rule["core"], by_rule["any"]
    if core:
        they = "they" if len(core) > 1 else core[0]
        parts.append(
            f"I couldn't give {names_in_words(core)} a main dish and a staple at every lunch and dinner with what "
            f"{they} can eat."
        )
    if other:
        parts.append(f"At one of the other meals there was nothing {names_in_words(other)} can eat at all.")
    parts.append(
        "Try a higher budget, more cooking time or fewer dishes a meal; no allergen, diet or excluded ingredient "
        "will be relaxed."
    )
    return " ".join(parts)


def pool_courses(meals) -> list[str] | None:
    """The courses the recipe pool loads for a plan's meals (None: mains and soups, the one-dish dinner). A meal of
    meal roles loads every dish course: a staple may be a side or a baked good, a vegetable dish a main."""
    if not meals:
        return None
    courses = {course for _, roles in meals for role in roles for course in role.courses}
    if any(structured(roles) for _, roles in meals):
        courses |= set(get_args(DishCourse))
    return sorted(courses)


def pool_for(meals, recipes) -> list:
    """The pool's recipes a plan's meals can take: for meals of meal roles, only those a role's tags admit."""
    if not meals or not any(structured(roles) for _, roles in meals):
        return recipes
    tags = {tag for _, roles in meals if structured(roles) for role in roles for tag in role.meal_roles}
    courses = {course for _, roles in meals if not structured(roles) for role in roles for course in role.courses}
    return [
        recipe
        for recipe in recipes
        if meal_role_of(recipe) in tags or (courses and (recipe.course is None or recipe.course in courses))
    ]


def people_at(servings) -> int:
    """How many people a household size counts as for its dish count (ADR-0070 table), halves rounded up. A
    household of members counts the members present instead (`slot_people`)."""
    return max(1, floor(float(servings) + 0.5))


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
    # One per selected recommendation: (slot index, meal type, role, portion share, servings cooked). Servings
    # are None without a household block: the household size at the portion share, as before.
    placements: list[tuple[int, str, str, Fraction, Fraction | None]] | None = None


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


# Dishes of each kind the packet adds for every group of alike members (`_packet_covering`), beside the ranking's
# own picks, whether or not those already hold one that suits the group. Four was too few: a member whose diet is
# narrow had four cores for a whole week. Added only when the ranking kept none, a group with one suitable dish in
# the ranking's picks had that one dish all week (task 14: `two-one-vegetarian` repeated two dishes eight times).
#
# Layer 08 PR-4 kept the top-up conditional because topping up always refused `mixed-diets` at 6 and at 40. That
# refusal was never the packet's: `meal_beam.meal_options` widened each role to four times its usual dishes and
# then gave up, so one lunch had no meal at all although eligible dishes were left. The meal beam now tries every
# eligible dish, up to `LAST_STEP_COMBINATIONS` combinations, before it calls a meal empty (`MEAL_OPTION_WIDENING`),
# and every setting plans; the measurements are in the task 14 record.
PACKET_COVERAGE_CANDIDATES = 40


def composed_packet(
    composition, day_count: int, budget, recommendations, recipes, *, keep=(), members=(), cooked=None
) -> tuple[list, dict[str, int]]:
    """The recommendations a composed week is planned from, and how many each kind of dish keeps.

    The meal beam ranks each role's dishes itself; keep the best of every course it may fill, enough of each
    for every slot that uses it to get a different dish (a lunch-and-dinner week needs fourteen mains, not the
    24 a dinner week kept).

    `members` are the household's own limits (ADR-0071 section 1): each kind also keeps a few dishes each member
    can eat, and a few every member can, because a packet chosen by rank alone can hold no dish at all that
    suits one member, and then no meal covers that member however the search combines what it was given.
    `cooked(recipe)` gives a recipe's lines as the household cooks them (`_packet_covering`).
    """
    uses: dict[str, int] = {}
    for _, roles in composition:
        for role in roles:
            # A role of meal roles keeps dishes by their tag ("role:staple"), one of courses by its course.
            tags = getattr(role, "meal_roles", None)
            for kind in [f"role:{tag}" for tag in tags] if tags else role.courses:
                # The vegetable role keeps the best vegetable-led dishes, which the best sides are not.
                key = f"vegetable {kind}" if vegetable_role(role.role_id) else kind
                uses[key] = uses.get(key, 0) + day_count
    limits = {key: max(COMPOSED_CANDIDATES_PER_COURSE, 3 * count) for key, count in uses.items()}
    if "role:staple" in limits:
        # Rice by default repeats by design (ADR-0070): a few staples of each kind, not three a meal.
        limits["role:staple"] = meal_structure.meal_structure()["staple_candidates"]
    by_id = {r.id: r for r in recipes}
    ranked_by_key: dict[str, list] = {}
    for recommendation in recommendations:
        recipe = by_id.get(recommendation.recipe.id)
        course = getattr(recipe, "course", None) or "main"
        tag = f"role:{meal_role_of(recipe)}"
        for key in (course, f"vegetable {course}", tag, f"vegetable {tag}"):
            led = key.startswith("vegetable ")
            if key in limits and (not led or (recipe is not None and catalog_vegetable_led(recipe))):
                ranked_by_key.setdefault(key, []).append(recommendation)
    chosen: set[int] = set()
    for key, ranked in ranked_by_key.items():
        if key == "role:staple":
            chosen |= {r.recipe.id for r in staple_packet(ranked, limits[key])}
            continue
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
        chosen |= {r.recipe.id for r in _packet_covering(ranked, best, members, by_id, limits[key], cooked)}
    return [r for r in recommendations if r.recipe.id in chosen or (keep and r.recipe.slug in keep)], limits


def _packet_covering(ranked: list, best: list, members, by_id: dict, limit: int, cooked=None) -> list:
    """Recommendations added to one kind of dish so every member a meal has to cover has a real choice of it
    (ADR-0071 section 1).

    Every group gets up to `PACKET_COVERAGE_CANDIDATES` more of them that suit it, or as many as the ranking keeps
    for the table where that is more, after the ranking's own picks. A group the ranking keeps one suitable dish for
    still gets them: one dish is no choice, and a week planned from it repeats it at every meal of that member.

    `cooked(recipe)` gives a recipe's lines as this household cooks them (`alternatives.lines`), so an "A or B" line
    is judged by the option that reaches the table; None reads the recipe's own lines.

    Empty without members and for a household whose members are all alike, so a packet that is not a
    shared-dish household's is exactly the packet it was before.
    """
    groups = covering_groups(members)
    if not groups:
        return []
    want = max(limit, PACKET_COVERAGE_CANDIDATES)
    lines = {}

    def eats(member, recipe) -> bool:
        if cooked is not None and recipe.id not in lines:
            lines[recipe.id] = cooked(recipe)
        return catalog_can_eat(member, recipe, lines.get(recipe.id))

    added: list = []
    for group in groups:

        def suits(recommendation, group=group) -> bool:
            recipe = by_id.get(recommendation.recipe.id)
            return recipe is not None and all(eats(member, recipe) for member in group)

        more = [r for r in ranked if r not in best and r not in added and suits(r)]
        added += more[:want]
    return added


def staple_packet(ranked, limit: int) -> list:
    """The staples a week is planned from: the best few plain staples of each kind (rice, noodles, flatbread ...,
    data/planning/meal-structure-v1.json `staple_defaults`), then the best of the rest."""
    per_kind = meal_structure.meal_structure()["staple_candidates_per_kind"]
    taken: Counter = Counter()
    first = []
    for recommendation in ranked:
        kind = meal_structure.plain_staple_kind(recommendation.recipe.slug)
        if kind is not None and taken[kind] < per_kind:
            taken[kind] += 1
            first.append(recommendation)
    rest = [r for r in ranked if r not in first]
    return (first + rest)[:limit]


class ProductPlanningEngine:
    def __init__(self, *, overrides=None, validator=None):
        # Search limits a caller sets ({"width": 2}: a Debugging replay) bound a composed week's meal beam too; a
        # limit left out keeps the planner's own, which for a composed week grows with its slots.
        self.overrides = overrides or {}
        self.limits = replace(BeamLimits(), **self.overrides)
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
        minimum_distinct_dishes=0,
        cheapest_last=True,
        budget_is_hard=True,
        locked=None,
        used=None,
        dates=None,
        plan_days=None,
        plan_day_count=None,
    ):
        """A validated week, or ProductPlanningError saying why there is none.

        `locked` keeps a meal's present dishes while one is added to it: (day offset, meal) -> {role id:
        recipe slug}. `budget_is_hard=False` plans a change the household may take over the budget (owner,
        2026-10-02): every other rule holds, the budget is only reported, and of the weeks found (cost-led
        searches among them) one costing least at the checkout is chosen (see `over_budget_pick`). `used` (recipe
        slug -> uses) is what the rest of a week already serves when part of it is planned: those uses count
        towards the household's cap on uses. `minimum_distinct_dishes` takes only weeks of at least that many
        different dishes (ADR-0067's four). `dates` are the calendar days planned when they are not consecutive
        (part of a saved week), so a household's weekday rules read the right day; `plan_days` are those days'
        numbers in the saved plan of `plan_day_count` days (1-based), so each meal is bought on its own trip and a
        perishable is counted from that trip.
        """
        locked = locked or {}
        kept_dishes = {slug for roles in locked.values() for slug in roles.values()}
        household = getattr(constraints, "household", None)
        # A limit the household switched on is a hard band of each day, pro-rated to the meals planned.
        nutrition_targets = [
            *constraints.nutrition_constraints,
            *limit_targets(household, [meal for meal, _ in meals_of_the_day(constraints) or [("dinner", None)]]),
        ]
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
            "policy_version": ("product-scoped-nutrition-v1" if nutrition_targets else "product-fixed-shopping-v1"),
            "validation": None,
        }
        trace["request"] = constraints.model_dump(mode="json")
        # The meals of each day and their dish roles (ADR-0046). None is the MVP: one dish a dinner.
        shape = meals_of_the_day(constraints)
        composition = shape  # kept as the name for "planned with the meal beam" below
        # The household's rules (layer 08) are on with a household block or a structured meal (ADR-0070): only
        # then are the recipes' tags read, perishables kept to their days and equipment checked. Without either the
        # packet, and so every digest and protocol report, is exactly as before.
        any_structured = any(structured(roles) for _, roles in shape or [])
        household_rules = household is not None or any_structured
        plan_day_count = plan_day_count or constraints.day_count
        plan_days = plan_days or list(range(1, constraints.day_count + 1))
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
                cheap_candidates = sorted(ranked[limit // 2 :], key=dish_cost)[: limit - len(best)]
                trace["budget_packet"] = {"ranked": len(best), "cheapest": len(cheap_candidates)}
                ranked = best + cheap_candidates
            recommendations = ranked[:limit]
        else:
            recommendations, limits = composed_packet(
                composition,
                constraints.day_count,
                constraints.weekly_budget_sgd,
                recommendations,
                recipes,
                keep=kept_dishes,
                members=member_limits(household),
                cooked=lambda recipe: alternatives.lines(recipe, constraints),
            )
            trace["candidate_limit"] = limits
        if not recommendations:
            trace.update(status="candidate_rejected", evidence="bounded_search_exhausted")
            raise ProductPlanningError(
                "candidate_rejected", "No candidate plan was found; try a different recipe selection.", trace
            )
        by_id = {r.id: r for r in recipes}
        assumed = assumed_basics(household, constraints.excluded_ingredients)
        basics_used: dict[str, set[str]] = {}  # recipe -> the basics it uses and the week does not buy
        candidates, options, observations, display_names = [], {}, {}, {}
        provenance = {}  # product id -> the PriceEvidence of the observation the planner prices with
        recipe_snapshots = {}
        diagnostics = []
        sources = []
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
            sources.append((recommendation, source))
        # A liquid one dish measures in grams and another in millilitres is bought by weight in every week of
        # this packet, as the weekly list adds it (`weighed`): its millilitres in grams, and no bottle priced by
        # volume, so the search, the checkout and the validator see one line and one product.
        weigh = weighed((item.normalized_name, item.unit) for _, source in sources for item in source.ingredients)
        line_units = defaultdict(set)  # ingredient -> the units the packet's lines of it are in
        for recommendation, source in sources:
            for ingredient in source.ingredients:
                if ingredient.normalized_name in weigh:
                    ingredient.quantity, ingredient.unit = in_grams(
                        ingredient.quantity, ingredient.unit, ingredient.normalized_name
                    )
                line_units[ingredient.normalized_name].add(ingredient.unit)
            converted = recipe_input(source, allowed_meal_types=meal_affinity(source), nutrition_basis="per_serving")
            if converted.candidate is None:
                diagnostics.extend(converted.issues)
                continue
            candidate = converted.candidate
            # Basic seasonings at home are not shopping (ADR-0068): the lines go only after the candidate's
            # allergens were read from every line, and an excluded basic is never assumed (`assumed_basics`).
            bought = [item for item in candidate.ingredients if item.ingredient_id not in assumed]
            if bought and len(bought) < len(candidate.ingredients):
                basics_used[candidate.recipe_id] = {item.ingredient_id for item in candidate.ingredients} - {
                    item.ingredient_id for item in bought
                }
                candidate = candidate.model_copy(update={"ingredients": bought})
            # ponytail: a recipe of basics alone is bought as listed; none is in the catalog's meal courses.
            if composition is not None and candidate.course is None:
                # The curated catalog predates course labels and holds only dinner mains.
                candidate = candidate.model_copy(update={"course": "main"})
            if household_rules:
                candidate = candidate.model_copy(update=recipe_tags(by_id[recommendation.recipe.id], candidate))
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
                if line.ingredient_name in weigh:
                    if product.package_unit == "ml":
                        continue
                    unit = "g"
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
        slots, slot_day, unattended = [], {}, []
        trip_days = meal_structure.trip_days()
        floor_kcal = hpb()["adult_reference"]["energy_kcal"]
        for i in range(constraints.day_count):
            planned_date = dates[i] if dates else constraints.start_date + timedelta(days=i)
            # The plan's day number: its trip (before day 1, and day 8 in a longer plan) and days since it.
            day = plan_days[i] - 1
            trip = 1 + day // trip_days if plan_day_count > trip_days else None
            since_trip = day % trip_days + 1 if household_rules else None
            for meal, roles in composition or [("dinner", None)]:
                # Each meal is cooked for the members home for it (layer 08 presence rules); nobody home, no meal.
                servings = (
                    slot_servings(household, planned_date, meal)
                    if household is not None and household.members is not None
                    else constraints.household_size
                )
                if not servings:
                    unattended.append(f"{planned_date:%A} {meal} is not planned: nobody is home.")
                    continue
                meal_roles, floor_share, kept_roles = roles, None, locked.get((i, meal))
                if structured(roles):
                    # The dinner grows with the people at it (ADR-0070 table); a count the household stated has no
                    # role planned by who is present, so it stays as stated.
                    people = (
                        slot_people(household, planned_date, meal)
                        if household is not None and household.members is not None
                        else people_at(servings)
                    )
                    meal_roles = meal_structure_roles(roles, people)
                    floor_share = meal_structure.energy_floor_share(meal)
                    if kept_roles:
                        kept_roles = {r: d for r, d in kept_roles.items() if r in {x.role_id for x in meal_roles}}
                slot = PlanningSlot(
                    slot_id=f"slot-{i}" if meal == "dinner" else f"slot-{i}-{meal}",
                    planned_date=planned_date,
                    meal_type=meal,
                    servings=servings,
                    max_time_minutes=slot_time_limit(
                        household, constraints.max_cooking_time_minutes, planned_date, meal
                    ),
                    composition=meal_roles,
                    locked_roles=kept_roles,
                    min_energy_kcal=round(floor_share * floor_kcal, 1) if floor_share else None,
                    trip=trip,
                    days_after_shopping=since_trip,
                    # The shared-dish model (ADR-0071 section 1): who is at this meal, and each one's own limits.
                    members=slot_members(household, planned_date, meal, floor_share),
                )
                slots.append(slot)
                slot_day[slot.slot_id] = (i, meal)
        if unattended:
            trace["unattended_slots"] = unattended
        if not slots:
            raise ProductPlanningError("candidate_rejected", "Nobody is home for any planned meal this week.", trace)
        pantry = []
        for item in constraints.available_ingredients:
            quantity, unit = normalized(item.quantity, item.unit)
            # The validator deducts a pantry quantity in its line's unit, so it is held in the unit the packet's
            # lines use: a litre of milk at home covers grams of it, as the weekly list deducts it.
            (wanted, *others) = line_units.get(item.normalized_name) or {unit}
            converted = convert_quantity(quantity, unit, wanted, item.normalized_name) if quantity is not None else None
            if not others and converted is not None:
                quantity, unit = converted, wanted
            pantry.append(PlanningPantryItem(ingredient_id=item.normalized_name, quantity=quantity, unit=unit))
        bands = compile_nutrition_targets(
            nutrition_targets, constraints.nutrition_guard_band, meals_per_day=len(composition or [0])
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
            composition_policy=(
                PlanningCompositionPolicy(
                    structured_shares=meal_structure.portion_shares(),
                    staple_hands_off_cook=meal_structure.meal_structure()["staple_hands_off_cook"],
                )
                if any_structured
                else PlanningCompositionPolicy()
            ),
            missing_equipment=list(household.missing_equipment) if household is not None else [],
            perishable_days=meal_structure.perishable_days() if household_rules else None,
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
                    # grocery cost into its rank, from lightly to strongly. The cost is against the packet's
                    # cheapest dish, not the budget: the weeks they find are the same under any budget, so the
                    # cheapest week a refusal names plans under its cost and no budget plans one cheaper. Against
                    # the budget for one dinner, the fixture catalog's 2-person week was refused at S$16 to S$52
                    # with "cheapest" weeks of S$41.80 to S$55.40, and first planned at S$58.
                    unit = min((c for c in map(dish_cost, recommendations) if c > 0), default=1.0)
                    cost = {r.recipe.slug: dish_cost(r) / unit for r in recommendations}
                    # The budget-led weights are searched too, against the budget for one dinner (here in the same
                    # unit): a roomier budget presses cost less, and the most varied week within it comes first.
                    # Against the cheapest dish alone, the fixture 2-person week at S$60 was one curry four times
                    # (S$46.50) where those weights plan five different dinners (S$55.55). The fixed weights' weeks
                    # are still tried under any budget, so a refusal names at most their cheapest (S$31.70 there).
                    per_slot = budget / constraints.day_count
                    weights = sorted({*(w * unit / per_slot for w in COST_WEIGHTS), *ONE_DISH_COST_WEIGHTS})

                    def cost_fallback() -> list[list[PlanningAssignment]]:
                        found_states: list = []
                        for weight in weights:
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
                        trace["cost_fallback"] = {"weights": [round(w, 4) for w in weights], "candidates": len(extra)}
                        return [[PlanningAssignment(slot_id=s, recipe_id=r) for s, r in picked] for picked in extra]

                    fallback = cost_fallback
                assignments_list = [
                    [PlanningAssignment(slot_id=s, recipe_id=r) for s, r in picked] for picked in choices
                ]
            else:
                # The search budget grows with the slots, so a three-meal week is searched as
                # fully as a dinner week (ADR-0046 section 3).
                meal_limits = MealBeamLimits(
                    # 256 meals a slot keep the rotated dishes a 64-meal cut dropped; the budget
                    # covers the beam's 32 states times those meals, slot by slot.
                    meal_options_per_slot=256,
                    max_expansions=max(MealBeamLimits().max_expansions, 32 * 256 * len(slots) + 256),
                    repeat_cost=1.0,
                    flat_repeat=True,
                    max_meal_combinations=MEAL_COMBINATIONS,
                    distinct_kinds=True,
                    rotate_candidates=True,
                )
                meal_beam = MealBeamPlanner(replace(meal_limits, **self.overrides), local_losses=losses)
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
                staples = staple_slots(problem)
                uncounted = problem.uncounted_roles

                def variety(state) -> tuple[int, int, int, int]:
                    """Sorts the fewest empty optional dishes, then the most distinct dishes, then the fewest
                    times one dish comes, then kinds, first.

                    The owner's order (2026-10-02, amending ADR-0045 for composed weeks): a week with its
                    optional dishes filled comes before one with a dish or two more of variety. Of two weeks
                    as varied, one dish twice and another twice beats one dish three times ("菜很单调")."""
                    # The staple repeats by design (ADR-0070) and counts towards no variety.
                    dishes = [recipe for _, meal in state.choices for role, recipe in meal if role not in uncounted]
                    repeats, same_kind = sameness(dishes)
                    most = max(Counter(dishes).values(), default=0)
                    return empty_roles(state, roles_of, staples), repeats - len(dishes), most, same_kind - len(dishes)

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
                    that none is cheaper. With `minimum_distinct_dishes` only weeks of that many different dishes
                    count, in the probes and the bisection alike (ADR-0067).
                    """
                    cost = {r.recipe.slug: dish_cost(r) for r in recommendations}
                    weight = COST_WEIGHTS[-1]
                    led = replace(meal_beam.limits, repeat_cost=meal_beam.limits.repeat_cost + weight)

                    def within(limit: int) -> tuple:
                        share = len(slots) / limit
                        blended = {slug: loss + weight * cost.get(slug, 0.0) * share for slug, loss in losses.items()}
                        bounded = problem.model_copy(deep=True, update={"purchase_budget_sgd": float(limit)})
                        states = MealBeamPlanner(led, local_losses=blended).search_candidates(bounded).states
                        if minimum_distinct_dishes:
                            states = tuple(
                                state
                                for state in states
                                if len({recipe for _, meal in state.choices for _, recipe in meal})
                                >= minimum_distinct_dishes
                            )
                        return states

                    def bought(state) -> float:
                        """What the week buys in whole packages, as the validator totals it."""
                        return sum(
                            row.purchase_cost_sgd for row in builder._build_shopping(problem, assignments_of(state))
                        )

                    # Up from a first guess until a week completes, then halve the gap between the last budget
                    # that completed none and the cheapest week found so far, to the whole dollar: no whole-dollar
                    # budget under the one offered completes a week. Every week found is kept, so the cheapest of
                    # any probe is tried.
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
                        while not states and high - low > 1:
                            limit = (low + high) // 2
                            states = within(limit)
                            low = low if states else limit
                    trace["cheapest_search"] = {"budget_sgd": high, "candidates": len(kept)}
                    if minimum_distinct_dishes:
                        trace["cheapest_search"]["minimum_distinct_dishes"] = minimum_distinct_dishes
                    return most_varied_first([(weight, state) for state in kept.values()])

                found = [(0.0, state) for state in search.states]

                def full_and_varied(state) -> bool:
                    """Every role filled and no dish or kind twice, every role counted: the least `variety` can be."""
                    dishes = [recipe for _, meal in state.choices for role, recipe in meal if role not in uncounted]
                    return variety(state)[0] == 0 and sameness(dishes) == (0, 0)

                full_and_repeat_free = any(full_and_varied(state) for state in search.states)
                if budget is not None and (not full_and_repeat_free or not budget_is_hard):
                    # A budget-pruned search keeps the cheap repeats or leaves optional dishes out; the first
                    # week in that order within the budget may come from a cost-led search, so all are tried.
                    # Over the budget anyway, the cost-led searches hold the cheapest weeks.
                    found += limit_led()
                    # A search keeps partial weeks and cannot see the room a finished one leaves: unless a week
                    # found is filled with no dish twice, the most varied weeks found and the cheapest spend theirs
                    # on dishes not yet in the week. Over the budget that week need not be the one chosen (the
                    # cheapest is, a repeat charged at one meal's share: `over_budget_pick`), so the cheap weeks
                    # spend their room too: the 2026-10-04 walkthrough's added lunches were one slaw five times
                    # beside a S$58 week of seven different ones.
                    seen = {state.choices for _, state in found}
                    cheapest_starts = sorted(found, key=lambda item: (item[1].cost, item[1].choices))
                    starts = sorted(found, key=order)[:VARIED_STARTS] + cheapest_starts[:VARIED_STARTS]
                    if budget_is_hard and any(variety(state)[0] == 0 and variety(state)[2] <= 1 for _, state in found):
                        starts = []
                    heavy_composition = sum(
                        len(slot.composition or ()) for slot in problem.slots
                    ) >= HEAVY_COMPOSITION_DISH_POSITIONS and not any(slot.locked_roles for slot in problem.slots)

                    def is_best(state) -> bool:
                        """At the least `variety` can be, which `order` sorts by first: every role filled, no dish
                        or kind twice, counting every role. Weeks as varied still sort by search and loss, and a
                        later start could find one lighter; only variety is kept from getting worse."""
                        return heavy_composition and full_and_varied(state)

                    found.extend(
                        _vary_starts(
                            meal_beam,
                            problem,
                            starts,
                            seen,
                            is_best=is_best,
                        )
                    )
                elif banded:
                    fallback = lambda: most_varied_first(limit_led())  # noqa: E731
                assignments_list = most_varied_first(found)
                if cheapest:
                    assignments_list, fallback, last_resort = [], None, cheapest_weeks
                elif cheapest_last and budget is not None:
                    # Every week above failed: the cheapest week the search can find, if it is within budget. Every
                    # plan shape gets it, however many dishes a meal has (owner, 2026-10-22; ADR-0080).
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
            if len({a.recipe_id for a in assignments}) < minimum_distinct_dishes:
                continue  # a week with fewer different dishes than asked for is not one (ADR-0067)
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
            result = over_budget_pick(passed, problem.slots, constraints.weekly_budget_sgd, problem.uncounted_roles)
        if result is None:
            # A search that built no week said why (a meal, the repeats, the budget) or ran out of steps: no week
            # reached a check, so an input issue elsewhere in the pool (one recipe's servings) did not decide it, and
            # "details are missing" sent the household to retry a request that cannot plan as asked.
            searched = trace.get("search", {}) if not trace["validation_attempts"] else {}
            emptied_by = searched.get("emptied_by")
            uncertain = uncertain and emptied_by is None and not searched.get("exhausted")
            evidence = "needs_data" if uncertain else "bounded_search_exhausted"
            status = "needs_data" if uncertain else "candidate_rejected"
            if not uncertain and constraints.planner_strategy == "greedy-baseline" and trace["validation_attempts"]:
                # The baseline produced a candidate; its rejection is not a search-resource limit or a proof.
                evidence = "candidate_validation_failed"
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
                # A seven-day plan of course roles keeps its words (and the protocol reports theirs).
                what, span = (
                    ("seven dinners", "week")
                    if constraints.day_count == 7 and not any_structured
                    else ("these meals", "plan")
                )
                message = (
                    f"I couldn't fit {what} into S${constraints.weekly_budget_sgd:.2f}. The cheapest {span} "
                    f"I found costs S${min(totals):.2f}. Try a higher budget or fewer limits."
                )
            elif trace.get("search", {}).get("exhausted"):
                # The search used every step it is allowed (`max_expansions`) and built no week. Said as that, not as
                # a slow plan to try again: planning time has no limit (ADR-0080), and the same request searches the
                # same way again.
                message = (
                    "I searched as far as the planner goes and found no week that fits. Try relaxing one of the limits."
                )
            elif emptied_by == "repeats":
                message = (
                    "I couldn't find enough different dishes for a week without repeats under these limits. "
                    "Allow a dish twice, or relax one of the limits."
                )
            else:
                message = "I couldn't find a week that meets every limit. Try relaxing one of them."
            by_rule = uncoverable_by_rule(problem)
            uncovered = [name for names in by_rule.values() for name in names]
            if uncovered:
                message = uncovered_message(by_rule)
                trace["uncovered_members"] = uncovered
                trace["uncovered_members_by_rule"] = by_rule
            raise ProductPlanningError(status, message, trace, problem=problem.model_copy(deep=True))
        assignments, shopping, report = result
        # A perishable line says "use within N days" on the list (layer 08); only with the household's rules on.
        perishables = perishable_ingredients(by_id.values()) if household_rules else set()
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
                    shopping_trip=row.trip,
                    perishable=True if row.ingredient_id in perishables else None,
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
                    [
                        *(
                            warning
                            for r in recommendations
                            if r.grocery_estimate
                            for warning in r.grocery_estimate.warnings
                        ),
                        *filter(
                            None, [basics_note({b for a in assignments for b in basics_used.get(a.recipe_id, ())})]
                        ),
                        *unattended,
                    ]
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
        portions = dish_portions(problem, assignments)
        placements = [
            (
                *slot_day[a.slot_id],
                a.role_id or "main",
                # The dish's share of its meal, what one person who eats it has; with a household block, the
                # servings it is cooked for besides, which are the members who can eat it (ADR-0071 section 1).
                portions[i][0],
                portions[i][0] * portions[i][1] if household is not None else None,
            )
            for i, a in enumerate(assignments)
        ]
        return ProductPlan(selected, grocery, trace, placements)


def meal_structure_roles(roles, people: int) -> list:
    """A structured meal's roles with `people` at it: a role with min_people only from that many on."""
    return [role for role in roles if (role.min_people or 0) <= people]


def recipe_tags(recipe, candidate) -> dict:
    """The layer 08 tags a candidate carries (PR-2), from its catalog recipe: its meal role, staple, protein
    sources, cooking methods, equipment, cuisine group, and whether a line it buys is perishable. A recipe whose
    meal role, staple or protein sources wait for review carries none of the three: it is untagged."""
    bought = {item.ingredient_id for item in candidate.ingredients}
    perishable = any(
        line.ingredient.perishable is True and line.ingredient.normalized_name in bought
        for line in getattr(recipe, "recipe_ingredients", None) or []
    )
    held = not unreviewed(recipe)
    return {
        "meal_role": meal_role_of(recipe),
        "contains_staple": recipe.contains_staple if held else None,
        "protein_sources": recipe.protein_sources if held else None,
        "cooking_methods": recipe.cooking_methods,
        "equipment": recipe.equipment,
        "cuisine_group": meal_structure.cuisine_group(recipe.cuisine),
        "perishable": True if perishable else None,
    }


def perishable_ingredients(recipes) -> set[str]:
    return {
        line.ingredient.normalized_name
        for recipe in recipes
        for line in getattr(recipe, "recipe_ingredients", None) or []
        if line.ingredient.perishable is True
    }


def over_budget_pick(passed, slots, budget, uncounted=frozenset()):
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
        dishes = [a.recipe_id for a in assignments if getattr(a, "role_id", None) not in uncounted]
        staples = {a.slot_id for a in assignments if getattr(a, "role_id", None) == "staple"}
        # A staple left out beside a dish that carries it is no empty dish (ADR-0070).
        empty = sum(
            len(slot.composition or [None])
            - filled[slot.slot_id]
            - (
                structured_slot(slot)
                and slot.slot_id not in staples
                and any(r.role_id == "staple" for r in slot.composition)
            )
            for slot in slots
        )
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
