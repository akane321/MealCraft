"""Native meal-option CP-SAT reference; no complete-plan enumeration.

Quantity scale includes recipe-serving denominators; nutrition uses a 0.001
grid and ranking 0.0001. Unsupported precision/policies are refused.
"""

from collections import defaultdict
from math import gcd, isfinite, lcm
from time import perf_counter

from app.planning.algorithm_reference import domains, evaluate, require_min_dish_kinds
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.input_audit import require_finite_problem
from app.planning.meal_beam import MealState, assignments_of
from app.planning.meal_composition import dish_servings, meal_shares


def integer(value, scale=1000):
    scaled = value * scale
    if not isfinite(scaled) or abs(scaled - round(scaled)) > 1e-7 + 1e-12 * abs(scaled):
        raise ValueError("Coefficient precision exceeds the native model's declared grid")
    return round(scaled)


class NativeSharedScoreCpSat(DiversityAwareGreedyPlanner):
    def solve_exact(self, problem, *, time_limit=15, optimize=True, min_dish_kinds=0):
        from ortools.sat.python import cp_model

        require_finite_problem(problem)
        require_min_dish_kinds(min_dish_kinds)
        if not isfinite(time_limit) or time_limit <= 0:
            raise ValueError("Time limit must be finite and positive")
        if set(self.objective.keys) != {r.recipe_id for r in problem.recipes}:
            raise ValueError("Objective candidates differ from the problem")
        if problem.diversity_policy:
            raise ValueError("Legacy diversity policy needs native encoding before comparison")
        norms = {
            f"nutrition_{b.metric}_{b.scope}": integer(self.objective.scales[f"nutrition_{b.metric}_{b.scope}"])
            for b in problem.nutrition_bands
            if not b.hard
        }
        soft_scale = lcm(*norms.values()) if norms else 1
        started = perf_counter()
        slots, pools = domains(self, problem)
        recipes = {r.recipe_id: r for r in problem.recipes}
        quantity_scale = 100000 * lcm(*(r.servings for r in problem.recipes))
        if quantity_scale > 10**9:
            raise ValueError("Recipe serving denominators exceed the supported integer scale")
        model = cp_model.CpModel()
        options, selections = {}, {}
        demand = defaultdict(list)
        counts = defaultdict(list)
        rule_counts, ingredient_meals = defaultdict(list), defaultdict(list)
        soft_terms = []
        nutrition = defaultdict(list)
        empty_terms, rank_terms = [], []
        units = {}
        upper_quantity = defaultdict(int)
        for slot, pool in zip(slots, pools, strict=True):
            chosen = []
            for index, dishes in enumerate(pool):
                assignments = assignments_of(MealState(((slot.slot_id, dishes),)))
                # Local validator filters all meal-local hard rules. Horizon
                # and daily nutrition are encoded below, not checked as meals.
                local = problem.model_copy(
                    update={
                        "slots": [slot],
                        "purchase_budget_sgd": None,
                        "repetition_rules": None,
                        "nutrition_bands": [b for b in problem.nutrition_bands if b.scope in {"per_dish", "per_slot"}],
                    }
                )
                shopping = self.candidates._build_shopping(local, assignments)
                report = self.candidates.validator.validate(local, assignments, shopping)
                if report.status == "indeterminate":
                    raise ValueError("Indeterminate meal evidence prevents a native optimality claim")
                if report.status != "passed":
                    continue
                x = model.NewBoolVar(f"meal_{slot.slot_id}_{index}")
                for check in report.checks:
                    if check.code.startswith("nutrition_") and not check.hard:
                        soft_terms.append(integer(max(0, -check.margin)) * (soft_scale // norms[check.code]) * x)
                chosen.append(x)
                options[slot.slot_id, index] = dishes
                selections[slot.slot_id, index] = x
                serving = dish_servings(local, assignments)
                local_demand = defaultdict(float)
                for n, assignment in enumerate(assignments):
                    recipe = recipes[assignment.recipe_id]
                    share = float(serving.get(n, slot.servings))
                    for ingredient in recipe.ingredients:
                        if ingredient.quantity is None or ingredient.unit is None:
                            raise ValueError("Native model requires known ingredient quantities")
                        key = (ingredient.ingredient_id, ingredient.unit, slot.trip)
                        local_demand[key] += ingredient.quantity * share / recipe.servings
                    if assignment.role_id not in problem.uncounted_roles:
                        counts[assignment.recipe_id].append(x)
                    if assignment.role_id not in problem.uncounted_roles:
                        rule_counts[assignment.recipe_id].append(x)
                    rank_terms.append(integer(self.objective.ranking[assignment.recipe_id], 10000) * x)
                for key, value in local_demand.items():
                    amount = integer(value, quantity_scale)
                    demand[key].append((amount, x))
                    upper_quantity[key] += amount
                    ingredient, unit, _ = key
                    if ingredient in units and units[ingredient] != unit:
                        raise ValueError("Native model requires one unit per ingredient")
                    units[ingredient] = unit
                for ingredient in {
                    item.ingredient_id
                    for a in assignments
                    if a.role_id not in problem.uncounted_roles
                    for item in recipes[a.recipe_id].ingredients
                }:
                    ingredient_meals[ingredient].append(x)
                present = {role for role, _ in dishes}
                empty = sum(not r.required and r.role_id not in present for r in slot.composition or [])
                if not dishes and not slot.required:
                    empty = 1
                empty_terms.append(empty * x)
                shares = meal_shares(local, slot, dishes, recipes) if dishes else {}
                for metric in {b.metric for b in problem.nutrition_bands}:
                    value = sum(
                        getattr(recipes[rid].nutrients_per_serving, metric)
                        * (1 if len(dishes) == 1 else float(shares[role]))
                        for role, rid in dishes
                    )
                    nutrition[slot.slot_id, metric].append(integer(value) * x)
            model.AddExactlyOne(chosen)

        symmetry_pairs = 0
        if optimize and not problem.nutrition_bands:
            # Permute only truly identical meal settings within a shopping trip.
            # No date-dependent nutrition is present; quantities, counts and
            # objective terms are unchanged by these permutations.
            previous = {}
            for slot in slots:
                signature = repr(slot.model_dump(exclude={"slot_id", "planned_date"}))
                available = tuple((index, dishes) for (sid, index), dishes in options.items() if sid == slot.slot_id)
                group = (signature, available)
                index_sum = sum(index * var for (sid, index), var in selections.items() if sid == slot.slot_id)
                if group in previous:
                    model.Add(previous[group] <= index_sum)
                    symmetry_pairs += 1
                previous[group] = index_sum

        rules = problem.repetition_rules
        if rules:
            if rules.max_uses_per_recipe is not None:
                for values in rule_counts.values():
                    model.Add(sum(values) <= rules.max_uses_per_recipe)
            for rule in rules.recipe_counts:
                count = sum(rule_counts[rule.recipe_id])
                model.Add(count >= rule.min_uses)
                if rule.max_uses is not None:
                    model.Add(count <= rule.max_uses)
            for rule in rules.ingredient_meals:
                model.Add(sum(ingredient_meals[rule.ingredient_id]) >= rule.min_meals)

        # Ordered representative recurrence exactly matches AlgorithmObjective.
        used, representative = {}, {}
        keys = self.objective.keys
        related = self.objective.near | self.objective.unknown
        max_dishes = sum(max((len(o) for o in pool), default=0) for pool in pools)
        recipe_counts = {}
        for rid in sorted(keys, key=keys.get):
            count = model.NewIntVar(0, max_dishes, f"count_{rid}")
            model.Add(count == sum(counts[rid]))
            recipe_counts[rid] = count
            used[rid] = model.NewBoolVar(f"used_{rid}")
            model.Add(count >= 1).OnlyEnforceIf(used[rid])
            model.Add(count == 0).OnlyEnforceIf(used[rid].Not())
            conflicts = [v for other, v in representative.items() if tuple(sorted((keys[rid], keys[other]))) in related]
            rep = model.NewBoolVar(f"representative_{rid}")
            model.Add(rep <= used[rid])
            for conflict in conflicts:
                model.Add(rep + conflict <= 1)
            model.Add(rep >= used[rid] - sum(conflicts))
            representative[rid] = rep
        model.Add(sum(representative.values()) >= min_dish_kinds)
        repeat_terms = []
        for rid, count in recipe_counts.items():
            repeated = model.NewIntVar(0, max_dishes * max_dishes, f"repeat_{rid}")
            model.AddAllowedAssignments([count, repeated], [(n, n * (n - 1) // 2) for n in range(max_dishes + 1)])
            repeat_terms.append(repeated)
        ids = sorted(keys)
        for i, left in enumerate(ids):
            for right in ids[i + 1 :]:
                if tuple(sorted((keys[left], keys[right]))) in related:
                    repeated = model.NewIntVar(0, max_dishes * max_dishes, "near_repeat")
                    model.AddMultiplicationEquality(repeated, [recipe_counts[left], recipe_counts[right]])
                    repeat_terms.append(repeated)

        # Each trip consumes only the pantry left after earlier trips.
        pantry = {p.ingredient_id: p for p in problem.pantry}
        divisors = {}
        if optimize:
            for ingredient, unit in units.items():
                coefficients = [
                    amount for (name, _, _), values in demand.items() if name == ingredient for amount, _ in values
                ]
                coefficients += [
                    integer(p.package_quantity, quantity_scale)
                    for p in problem.products
                    if p.ingredient_id == ingredient and p.package_unit == unit and p.available
                ]
                p = pantry.get(ingredient)
                if p and p.quantity is not None and p.unit == unit:
                    coefficients.append(integer(p.quantity, quantity_scale))
                divisors[ingredient] = max(1, gcd(*coefficients))
        stock = {}
        costs = []
        trip_costs = defaultdict(list)
        for key in sorted(demand, key=lambda k: (k[0], k[1], k[2] or 0)):
            ingredient, unit, _ = key
            divisor = divisors.get(ingredient, 1)
            cap = upper_quantity[key] // divisor
            qty = model.NewIntVar(0, cap, "quantity")
            model.Add(qty == sum((amount // divisor) * var for amount, var in demand[key]))
            if ingredient not in stock:
                p = pantry.get(ingredient)
                stock[ingredient] = (
                    integer(p.quantity, quantity_scale) // divisor
                    if p and p.quantity is not None and p.unit == unit
                    else 0
                )
            remaining = model.NewIntVar(0, cap, "remaining")
            model.AddMaxEquality(remaining, [0, qty - stock[ingredient]])
            stock_next = model.NewIntVar(
                0,
                integer(pantry[ingredient].quantity, quantity_scale) // divisor
                if ingredient in pantry and pantry[ingredient].quantity is not None and pantry[ingredient].unit == unit
                else 0,
                "stock",
            )
            model.AddMaxEquality(stock_next, [0, stock[ingredient] - qty])
            stock[ingredient] = stock_next
            choices = []
            for p in problem.products:
                if p.ingredient_id != ingredient or p.package_unit != unit or not p.available:
                    continue
                size, price = integer(p.package_quantity, quantity_scale) // divisor, integer(p.price_sgd, 100)
                packages = model.NewIntVar(0, (cap + size - 1) // size, "packages")
                model.AddDivisionEquality(packages, remaining + size - 1, size)
                choices.append(packages * price)
            if not choices:
                model.Add(remaining == 0)
            else:
                cost = model.NewIntVar(
                    0, max(1, cap) * max(integer(p.price_sgd, 100) for p in problem.products), "cost"
                )
                model.AddMinEquality(cost, choices)
                costs.append(cost)
                trip_costs[key[2]].append(cost)
        checkout = sum(costs)
        if problem.budget_is_hard and problem.purchase_budget_sgd is not None:
            for values in trip_costs.values():
                model.Add(sum(values) <= integer(problem.purchase_budget_sgd, 100))
        for band in problem.nutrition_bands:
            if band.scope in {"per_dish", "per_slot"}:
                continue  # Already independently checked while creating options.
            days = sorted({s.planned_date for s in slots})
            groups = (
                [[s for s in slots if s.planned_date == day] for day in days] if band.scope == "per_day" else [slots]
            )
            for group in groups:
                divisor = (
                    1
                    if band.scope == "per_day"
                    else (len(slots) if band.average_basis == "selected_slots" else len(days))
                )
                if any(not s.required for s in group):
                    raise ValueError("Native aggregate nutrition currently requires required meal slots")
                value = sum(sum(nutrition[s.slot_id, band.metric]) for s in group)
                if not band.hard:
                    # Deviation in milli-nutrient units, averaged then rounded
                    # half-to-even like the validator's three-decimal margin.
                    bound = 10**12
                    deviation = model.NewIntVar(0, bound, "soft_deviation")
                    margins = [0]
                    if band.lower is not None:
                        margins.append(integer(band.lower) * divisor - value)
                    if band.upper is not None:
                        margins.append(value - integer(band.upper) * divisor)
                    model.AddMaxEquality(deviation, margins)
                    quotient = model.NewIntVar(0, bound, "soft_quotient")
                    remainder = model.NewIntVar(0, divisor - 1, "soft_remainder")
                    model.AddDivisionEquality(quotient, deviation, divisor)
                    model.AddModuloEquality(remainder, deviation, divisor)
                    parity = model.NewIntVar(0, 1, "soft_parity")
                    model.AddModuloEquality(parity, quotient, 2)
                    up = model.NewBoolVar("round_up")
                    model.AddAllowedAssignments(
                        [remainder, parity, up],
                        [
                            (r, p, int(2 * r > divisor or (2 * r == divisor and p == 1)))
                            for r in range(divisor)
                            for p in (0, 1)
                        ],
                    )
                    code = f"nutrition_{band.metric}_{band.scope}"
                    soft_terms.append((quotient + up) * (soft_scale // norms[code]))
                    continue
                if band.lower is not None:
                    model.Add(value >= integer(band.lower) * divisor)
                if band.upper is not None:
                    model.Add(value <= integer(band.upper) * divisor)
        terms = [
            sum(empty_terms),
            -sum(representative.values()),
            sum(repeat_terms),
            sum(soft_terms),
            sum(rank_terms),
            checkout,
        ]
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 4 if optimize else 1
        solver.parameters.random_seed = 0
        output = {
            "status": "unknown",
            "objective_priority": self.objective.priority,
            "min_dish_kinds": min_dish_kinds,
            "scope": "native generated meal options",
            "meal_variables": len(selections),
            "build_ms": (perf_counter() - started) * 1000,
            "symmetry_pairs": symmetry_pairs,
            "workers": solver.parameters.num_search_workers,
            "stage_ms": [],
        }
        for term in self.objective.ordered(terms):
            if optimize and isinstance(term, int):
                output["stage_ms"].append(0.0)
                continue
            remaining_time = time_limit - (perf_counter() - started)
            if remaining_time <= 0:
                return output
            solver.parameters.max_time_in_seconds = remaining_time
            model.Minimize(term)
            stage_started = perf_counter()
            status = solver.Solve(model)
            output["stage_ms"].append((perf_counter() - stage_started) * 1000)
            if status != cp_model.OPTIMAL:
                output["status"] = solver.StatusName(status).lower()
                return output
            model.Add(term == solver.Value(term))
        choices = tuple(
            (s.slot_id, options[key])
            for s in slots
            for key, var in selections.items()
            if key[0] == s.slot_id and solver.Value(var)
        )
        score, assignments, shopping, report = evaluate(self, problem, choices, min_dish_kinds=min_dish_kinds)
        if report.status != "passed" or score is None:
            return {**output, "status": "validation_rejected"}
        modeled = [solver.Value(t) for t in terms]
        modeled[3] /= soft_scale
        modeled[4] /= 10000
        modeled = self.objective.ordered(modeled)
        if any(abs(a - b) > 1e-7 for a, b in zip(score, modeled, strict=True)):
            return {**output, "status": "score_mismatch", "score": score, "modeled_score": modeled}
        return {
            **output,
            "status": "optimal_for_native_model",
            "score": score,
            "minimum_checkout_sgd": report.purchase_total_sgd if self.objective.priority == "price" else None,
            "assignments": [a.model_dump() for a in assignments],
            "shopping": [r.model_dump() for r in shopping],
            "total_ms": (perf_counter() - started) * 1000,
        }
