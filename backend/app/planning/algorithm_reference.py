"""Offline reference and annealing over the same bounded meal-option domain."""

from itertools import product
from math import exp, prod
from random import Random

from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.input_audit import require_finite_problem
from app.planning.meal_beam import MealState, assignments_of


def domains(planner, problem):
    slots = sorted(problem.slots, key=planner.candidates._slot_key)
    result = []
    for slot in slots:
        options = [option.dishes for option in planner.candidates.meal_options(problem, slot)]
        if not slot.required and slot.locked_recipe_id is None and not slot.locked_roles:
            options.append(())
        result.append(tuple(dict.fromkeys(options)))
    return slots, result


def require_min_dish_kinds(value):
    if type(value) is not int or value < 0:
        raise ValueError("min_dish_kinds must be a nonnegative integer")


def evaluate(planner, problem, choices, *, min_dish_kinds=0, validate=None):
    assignments = assignments_of(MealState(choices))
    shopping = planner.candidates._build_shopping(problem, assignments)
    report = (validate or planner.candidates.validator.validate)(problem, assignments, shopping)
    score = planner.objective.score_validated(problem, assignments, report) if report.status == "passed" else None
    if score is not None:
        kind_index = 2 if planner.objective.priority == "price" else 1
        if -score[kind_index] < min_dish_kinds:
            score = None
    return score, assignments, shopping, report


class EnumeratedReference(DiversityAwareGreedyPlanner):
    """Exact only over generated options and the fixed shopping policy."""

    def solve_reference(self, problem, *, max_combinations=10000, min_dish_kinds=0):
        require_finite_problem(problem)
        require_min_dish_kinds(min_dish_kinds)
        if max_combinations < 1:
            raise ValueError("Combination limit must be positive")
        if {r.recipe_id for r in problem.recipes} != set(self.objective.keys):
            raise ValueError("Objective candidates differ from the problem")
        slots, options = domains(self, problem)
        total = prod(map(len, options))
        result = {
            "status": "limit_exceeded",
            "total": total,
            "checked": 0,
            "unknown": 0,
            "score": None,
            "objective_priority": self.objective.priority,
            "min_dish_kinds": min_dish_kinds,
        }
        if total > max_combinations:
            return result
        for selection in product(*options):
            choices = tuple((s.slot_id, dishes) for s, dishes in zip(slots, selection, strict=True))
            score, _, _, report = evaluate(self, problem, choices, min_dish_kinds=min_dish_kinds)
            result["checked"] += 1
            result["unknown"] += report.status == "indeterminate"
            if score is not None and (result["score"] is None or score < result["score"]):
                result["score"] = score
        result["status"] = (
            "needs_data"
            if result["unknown"]
            else "optimal_for_generated_options"
            if result["score"] is not None
            else "no_valid_generated_assignment"
        )
        if self.objective.priority == "price" and result["status"] == "optimal_for_generated_options":
            result["minimum_checkout_sgd"] = result["score"][0] / 100
        return result


class AnnealingPlanner(DiversityAwareGreedyPlanner):
    def __init__(self, objective, candidates=None, *, seed=0, steps=200):
        super().__init__(objective, candidates)
        if steps < 1:
            raise ValueError("Step count must be positive")
        self.seed, self.steps = seed, steps

    def solve(self, problem, *, initial=None, validate=None):
        # A product adapter may supply its validated beam result. Never mutate it
        # or trust a validation report produced for a different request.
        best = super().solve(problem) if initial is None else initial.model_copy(deep=True)
        best.trace.algorithm = "simulated-annealing"
        if best.status != "feasible":
            best.trace.warnings.append("No feasible seed; annealing did not run.")
            return best
        if initial is not None or validate is not None:
            shopping = self.candidates._build_shopping(problem, best.assignments)
            report = (validate or self.candidates.validator.validate)(problem, best.assignments, shopping)
            if report.status != "passed":
                raise ValueError("Initial annealing plan does not pass the current problem's validation")
            best.shopping, best.validation = shopping, report
        slots, options = domains(self, problem)
        current = tuple(
            (s.slot_id, tuple((a.role_id, a.recipe_id) for a in best.assignments if a.slot_id == s.slot_id))
            for s in slots
        )
        score = best_score = self.objective.score_validated(problem, best.assignments, best.validation)
        rng = Random(self.seed)
        worse = 0
        for step in range(self.steps):
            if not slots:
                break
            trial = list(current)
            i = rng.randrange(len(slots))
            if len(slots) > 1 and rng.random() < 0.5:
                j = rng.randrange(len(slots))
                if trial[j][1] not in options[i] or trial[i][1] not in options[j]:
                    continue
                trial[i], trial[j] = (slots[i].slot_id, current[j][1]), (slots[j].slot_id, current[i][1])
            else:
                trial[i] = (slots[i].slot_id, rng.choice(options[i]))
            trial = tuple(trial)
            candidate_score, assignments, shopping, report = evaluate(self, problem, trial, validate=validate)
            if candidate_score is None:
                continue
            # Final ranking remains lexicographic. Acceptance uses the first
            # differing component, scaled by the current magnitude, not a new
            # weighted objective. This exploration policy is experimental.
            delta = next(((b - a) / max(1, abs(a)) for a, b in zip(score, candidate_score, strict=True) if a != b), 0)
            temperature = 1.0 * (0.01 ** (step / max(1, self.steps - 1)))
            if delta <= 0 or rng.random() < exp(-delta / temperature):
                worse += delta > 0
                current, score = trial, candidate_score
                if score < best_score:
                    best_score = score
                    best.assignments, best.shopping, best.validation = assignments, shopping, report
        best.trace.warnings.append(
            f"seed={self.seed}; steps={self.steps}; temperature=1.0..0.01; "
            f"accepted_worse={worse}; feasible-only moves; no optimality proof"
        )
        return best
