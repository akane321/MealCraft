"""Exact CP-SAT planning of composed meals: the solver of arms B and O2 (ADR-0037).

It minimises the meal beam's own objective (`app/planning/meal_beam.py`) over
the whole candidate packet, so a gap between the two is search loss and
nothing else:
- each dish's loss, weighted by its share of the meal;
- 2.0 for every empty optional role;
- without a diversity policy, 0.10 for every earlier use of a recipe and 0.35
  for repeating a dish of the previous meal.

Hard rules are the meal beam's:
- each dish passes on its own (`dish_eligible`);
- one dish per required role, at most one per optional role;
- no dish twice in a meal;
- the one-cook meal time, with the limit rounded down to the 5-minute grid the
  estimate rounds up to.

A hard budget is modelled with the reference shopping policy: one product per
ingredient, whole packages, known pantry deducted. Demand coefficients are
rounded up to thousandths, so a plan within a cent of the budget may be refused
that the validator would pass. Every returned plan still goes through the
independent validator.

Unsupported inputs are refused, never approximated:
- a diversity policy;
- hard per-meal, per-day or horizon nutrition bands.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import ceil

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss, meal_affinity_loss
from app.planning.input_audit import require_finite_problem
from app.planning.meal_beam import ANY_COURSE, EMPTY_OPTIONAL_ROLE_LOSS, dish_eligible
from app.planning.meal_composition import MAIN_ROLE, hands_on_and_waiting
from app.planning.nutrition_scope import nutrition_guard_loss
from app.schemas.planning_v2 import FinalPlanningProblem, FinalPlanningSolution, PlanningAssignment, PlanningTrace

SCALE = 1000  # losses and quantities in thousandths
REPEAT_LOSS, ADJACENT_LOSS = 0.10, 0.35


@dataclass(frozen=True)
class MealCpSatLimits:
    """ADR-0037 section 3: B uses 30 s, O2 300 s; deterministic time makes a run repeatable."""

    max_time_seconds: float = 30.0
    max_deterministic_time: float = 30.0
    workers: int = 8


@dataclass(frozen=True)
class MealCpSatResult:
    solution: FinalPlanningSolution | None
    status: str  # optimal | feasible | infeasible | unknown | model_invalid
    objective: float | None
    best_bound: float | None
    wall_seconds: float


class MealCpSatPlanner(FinalScopeReferencePlanner):
    def __init__(self, limits: MealCpSatLimits | None = None, *, local_losses: dict[str, float] | None = None):
        super().__init__()
        self.limits = limits or MealCpSatLimits()
        self.local_losses = dict(local_losses) if local_losses is not None else None

    def _dish_loss(self, problem, slot, recipe) -> float:
        local = (
            self.local_losses[recipe.recipe_id]
            if self.local_losses is not None
            else local_recipe_loss(
                recipe, max_time_minutes=slot.max_time_minutes, health_preferences=problem.health_preferences
            )
        )
        # A soft nutrition guard keeps a dish near a stated target (planning-nutrition-scope).
        return local + meal_affinity_loss(recipe, slot.meal_type) + nutrition_guard_loss(problem, recipe)

    def solve_exact(
        self, problem: FinalPlanningProblem, *, hint: list[PlanningAssignment] | None = None
    ) -> MealCpSatResult:
        """`hint` warm-starts the search from a known plan, such as the meal beam's.

        It changes where the search starts, never what is optimal: a hinted run
        still proves, or fails to prove, the same optimum. Without it, CP-SAT with
        a budget can run out of time before it finds a plan the beam found at once.
        """
        from ortools.sat.python import cp_model

        require_finite_problem(problem)
        if problem.diversity_policy is not None:
            raise ValueError("The CP-SAT meal planner does not model a diversity policy")
        if any(b.hard and b.scope in {"per_slot", "per_day", "horizon_average"} for b in problem.nutrition_bands):
            raise ValueError("The CP-SAT meal planner does not model meal, day or horizon nutrition bands")

        started = time.perf_counter()
        model = cp_model.CpModel()
        slots = sorted(problem.slots, key=self._slot_key)
        recipes = sorted(problem.recipes, key=lambda r: r.recipe_id)
        policy = problem.composition_policy
        objective = []
        zero = model.NewConstant(0)
        x: dict[tuple[str, str | None, str], object] = {}  # slot, role key, recipe
        served: dict[str, dict[str, object]] = {}  # slot -> recipe -> "in this meal"
        size_of: dict[tuple[str, int], object] = {}

        for slot in slots:
            roles = slot.composition or [ANY_COURSE]
            composed = slot.composition is not None
            per_recipe: dict[str, list] = {}
            fills = []
            for role in roles:
                key = role.role_id if composed else None
                eligible = [
                    r
                    for r in recipes
                    if dish_eligible(problem, slot, r)
                    and (not composed or r.course in role.courses)
                    and (composed or slot.locked_recipe_id in (None, r.recipe_id))
                ]
                chosen = []
                for r in eligible:
                    var = model.NewBoolVar(f"x[{slot.slot_id},{key},{r.recipe_id}]")
                    x[slot.slot_id, key, r.recipe_id] = var
                    chosen.append(var)
                    per_recipe.setdefault(r.recipe_id, []).append(var)
                must = (slot.required or slot.locked_recipe_id is not None) and role.required
                picked = sum(chosen, zero)
                model.Add(picked == 1) if must else model.Add(picked <= 1)
                filled = model.NewBoolVar(f"filled[{slot.slot_id},{key}]")
                model.Add(picked == filled)
                fills.append((role, key, filled))
                if not role.required:
                    objective.append(round(EMPTY_OPTIONAL_ROLE_LOSS * SCALE) * (1 - filled))
            # No dish twice in one meal.
            served[slot.slot_id] = {}
            for recipe_id, vars_ in per_recipe.items():
                model.Add(sum(vars_) <= 1)
                used = model.NewBoolVar(f"in[{slot.slot_id},{recipe_id}]")
                model.Add(sum(vars_) == used)
                served[slot.slot_id][recipe_id] = used

            # The meal's size decides every dish's share.
            n_filled = sum((f for _, _, f in fills), zero)
            sizes = range(0, len(roles) + 1)  # an optional slot may be left empty
            for n in sizes:
                size_of[slot.slot_id, n] = model.NewBoolVar(f"size[{slot.slot_id},{n}]")
                if n > len(policy.main_shares):
                    model.Add(size_of[slot.slot_id, n] == 0)  # no shares defined for this many dishes
            model.AddExactlyOne(size_of[slot.slot_id, n] for n in sizes)
            model.Add(n_filled == sum(n * size_of[slot.slot_id, n] for n in sizes))

            # Share-weighted dish losses: one product term per (dish, meal size).
            by_id = {r.recipe_id: r for r in recipes}
            for _role, key, _ in fills:
                for n in sizes[1:]:
                    share = _share(policy, n, (key or MAIN_ROLE) == MAIN_ROLE)
                    if share is None:
                        continue
                    for r_id in [rid for (s, k, rid) in x if s == slot.slot_id and k == key]:
                        both = model.NewBoolVar("")
                        model.AddBoolAnd([x[slot.slot_id, key, r_id], size_of[slot.slot_id, n]]).OnlyEnforceIf(both)
                        model.AddBoolOr(
                            [x[slot.slot_id, key, r_id].Not(), size_of[slot.slot_id, n].Not()]
                        ).OnlyEnforceIf(both.Not())
                        cost = round(share * self._dish_loss(problem, slot, by_id[r_id]) * SCALE)
                        if cost:
                            objective.append(cost * both)

            # One-cook meal time in half-minutes: hands-on in sequence, the longest wait, a switch per extra dish.
            if slot.max_time_minutes is not None and composed:
                step = policy.round_to_minutes
                limit = (slot.max_time_minutes // step) * step
                hands, waits = [], []
                for (s, _key, r_id), var in x.items():
                    if s != slot.slot_id:
                        continue
                    h, w = hands_on_and_waiting(by_id[r_id], policy)
                    hands.append(ceil(h * 2) * var)
                    waits.append((ceil(w * 2), var))
                wait = model.NewIntVar(0, 2 * 720, f"wait[{slot.slot_id}]")
                for value, var in waits:
                    model.Add(wait >= value).OnlyEnforceIf(var)
                switches = 2 * policy.switch_minutes * (n_filled - 1)
                # A single dish is its own total time, which dish_eligible already bounds; an empty meal takes none.
                model.Add(sum(hands, zero) + wait + switches <= 2 * limit).OnlyEnforceIf(
                    [size_of[slot.slot_id, 1].Not(), size_of[slot.slot_id, 0].Not()]
                )

        rules = problem.repetition_rules
        free = set(rules.repeat_ok_roles) if rules else set()
        # Stated repetition rules are hard; a dish in a repeat-ok role pays no penalty.
        all_ids = sorted({rid for (_, _, rid) in x})
        if rules is not None:
            by_recipe = {r.recipe_id: r for r in recipes}
            for r_id in all_ids:
                used = sum(v for (_, _, rid), v in x.items() if rid == r_id)
                cap = next((c.max_uses for c in rules.recipe_counts if c.recipe_id == r_id), None)
                cap = cap if cap is not None else rules.max_uses_per_recipe
                if cap is not None:
                    model.Add(used <= cap)
            for count in rules.recipe_counts:
                used = sum((v for (_, _, rid), v in x.items() if rid == count.recipe_id), zero)
                model.Add(used >= count.min_uses)
            for want in rules.ingredient_meals:
                hits = []
                for slot in slots:
                    has = [
                        v
                        for (s, _, rid), v in x.items()
                        if s == slot.slot_id
                        and want.ingredient_id in {i.ingredient_id for i in by_recipe[rid].ingredients}
                    ]
                    meal_has = model.NewBoolVar("")
                    model.Add(sum(has, zero) >= 1).OnlyEnforceIf(meal_has)
                    hits.append(meal_has)
                model.Add(sum(hits, zero) >= want.min_meals)
        penalised = {slot.slot_id: {} for slot in slots}
        for (s, key, r_id), var in x.items():
            if key not in free:
                penalised[s].setdefault(r_id, []).append(var)
        for s in penalised:
            for r_id, vars_ in list(penalised[s].items()):
                in_meal = model.NewBoolVar("")
                model.Add(sum(vars_) == in_meal)
                penalised[s][r_id] = in_meal
        # Legacy repetition penalties over dishes (no diversity policy).
        for r_id in all_ids:
            uses = [penalised[s.slot_id][r_id] for s in slots if r_id in penalised[s.slot_id]]
            if len(uses) > 1:
                count = model.NewIntVar(0, len(uses), f"uses[{r_id}]")
                model.Add(count == sum(uses))
                square = model.NewIntVar(0, len(uses) ** 2, f"uses2[{r_id}]")
                model.AddMultiplicationEquality(square, [count, count])
                # sum over uses of earlier uses = n(n-1)/2
                objective.append(round(REPEAT_LOSS * SCALE / 2) * (square - count))
            for previous, current in zip(slots, slots[1:], strict=False):
                a, b = penalised[previous.slot_id].get(r_id), penalised[current.slot_id].get(r_id)
                if a is not None and b is not None:
                    both = model.NewBoolVar("")
                    model.AddBoolAnd([a, b]).OnlyEnforceIf(both)
                    model.AddBoolOr([a.Not(), b.Not()]).OnlyEnforceIf(both.Not())
                    objective.append(round(ADJACENT_LOSS * SCALE) * both)

        if problem.purchase_budget_sgd is not None and problem.budget_is_hard:
            self._budget(model, problem, slots, x, size_of, policy)

        if hint:
            # A complete hint: every dish variable, chosen or not, so the solver starts from one whole plan.
            chosen = {(a.slot_id, a.role_id, a.recipe_id) for a in hint} | {
                (a.slot_id, None, a.recipe_id) for a in hint
            }
            for key, var in x.items():
                model.AddHint(var, 1 if key in chosen else 0)
        model.Minimize(sum(objective))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.limits.max_time_seconds
        solver.parameters.max_deterministic_time = self.limits.max_deterministic_time
        solver.parameters.num_workers = self.limits.workers
        solver.parameters.interleave_search = True
        solver.parameters.random_seed = 0
        solver.parameters.repair_hint = bool(hint)
        code = solver.Solve(model)
        wall = time.perf_counter() - started
        status = {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "infeasible",
            cp_model.MODEL_INVALID: "model_invalid",
        }.get(code, "unknown")
        if status not in {"optimal", "feasible"}:
            return MealCpSatResult(None, status, None, None, wall)
        assignments = [
            PlanningAssignment(slot_id=s, role_id=k, recipe_id=r)
            for (s, k, r), var in sorted(x.items(), key=lambda item: (item[0][0], str(item[0][1]), item[0][2]))
            if solver.Value(var)
        ]
        shopping = self._build_shopping(problem, assignments)
        report = self.validator.validate(problem, assignments, shopping)
        verdict = {"passed": "feasible", "indeterminate": "needs_data", "failed": "candidate_rejected"}[report.status]
        solution = FinalPlanningSolution(
            problem_id=problem.problem_id,
            status=verdict,
            assignments=assignments,
            shopping=shopping,
            validation=report,
            trace=PlanningTrace(
                algorithm="cp-sat-meal-planner",
                algorithm_version="meal-cp-sat-v1",
                deterministic=True,
                warnings=[
                    f"cp_sat_status={status}; objective={solver.ObjectiveValue() / SCALE:.3f}; "
                    f"best_bound={solver.BestObjectiveBound() / SCALE:.3f}; wall_seconds={wall:.2f}",
                    f"limits=max_time {self.limits.max_time_seconds}s, deterministic "
                    f"{self.limits.max_deterministic_time}, workers {self.limits.workers}, interleaved",
                ],
            ),
        )
        return MealCpSatResult(
            solution, status, solver.ObjectiveValue() / SCALE, solver.BestObjectiveBound() / SCALE, wall
        )

    def solve(
        self, problem: FinalPlanningProblem, *, hint: list[PlanningAssignment] | None = None
    ) -> FinalPlanningSolution:
        result = self.solve_exact(problem, hint=hint)
        if result.solution is not None:
            return result.solution
        report = self.validator.validate(problem, [], [])
        return FinalPlanningSolution(
            problem_id=problem.problem_id,
            # CP-SAT's infeasibility is a proof within this packet and model; unknown is not.
            status="infeasible" if result.status == "infeasible" else "candidate_rejected",
            assignments=[],
            shopping=[],
            validation=report,
            trace=PlanningTrace(
                algorithm="cp-sat-meal-planner",
                algorithm_version="meal-cp-sat-v1",
                deterministic=True,
                warnings=[f"cp_sat_status={result.status}; wall_seconds={result.wall_seconds:.2f}"],
            ),
        )

    def _budget(self, model, problem, slots, x, size_of, policy) -> None:
        """Reference shopping as constraints: one product per ingredient, whole packages, pantry deducted."""
        by_id = {r.recipe_id: r for r in problem.recipes}
        by_slot = {slot.slot_id: slot for slot in slots}
        demand: dict[tuple[str, str | None], list] = {}
        for (s, key, r_id), var in x.items():
            slot, recipe = by_slot[s], by_id[r_id]
            for n in range(1, len(slot.composition or [ANY_COURSE]) + 1):
                share = _share(policy, n, (key or MAIN_ROLE) == MAIN_ROLE)
                if share is None:
                    continue
                both = model.NewBoolVar("")
                model.AddBoolAnd([var, size_of[s, n]]).OnlyEnforceIf(both)
                model.AddBoolOr([var.Not(), size_of[s, n].Not()]).OnlyEnforceIf(both.Not())
                for item in recipe.ingredients:
                    if item.quantity is None:
                        raise ValueError("A budgeted CP-SAT plan needs every ingredient quantity")
                    amount = ceil(item.quantity * slot.servings * share / recipe.servings * SCALE)
                    demand.setdefault((item.ingredient_id, item.unit), []).append((amount, both))
        pantry = {p.ingredient_id: p for p in problem.pantry}
        costs = []
        for (ingredient, unit), terms in sorted(demand.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
            need = model.NewIntVar(0, sum(a for a, _ in terms), f"need[{ingredient}]")
            stock = pantry.get(ingredient)
            held = round(stock.quantity * SCALE) if stock and stock.quantity is not None and stock.unit == unit else 0
            model.Add(need >= sum(a * v for a, v in terms) - held)
            products = [
                p for p in problem.products if p.available and p.ingredient_id == ingredient and p.package_unit == unit
            ]
            if not products:
                model.Add(need == 0)  # an unpriceable demand cannot be bought within any budget
                continue
            picks = []
            for product in products:
                size = round(product.package_quantity * SCALE)
                most = ceil(sum(a for a, _ in terms) / max(size, 1)) + 1
                packages = model.NewIntVar(0, most, f"pk[{product.product_id}]")
                pick = model.NewBoolVar("")
                model.Add(packages * size >= need).OnlyEnforceIf(pick)
                model.Add(packages == 0).OnlyEnforceIf(pick.Not())
                picks.append(pick)
                costs.append(round(product.price_sgd * 100) * packages)
            model.AddExactlyOne(picks)
        model.Add(sum(costs) <= round(problem.purchase_budget_sgd * 100))


def _share(policy, dishes: int, is_main: bool) -> float | None:
    if dishes > len(policy.main_shares):
        return None
    if dishes == 1:
        return 1.0
    return policy.main_shares[dishes - 1] if is_main else policy.other_shares[dishes - 1]
