"""Offline LNS: release several meals and repair with the native CP-SAT model.

Every repair retains the whole horizon for package, trip and member arithmetic.
Iterations bound the search; repairs have no wall-clock cutoff. This does not
change the product planner or claim global optimality for a partial neighborhood.
"""

from random import Random
from time import perf_counter

from app.planning.algorithm_reference import evaluate
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat


class LargeNeighborhoodPlanner(DiversityAwareGreedyPlanner):
    def __init__(self, objective, candidates=None, *, seed=0, iterations=8, destroy_size=2):
        super().__init__(objective, candidates)
        if any(type(value) is not int or value < 1 for value in (iterations, destroy_size)):
            raise ValueError("Iterations and destroy size must be positive integers")
        self.seed, self.iterations, self.destroy_size = seed, iterations, destroy_size
        self.repairs = []

    def solve(self, problem, *, initial=None):
        self.repairs = []
        best = initial.model_copy(deep=True) if initial is not None else super().solve(problem)
        best.trace.algorithm = "large-neighborhood-search"
        # A seeded neighborhood schedule does not make parallel CP-SAT tie choices deterministic.
        best.trace.deterministic = False
        if best.status != "feasible":
            best.trace.warnings.append("No feasible seed; LNS did not run.")
            return best
        slots = sorted(problem.slots, key=self.candidates._slot_key)

        def choices(assignments):
            return tuple(
                (s.slot_id, tuple((a.role_id, a.recipe_id) for a in assignments if a.slot_id == s.slot_id))
                for s in slots
            )

        current = choices(best.assignments)
        score, _, shopping, report = evaluate(self, problem, current)
        if score is None:
            raise ValueError("LNS seed failed independent validation")
        best.shopping, best.validation = shopping, report
        rng = Random(self.seed)
        for step in range(self.iterations):
            released = set(rng.sample([s.slot_id for s in slots], min(self.destroy_size, len(slots))))
            fixed = {slot_id: dishes for slot_id, dishes in current if slot_id not in released}
            started = perf_counter()
            repair = NativeSharedScoreCpSat(self.objective, self.candidates)
            try:
                result = repair.solve_exact(problem, time_limit=None, fixed_choices=fixed)
            except ValueError as error:
                # Unsupported native input is diagnostic, never a proof of infeasibility.
                result = {"status": "unsupported", "reason": str(error)}
            row = {
                "iteration": step,
                "released": sorted(released),
                "status": result["status"],
                "elapsed_ms": (perf_counter() - started) * 1000,
                "accepted": False,
                "workers": result.get("workers"),
                "solver_seed": 0,
            }
            if "reason" in result:
                row["reason"] = result["reason"]
            self.repairs.append(row)
            if result["status"] != "optimal_for_native_model":
                best.trace.warnings.append(f"LNS repair {step}: {result['status']}; kept validated incumbent.")
                if result["status"] == "unsupported" or len(released) == len(slots):
                    break
                continue
            from app.schemas.planning_v2 import PlanningAssignment

            trial = choices([PlanningAssignment.model_validate(a) for a in result["assignments"]])
            trial_score, assignments, shopping, report = evaluate(self, problem, trial)
            if any(dict(trial)[slot_id] != dishes for slot_id, dishes in fixed.items()):
                raise RuntimeError("LNS repair changed a fixed meal")
            if trial_score is None or trial_score != tuple(result["score"]):
                raise RuntimeError("LNS repair failed independent score verification")
            if trial_score < score:
                current, score = trial, trial_score
                best.assignments, best.shopping, best.validation = assignments, shopping, report
                row["accepted"] = True
            if len(released) == len(slots):
                break
        best.trace.warnings.append(
            f"seed={self.seed}; repairs={len(self.repairs)}; iterations={self.iterations}; "
            f"destroy_size={self.destroy_size}; native workers=4; solver_seed=0; "
            "parallel tie choices may vary; no global optimality claim"
        )
        return best
