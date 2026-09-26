"""Bounded deterministic beam search over meals of several dishes (ADR-0036 section 5).

Each slot's meal is chosen as one combination of dishes, one per role. The
search keeps the best `width` partial plans, slot by slot in chronological
order; every retained completion is independently validated. Like the one-dish
beam, it proves neither optimality nor infeasibility.
"""

from dataclasses import asdict, dataclass
from itertools import product
from math import ceil

from app.planning.dietary_tags import satisfies
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss, meal_affinity_loss
from app.planning.input_audit import require_finite_problem
from app.planning.meal_composition import MAIN_ROLE, meal_minutes, portion_shares
from app.planning.nutrition_scope import nutrition_guard_loss
from app.planning.recipe_quality import dish_kind
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
    # Product settings (ADR-0046). The defaults reproduce the recorded multi-dish evaluations.
    # How much an earlier use of a recipe costs (ADR-0044 raised the one-dish beam's 0.10 to 1.0).
    repeat_cost: float = 0.10
    # Charge a reused recipe once, however often it came before: a household that asked for a soup
    # would rather have a soup again than none, which a cost growing per use would buy.
    flat_repeat: bool = False
    # Cap on dish combinations tried per meal: candidates per role shrink as roles are added, so a
    # five-dish meal is searched in seconds, not a minute. None keeps every combination.
    max_meal_combinations: int | None = None
    # No two dishes of one kind in a meal ("Indian Raita" and "Jim's Raita").
    distinct_kinds: bool = False
    # Each meal sees the best half of a role's candidates plus a window of the rest that moves
    # through the week, so seven dinners are not all drawn from the same five mains.
    rotate_candidates: bool = False

    def __post_init__(self):
        counts = (self.width, self.candidates_per_role, self.meal_options_per_slot, self.max_expansions)
        if min(counts) < 1 or self.repeat_cost < 0 or (self.max_meal_combinations or 1) < 1:
            raise ValueError("Meal beam limits must be positive")


@dataclass(frozen=True)
class MealOption:
    dishes: tuple[tuple[str | None, str], ...]  # (role_id, recipe_id); role None in a one-dish slot
    loss: float
    # What the meal's ingredients cost at the cheapest price per gram, before packages.
    cost: float = 0.0


@dataclass(frozen=True)
class MealState:
    choices: tuple[tuple[str, tuple[tuple[str | None, str], ...]], ...] = ()
    loss: float = 0.0
    cost: float = 0.0


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
        prices = cheapest_per_gram(problem) if problem.purchase_budget_sgd is not None else {}
        roles = slot.composition or [ANY_COURSE]
        per_role_limit = self.limits.candidates_per_role
        if self.limits.max_meal_combinations is not None:
            per_role_limit = max(3, min(per_role_limit, int(self.limits.max_meal_combinations ** (1 / len(roles)))))
        per_role: list[list[tuple[str | None, str] | None]] = []
        position = [s.slot_id for s in sorted(problem.slots, key=self._slot_key)].index(slot.slot_id)
        for role_index, role in enumerate(roles):
            turn = position + role_index * len(problem.slots)
            eligible = [
                r
                for r in recipes
                if dish_eligible(problem, slot, r) and (slot.composition is None or r.course in role.courses)
            ]
            if slot.composition is None and slot.locked_recipe_id is not None:
                eligible = [r for r in eligible if r.recipe_id == slot.locked_recipe_id]
            # A lunch takes lunch dishes whenever there are enough of them (ADR-0044, every meal since
            # ADR-0046); the soft affinity only matters when the catalog runs short.
            fitting = [r for r in eligible if slot.meal_type in r.allowed_meal_types]
            if len(fitting) >= self.limits.candidates_per_role:
                eligible = fitting
            ranked = sorted(eligible, key=lambda r: (self._dish_loss(problem, slot, r), r.recipe_id))
            key = role.role_id if slot.composition is not None else None
            best = per_role_limit if not (prices and self.limits.max_meal_combinations) else -(-per_role_limit // 2)
            kept = self._pick(ranked, best, turn)
            # A dish the household asked for is always a candidate, however it ranks.
            kept += [r for r in ranked[best:] if wanted(problem, r)]
            if prices:
                # With a budget, the cheapest dishes are candidates too. Ranking by loss alone
                # kept only dishes the search liked, and every plan it held was over budget.
                cheapest = sorted(
                    (r for r in ranked if r not in kept),
                    key=lambda r: (dish_cost(problem, slot, r, role.role_id, prices), r.recipe_id),
                )
                # Under the combination cap the cheapest share the role's places instead of doubling them.
                kept += self._pick(
                    cheapest,
                    per_role_limit if self.limits.max_meal_combinations is None else per_role_limit - best,
                    turn,
                )
            options: list[tuple[str | None, str] | None] = [(key, r.recipe_id) for r in kept]
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
            if self.limits.distinct_kinds:
                kinds = [dish_kind(by_id[recipe_id].title) for _, recipe_id in dishes]
                if len(kinds) != len(set(kinds)):
                    continue
            shares = portion_shares(problem.composition_policy, [role or MAIN_ROLE for role, _ in dishes])
            loss = sum(
                float(shares[role or MAIN_ROLE]) * self._dish_loss(problem, slot, by_id[recipe_id])
                for role, recipe_id in dishes
            ) + EMPTY_OPTIONAL_ROLE_LOSS * combination.count(None)
            cost = (
                sum(
                    dish_cost(problem, slot, by_id[recipe_id], role or MAIN_ROLE, prices, shares[role or MAIN_ROLE])
                    for role, recipe_id in dishes
                )
                if prices
                else 0.0
            )
            meals.append(MealOption(dishes, loss, cost))
            # Each dish's rank within its role; their sum spreads tied meals across every role's
            # choices, where ordering ties by id kept 64 meals sharing one main.
            spread[dishes] = sum(options.index(dish) for options, dish in zip(per_role, combination, strict=True))
        meals.sort(
            key=lambda meal: (
                -sum(wanted(problem, by_id[r]) for _, r in meal.dishes),
                meal.loss,
                spread[meal.dishes],
                meal.dishes,
            )
        )
        limit = self.limits.meal_options_per_slot
        if self.limits.rotate_candidates and len(meals) > limit:
            meals = spread_meals(meals, limit, per_role_limit)
        if prices and len(meals) > limit:
            # Under a budget, keep room for this slot's cheapest meals: kept by score alone,
            # the cheap combinations were cut here before the search could ever hold one.
            room = max(1, limit // 4)
            cheapest = sorted(meals[limit - room :], key=lambda meal: (meal.cost, meal.dishes))
            return meals[: limit - room] + cheapest[:room]
        return meals[:limit]

    def _pick(self, ranked: list, count: int, turn: int) -> list:
        """`count` dishes: all of the best when not rotating; else the best half and a moving window."""
        if not self.limits.rotate_candidates or len(ranked) <= count or count < 2:
            return ranked[:count]
        head = -(-count // 2)
        rest = ranked[head:]
        width = count - head
        start = (turn * width) % len(rest)
        return ranked[:head] + (rest[start:] + rest[:start])[:width]

    def _dish_loss(self, problem: FinalPlanningProblem, slot: PlanningSlot, recipe: PlanningRecipeCandidate) -> float:
        local = (
            self.local_losses[recipe.recipe_id]
            if self.local_losses is not None
            else local_recipe_loss(
                recipe, max_time_minutes=slot.max_time_minutes, health_preferences=problem.health_preferences
            )
        )
        # A soft nutrition guard keeps a dish near a stated target (planning-nutrition-scope).
        return local + meal_affinity_loss(recipe, slot.meal_type) + nutrition_guard_loss(problem, recipe)

    def search_candidates(self, problem: FinalPlanningProblem) -> MealBeamResult:
        require_finite_problem(problem)
        states = [MealState()]
        expansions, pruned, exhausted, empty = 0, False, False, []
        ordered = sorted(problem.slots, key=self._slot_key)
        day_closes = {
            slot.slot_id
            for slot, after in zip(ordered, [*ordered[1:], None], strict=True)
            if after is None or after.planned_date != slot.planned_date
        }
        for slot in ordered:
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
                        loss = (
                            state.loss
                            + option.loss
                            + repetition_loss(
                                problem, state, option.dishes, self.limits.repeat_cost, self.limits.flat_repeat
                            )
                        )
                        next_states.append(
                            MealState(state.choices + ((slot.slot_id, option.dishes),), loss, state.cost + option.cost)
                        )
                if exhausted:
                    break
            if exhausted:
                states = []  # A partial horizon is never returned as a plan.
                break
            remaining = len(problem.slots) - len(next_states[0].choices) if next_states else 0
            next_states = [s for s in next_states if requests_reachable(problem, s, remaining)]
            # A day over a stated daily ceiling never comes back under it; one below its floor
            # is final once its last meal is planned (ADR-0046 section 3).
            next_states = [s for s in next_states if day_permitted(problem, s, slot, slot.slot_id in day_closes)]
            budget = problem.purchase_budget_sgd if problem.budget_is_hard else None
            spend: dict[tuple, float] = {}
            if budget is not None:
                # Whole packages only ever add cost, so a partial plan already over the budget can
                # never come back under it. Drop those instead of filling the beam with them.
                packages = packages_by_ingredient(problem)
                spend = {s.choices: packaged_cost(problem, s.choices, packages) for s in next_states}
                next_states = [s for s in next_states if spend[s.choices] <= budget]
            # Progress towards what the household asked for orders states; it is never part of a
            # state's loss, so the loss stays the objective CP-SAT minimises.
            next_states.sort(key=lambda s: (s.loss - REQUEST_BONUS * request_progress(problem, s), s.choices))
            pruned = pruned or len(next_states) > self.limits.width
            if budget is not None and len(next_states) > self.limits.width:
                # Keep room for the cheapest plans too: the best-scoring ones can all be the dear
                # ones, and then every plan the beam holds fails the budget at the end of the week.
                room = max(1, self.limits.width // 4)
                best = next_states[: self.limits.width - room]
                cheapest = sorted(next_states[self.limits.width - room :], key=lambda s: (spend[s.choices], s.choices))
                states = best + cheapest[:room]
            else:
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


def cheapest_per_gram(problem) -> dict[str, float]:
    """The lowest price per gram for every ingredient with an available product."""
    prices: dict[str, float] = {}
    for option in problem.products:
        if option.available and option.package_quantity:
            price = option.price_sgd / option.package_quantity
            prices[option.ingredient_id] = min(prices.get(option.ingredient_id, price), price)
    return prices


def packages_by_ingredient(problem) -> dict[str, list[tuple[float, float]]]:
    packages: dict[str, list[tuple[float, float]]] = {}
    for option in problem.products:
        if option.available and option.package_quantity:
            packages.setdefault(option.ingredient_id, []).append((option.package_quantity, option.price_sgd))
    return packages


def planned_grams(problem, choices) -> dict[str, float]:
    """What the plan so far needs of each ingredient, each dish at its share of its meal."""
    slots = {slot.slot_id: slot for slot in problem.slots}
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    grams: dict[str, float] = {}
    for slot_id, dishes in choices:
        slot = slots[slot_id]
        shares = portion_shares(problem.composition_policy, [role or MAIN_ROLE for role, _ in dishes]) or {}
        for role, recipe_id in dishes:
            recipe = recipes[recipe_id]
            scale = slot.servings * float(shares.get(role or MAIN_ROLE, 1)) / recipe.servings
            for item in recipe.ingredients:
                if item.quantity is not None:
                    grams[item.ingredient_id] = grams.get(item.ingredient_id, 0.0) + item.quantity * scale
    return grams


def packaged_cost(problem, choices, packages: dict[str, list[tuple[float, float]]]) -> float:
    """What the plan so far costs in whole packages, the cheapest product for each ingredient.

    This is the shopping policy the validator prices, and adding dishes only ever adds
    cost, so a partial plan's cost is a lower bound on the finished plan's.
    """
    pantry = {item.ingredient_id: item.quantity for item in problem.pantry if item.quantity is not None}
    total = 0.0
    for ingredient, grams in planned_grams(problem, choices).items():
        remaining = max(0.0, grams - pantry.get(ingredient, 0.0))
        options = packages.get(ingredient)
        if remaining <= 0 or not options:
            continue  # an unpriceable ingredient is the validator's to refuse
        total += min(ceil(remaining / size - 1e-9) * price for size, price in options)
    return total


def dish_cost(
    problem, slot, recipe, role_id: str | None, prices: dict[str, float], share: float | None = None
) -> float:
    """What one dish's ingredients cost at those prices, at the share it is cooked for.

    Before the meal's size is known, the share of a full meal is used, which orders
    dishes the same way for every size.
    """
    if share is None:
        share = 1.0
    return sum(
        (item.quantity or 0) * slot.servings * float(share) / recipe.servings * prices.get(item.ingredient_id, 0.0)
        for item in recipe.ingredients
    )


def repetition_loss(problem, state: MealState, dishes, repeat_cost: float = 0.10, flat_repeat: bool = False) -> float:
    """Without a diversity policy, the one-dish beam's legacy penalties, counted per dish.

    Each earlier use of a recipe costs 0.10 and repeating the previous meal's
    dish costs 0.35 more (`app/planning/diversity.py`). A recorded policy makes
    repetition a hard rule instead (`horizon_permitted`).
    """
    if problem.diversity_policy is not None:
        return 0.0
    free = set(problem.repetition_rules.repeat_ok_roles) if problem.repetition_rules else set()
    previous = [recipe_id for _, meal in state.choices for role, recipe_id in meal if role not in free]
    last = {recipe_id for role, recipe_id in state.choices[-1][1] if role not in free} if state.choices else set()
    return sum(
        (min(previous.count(recipe_id), 1) if flat_repeat else previous.count(recipe_id)) * repeat_cost
        + (0.35 if recipe_id in last else 0.0)
        for role, recipe_id in dishes
        if role not in free
    )


# Orders beam states by progress towards stated requests; larger than any meal's loss.
REQUEST_BONUS = 3.0


def wanted(problem, recipe) -> bool:
    """A dish that counts towards a stated minimum."""
    rules = problem.repetition_rules
    if rules is None:
        return False
    if any(c.recipe_id == recipe.recipe_id and c.min_uses for c in rules.recipe_counts):
        return True
    names = {i.ingredient_id for i in recipe.ingredients}
    return any(w.ingredient_id in names for w in rules.ingredient_meals)


def _deficits(problem, state: MealState) -> list[int]:
    rules = problem.repetition_rules
    if rules is None:
        return []
    recipes = {r.recipe_id: r for r in problem.recipes}
    uses = [r for _, meal in state.choices for _, r in meal]
    deficits = [max(0, c.min_uses - uses.count(c.recipe_id)) for c in rules.recipe_counts]
    for w in rules.ingredient_meals:
        met = sum(
            any(w.ingredient_id in {i.ingredient_id for i in recipes[r].ingredients} for _, r in meal)
            for _, meal in state.choices
        )
        deficits.append(max(0, w.min_meals - met))
    return deficits


def request_progress(problem, state: MealState) -> int:
    rules = problem.repetition_rules
    if rules is None:
        return 0
    wanted_total = sum(c.min_uses for c in rules.recipe_counts) + sum(w.min_meals for w in rules.ingredient_meals)
    return wanted_total - sum(_deficits(problem, state))


def requests_reachable(problem, state: MealState, remaining_slots: int) -> bool:
    """Each stated minimum can still be met in the meals left (one use per meal at most)."""
    return all(deficit <= remaining_slots for deficit in _deficits(problem, state))


def day_permitted(problem, state: MealState, slot, day_closed: bool) -> bool:
    """The hard per-day nutrition bands on `slot`'s day so far: ceilings always, floors once it is closed."""
    bands = [band for band in problem.nutrition_bands if band.hard and band.scope == "per_day"]
    if not bands:
        return True
    slots = {item.slot_id: item for item in problem.slots}
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    meals = [dishes for slot_id, dishes in state.choices if slots[slot_id].planned_date == slot.planned_date]
    for band in bands:
        total = 0.0
        for dishes in meals:
            shares = portion_shares(problem.composition_policy, [role or MAIN_ROLE for role, _ in dishes]) or {}
            total += sum(
                float(shares.get(role or MAIN_ROLE, 1)) * getattr(recipes[recipe_id].nutrients_per_serving, band.metric)
                for role, recipe_id in dishes
            )
        if band.upper is not None and total - band.upper > 1e-6:
            return False
        if day_closed and band.lower is not None and band.lower - total > 1e-6:
            return False
    return True


def horizon_permitted(problem, state: MealState, dishes) -> bool:
    """No recipe twice, no primary protein shared with the previous meal, core caps over dishes."""
    previous = [recipe_id for _, meal in state.choices for _, recipe_id in meal]
    ids = [recipe_id for _, recipe_id in dishes]
    rules = problem.repetition_rules
    if rules is not None:
        caps = {c.recipe_id: c.max_uses for c in rules.recipe_counts if c.max_uses is not None}
        for recipe_id in set(ids):
            used = previous.count(recipe_id) + ids.count(recipe_id)
            cap = caps.get(recipe_id, rules.max_uses_per_recipe)
            if cap is not None and used > cap:
                return False
    policy = problem.diversity_policy
    if policy is None:
        return True
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


def spread_meals(meals: list[MealOption], limit: int, per_role_limit: int) -> list[MealOption]:
    """The best meals, but no dish in more than its fair share of them, then the best of the rest.

    Kept by score alone, a slot's meals all shared the same top dishes and the search could only
    repeat them through the week; every candidate needs some meals of its own to be chosen at all.
    """
    cap = max(4, limit // max(1, per_role_limit))
    counts: dict[str, int] = {}
    kept, deferred = [], []
    for meal in meals:
        ids = [recipe_id for _, recipe_id in meal.dishes]
        if all(counts.get(recipe_id, 0) < cap for recipe_id in ids):
            kept.append(meal)
            for recipe_id in ids:
                counts[recipe_id] = counts.get(recipe_id, 0) + 1
        else:
            deferred.append(meal)
    return kept + deferred
