"""Bounded deterministic beam search over meals of several dishes (ADR-0036 section 5).

Each slot's meal is chosen as one combination of dishes, one per role. The
search keeps the best `width` partial plans, slot by slot in chronological
order; every retained completion is independently validated. Like the one-dish
beam, it proves neither optimality nor infeasibility.
"""

from dataclasses import asdict, dataclass
from itertools import product

from app.planning.dietary_tags import satisfies
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss, meal_affinity_loss
from app.planning.input_audit import require_finite_problem
from app.planning.meal_composition import MAIN_ROLE, meal_minutes, portion_shares
from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    FinalPlanningSolution,
    PlanningAssignment,
    PlanningMealRole,
    PlanningRecipeCandidate,
    PlanningSlot,
    PlanningTrace,
)

# A one-dish slot is a single role that admits any course, as before course labels.
ANY_COURSE = PlanningMealRole(role_id=MAIN_ROLE, courses=["main"])
# An optional role the household asked for is left empty only when no dish fits:
# the cost of an empty one exceeds any dish's share-weighted loss (at most 1.5).
EMPTY_OPTIONAL_ROLE_LOSS = 2.0


@dataclass(frozen=True)
class MealBeamLimits:
    width: int = 32
    candidates_per_role: int = 8
    meal_options_per_slot: int = 64
    max_expansions: int = 20000

    def __post_init__(self):
        if min(asdict(self).values()) < 1:
            raise ValueError("Meal beam limits must be positive")


@dataclass(frozen=True)
class MealOption:
    dishes: tuple[tuple[str | None, str], ...]  # (role_id, recipe_id); role None in a one-dish slot
    loss: float


@dataclass(frozen=True)
class MealState:
    choices: tuple[tuple[str, tuple[tuple[str | None, str], ...]], ...] = ()
    loss: float = 0.0


@dataclass(frozen=True)
class MealBeamResult:
    states: tuple[MealState, ...]
    expansions: int
    pruned: bool
    exhausted: bool
    empty_slot_ids: tuple[str, ...]


class MealBeamPlanner(FinalScopeReferencePlanner):
    def __init__(self, limits: MealBeamLimits | None = None, *, local_losses: dict[str, float] | None = None):
        """`local_losses` replaces the reference dish loss, as the product's recommendation ranking does."""
        super().__init__()
        self.limits = limits or MealBeamLimits()
        self.local_losses = dict(local_losses) if local_losses is not None else None

    def meal_options(self, problem: FinalPlanningProblem, slot: PlanningSlot) -> list[MealOption]:
        """The slot's best meals: dishes that pass on their own, combined into meals that pass as meals."""
        recipes = sorted(problem.recipes, key=lambda r: r.recipe_id)
        roles = slot.composition or [ANY_COURSE]
        per_role: list[list[tuple[str | None, str] | None]] = []
        for role in roles:
            eligible = [
                r
                for r in recipes
                if dish_eligible(problem, slot, r) and (slot.composition is None or r.course in role.courses)
            ]
            if slot.composition is None and slot.locked_recipe_id is not None:
                eligible = [r for r in eligible if r.recipe_id == slot.locked_recipe_id]
            ranked = sorted(eligible, key=lambda r: (self._dish_loss(problem, slot, r), r.recipe_id))
            key = role.role_id if slot.composition is not None else None
            options: list[tuple[str | None, str] | None] = [
                (key, r.recipe_id) for r in ranked[: self.limits.candidates_per_role]
            ]
            if not role.required:
                options.append(None)
            per_role.append(options)
        by_id = {r.recipe_id: r for r in recipes}
        meals = []
        spread: dict[tuple, int] = {}
        for combination in product(*per_role):
            dishes = tuple(dish for dish in combination if dish is not None)
            if not dishes or not meal_permitted(problem, slot, dishes, by_id):
                continue
            shares = portion_shares(problem.composition_policy, [role or MAIN_ROLE for role, _ in dishes])
            loss = sum(
                float(shares[role or MAIN_ROLE]) * self._dish_loss(problem, slot, by_id[recipe_id])
                for role, recipe_id in dishes
            ) + EMPTY_OPTIONAL_ROLE_LOSS * combination.count(None)
            meals.append(MealOption(dishes, loss))
            # Each dish's rank within its role; their sum spreads tied meals across every role's
            # choices, where ordering ties by id kept 64 meals sharing one main.
            spread[dishes] = sum(options.index(dish) for options, dish in zip(per_role, combination, strict=True))
        meals.sort(key=lambda meal: (meal.loss, spread[meal.dishes], meal.dishes))
        return meals[: self.limits.meal_options_per_slot]

    def _dish_loss(self, problem: FinalPlanningProblem, slot: PlanningSlot, recipe: PlanningRecipeCandidate) -> float:
        local = (
            self.local_losses[recipe.recipe_id]
            if self.local_losses is not None
            else local_recipe_loss(
                recipe, max_time_minutes=slot.max_time_minutes, health_preferences=problem.health_preferences
            )
        )
        return local + meal_affinity_loss(recipe, slot.meal_type)

    def search_candidates(self, problem: FinalPlanningProblem) -> MealBeamResult:
        require_finite_problem(problem)
        states = [MealState()]
        expansions, pruned, exhausted, empty = 0, False, False, []
        for slot in sorted(problem.slots, key=self._slot_key):
            options = self.meal_options(problem, slot)
            must_assign = slot.required or slot.locked_recipe_id is not None
            if not options and must_assign:
                empty.append(slot.slot_id)
            candidates: list[MealOption | None] = [*options, *([] if must_assign else [None])]
            next_states = []
            for state in states:
                for option in candidates:
                    if expansions >= self.limits.max_expansions:
                        exhausted = True
                        break
                    expansions += 1
                    if option is None:
                        next_states.append(state)
                    elif horizon_permitted(problem, state, option.dishes):
                        loss = state.loss + option.loss + repetition_loss(problem, state, option.dishes)
                        next_states.append(MealState(state.choices + ((slot.slot_id, option.dishes),), loss))
                if exhausted:
                    break
            if exhausted:
                states = []  # A partial horizon is never returned as a plan.
                break
            next_states.sort(key=lambda s: (s.loss, s.choices))
            pruned = pruned or len(next_states) > self.limits.width
            states = next_states[: self.limits.width]
            if not states:
                break
        return MealBeamResult(tuple(states), expansions, pruned, exhausted, tuple(empty))

    def solve(self, problem: FinalPlanningProblem) -> FinalPlanningSolution:
        search = self.search_candidates(problem)
        results = []
        for state in search.states:
            assignments = assignments_of(state)
            shopping = self._build_shopping(problem, assignments)
            report = self.validator.validate(problem, assignments, shopping)
            priority = {"passed": 0, "indeterminate": 1, "failed": 2}[report.status]
            results.append(
                ((priority, report.hard_failure_count, state.loss, state.choices), assignments, shopping, report)
            )
        if results:
            _, assignments, shopping, report = min(results, key=lambda result: result[0])
        else:
            assignments, shopping = [], []
            report = self.validator.validate(problem, assignments, shopping)
        status = {"passed": "feasible", "indeterminate": "needs_data", "failed": "candidate_rejected"}[report.status]
        if search.exhausted or not search.states:
            status = "candidate_rejected"
        return FinalPlanningSolution(
            problem_id=problem.problem_id,
            status=status,
            assignments=assignments,
            shopping=shopping,
            validation=report,
            trace=PlanningTrace(
                algorithm="deterministic-meal-beam-search",
                algorithm_version="meal-beam-v1",
                deterministic=True,
                candidate_limit=self.limits.candidates_per_role,
                diversity_policy=problem.diversity_policy,
                warnings=[
                    f"limits={asdict(self.limits)}; expansions={search.expansions}",
                    f"beam_pruned={search.pruned}; expansion_limit_reached={search.exhausted}; "
                    f"completed_candidates={len(results)}; empty_slots={list(search.empty_slot_ids)}",
                    f"composition_policy={problem.composition_policy.model_dump()}",
                    # ponytail: per_day, horizon nutrition and budget are checked only by the
                    # validator at the end; add partial-plan bounds if they prune too little.
                    "Horizon nutrition and budget are not bounded during search. "
                    "No global infeasibility or optimality claim.",
                ],
            ),
        )


def assignments_of(state: MealState) -> list[PlanningAssignment]:
    return [
        PlanningAssignment(slot_id=slot_id, role_id=role, recipe_id=recipe_id)
        for slot_id, dishes in state.choices
        for role, recipe_id in dishes
    ]


def dish_eligible(problem: FinalPlanningProblem, slot: PlanningSlot, recipe: PlanningRecipeCandidate) -> bool:
    """What one dish must satisfy on its own; a meal can never exceed its longest dish's time."""
    if slot.max_time_minutes is not None and recipe.total_time_minutes > slot.max_time_minutes:
        return False
    if slot.max_dish_time_minutes is not None and recipe.total_time_minutes > slot.max_dish_time_minutes:
        return False
    if set(recipe.allergens) & set(problem.allergens):
        return False
    if set(problem.allergens) - set(problem.allergen_vocabulary or []):
        return False
    if {item.ingredient_id for item in recipe.ingredients} & set(problem.excluded_ingredients):
        return False
    if not satisfies(problem.dietary_requirements, recipe.dietary_tags):
        return False
    one_dish_meal = slot.composition is None
    for band in problem.nutrition_bands:
        if band.hard and (band.scope == "per_dish" or (one_dish_meal and band.scope == "per_slot")):
            actual = getattr(recipe.nutrients_per_serving, band.metric)
            if band.lower is not None and actual - band.lower < -1e-6:
                return False
            if band.upper is not None and band.upper - actual < -1e-6:
                return False
    return True


def meal_permitted(problem, slot, dishes, recipes) -> bool:
    """Meal-level hard rules: distinct dishes, portions, meal time, per-meal nutrition, one protein each."""
    ids = [recipe_id for _, recipe_id in dishes]
    if len(ids) != len(set(ids)):
        return False
    shares = portion_shares(problem.composition_policy, [role or MAIN_ROLE for role, _ in dishes])
    if shares is None or sum(shares.values()) < 1:
        return False
    chosen = [recipes[recipe_id] for recipe_id in ids]
    if slot.max_time_minutes is not None and meal_minutes(chosen, problem.composition_policy) > slot.max_time_minutes:
        return False
    if len(dishes) > 1:
        for band in problem.nutrition_bands:
            if band.hard and band.scope == "per_slot":
                actual = sum(
                    float(shares[role]) * getattr(recipes[recipe_id].nutrients_per_serving, band.metric)
                    for role, recipe_id in dishes
                )
                if band.lower is not None and actual - band.lower < -1e-6:
                    return False
                if band.upper is not None and band.upper - actual < -1e-6:
                    return False
    policy = problem.diversity_policy
    if policy is not None:
        proteins = [
            set(policy.classifications[recipe_id].primary_proteins.values())
            for recipe_id in ids
            if recipe_id in policy.classifications
        ]
        if sum(len(group) for group in proteins) != len(set().union(*proteins)):
            return False
    return True


def repetition_loss(problem, state: MealState, dishes) -> float:
    """Without a diversity policy, the one-dish beam's legacy penalties, counted per dish.

    Each earlier use of a recipe costs 0.10 and repeating the previous meal's
    dish costs 0.35 more (`app/planning/diversity.py`). A recorded policy makes
    repetition a hard rule instead (`horizon_permitted`).
    """
    if problem.diversity_policy is not None:
        return 0.0
    previous = [recipe_id for _, meal in state.choices for _, recipe_id in meal]
    last = {recipe_id for _, recipe_id in state.choices[-1][1]} if state.choices else set()
    return sum(previous.count(recipe_id) * 0.10 + (0.35 if recipe_id in last else 0.0) for _, recipe_id in dishes)


def horizon_permitted(problem, state: MealState, dishes) -> bool:
    """No recipe twice, no primary protein shared with the previous meal, core caps over dishes."""
    policy = problem.diversity_policy
    if policy is None:
        return True
    previous = [recipe_id for _, meal in state.choices for _, recipe_id in meal]
    ids = [recipe_id for _, recipe_id in dishes]
    if set(ids) & set(previous):
        return False
    if state.choices:
        last = [policy.classifications.get(recipe_id) for _, recipe_id in state.choices[-1][1]]
        if all(item is not None for item in last):
            last_proteins = {p for item in last for p in item.primary_proteins.values()}
            for recipe_id in ids:
                roles = policy.classifications.get(recipe_id)
                if roles is not None and set(roles.primary_proteins.values()) & last_proteins:
                    return False
    cores = {core for item in policy.classifications.values() for core in item.core_ingredient_ids}
    recipes = {r.recipe_id: r for r in problem.recipes}
    counts: dict[str, int] = {}
    for recipe_id in [*previous, *ids]:
        for core in {i.ingredient_id for i in recipes[recipe_id].ingredients} & cores:
            counts[core] = counts.get(core, 0) + 1
    return all(count <= policy.max_slots_per_core_ingredient for count in counts.values())
