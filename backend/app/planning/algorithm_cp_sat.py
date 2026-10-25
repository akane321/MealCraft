"""Offline CP-SAT table reference over generated meal options.

Uses count states only for interchangeable single-dish slots, otherwise ordered
meal-option products preserve dates, composition, nutrition and shopping trips.
This is deliberately a
bounded table model, not the scalable general household CP-SAT formulation.
"""

from itertools import combinations_with_replacement, product
from math import comb, prod
from time import perf_counter

from app.planning.algorithm_reference import domains, evaluate, require_min_dish_kinds
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.input_audit import require_finite_problem


class SharedScoreCpSat(DiversityAwareGreedyPlanner):
    def solve_exact(self, problem, *, max_states=10000, time_limit=10, min_dish_kinds=0):
        from ortools.sat.python import cp_model

        require_finite_problem(problem)
        require_min_dish_kinds(min_dish_kinds)
        if max_states < 1 or time_limit <= 0:
            raise ValueError("Limits must be positive")
        if {r.recipe_id for r in problem.recipes} != set(self.objective.keys):
            raise ValueError("Objective candidates differ from the problem")
        slots, pools = domains(self, problem)
        first = slots[0].model_dump(exclude={"slot_id", "planned_date"})
        compressible = (
            not (problem.diversity_policy or problem.perishable_days is not None or problem.nutrition_bands)
            and not any(
                s.composition
                or not s.required
                or s.trip is not None
                or s.model_dump(exclude={"slot_id", "planned_date"}) != first
                for s in slots
            )
            and not any(pool != pools[0] for pool in pools)
            and all(len(option) == 1 for option in pools[0])
        )
        started = perf_counter()
        total = (
            (comb(len(pools[0]) + len(slots) - 1, len(slots)) if pools[0] else 0)
            if compressible
            else prod(map(len, pools))
        )
        output = {
            "status": "limit_exceeded",
            "objective_priority": self.objective.priority,
            "min_dish_kinds": min_dish_kinds,
            "count_states": total,
            "score": None,
            "scope": "canonical count states" if compressible else "ordered generated meal options",
        }
        if total > max_states:
            return output
        rows, choices_by_row, unknown = [], [], 0
        selections = (
            (
                tuple(pools[0][index] for index in selected)
                for selected in combinations_with_replacement(range(len(pools[0])), len(slots))
            )
            if compressible
            else product(*pools)
        )
        for selected in selections:
            choices = tuple((s.slot_id, option) for s, option in zip(slots, selected, strict=True))
            score, _, _, report = evaluate(self, problem, choices, min_dish_kinds=min_dish_kinds)
            unknown += report.status == "indeterminate"
            if score is not None:
                rows.append(score)
                choices_by_row.append(choices)
        output["table_ms"] = (perf_counter() - started) * 1000
        output["unknown_states"] = unknown
        if not rows:
            output["status"] = "needs_data" if unknown else "no_valid_count_state"
            return output
        # Each component is replaced by its exact ordinal, preserving tuple
        # ordering without rounding floats or inventing a weighted objective.
        levels = [sorted({row[i] for row in rows}) for i in range(len(rows[0]))]
        ranks = [{value: index for index, value in enumerate(column)} for column in levels]
        model = cp_model.CpModel()
        chosen = model.NewIntVar(0, len(rows) - 1, "count_state")
        terms = [model.NewIntVar(0, len(column) - 1, f"term_{i}") for i, column in enumerate(levels)]
        model.AddAllowedAssignments(
            [chosen, *terms],
            [[j, *(ranks[i][v] for i, v in enumerate(row))] for j, row in enumerate(rows)],
        )
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        solve_start = perf_counter()
        for term in terms:
            remaining = time_limit - (perf_counter() - solve_start)
            if remaining <= 0:
                output["status"] = "unknown"
                return output
            solver.parameters.max_time_in_seconds = remaining
            model.Minimize(term)
            status = solver.Solve(model)
            if status != cp_model.OPTIMAL:
                output["status"] = solver.StatusName(status).lower()
                return output
            model.Add(term == solver.Value(term))
        score, assignments, shopping, report = evaluate(
            self, problem, choices_by_row[solver.Value(chosen)], min_dish_kinds=min_dish_kinds
        )
        if report.status != "passed" or score != rows[solver.Value(chosen)]:
            raise RuntimeError("CP-SAT result failed independent score verification")
        output.update(
            status="needs_data"
            if unknown
            else ("optimal_for_count_table" if compressible else "optimal_for_generated_options"),
            score=score,
            diversity=self.objective.diversity(problem, assignments),
            minimum_checkout_sgd=report.purchase_total_sgd
            if self.objective.priority == "price" and not unknown
            else None,
            assignments=[a.model_dump() for a in assignments],
            shopping=[row.model_dump() for row in shopping],
            solver_ms=(perf_counter() - solve_start) * 1000,
            total_ms=(perf_counter() - started) * 1000,
        )
        return output
