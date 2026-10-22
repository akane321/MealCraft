"""Bounded developer search arms; all acceptance uses the shared validator."""

from random import Random

from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.meal_beam import MealOption, MealState, assignments_of, day_permitted, horizon_permitted


class SharedObjectiveBeamPlanner(DiversityAwareGreedyPlanner):
    """Experimental beam, not the product beam's existing scoring policy."""

    def __init__(self, objective, candidates=None, *, width=8, max_expansions=1000):
        super().__init__(objective, candidates)
        if width < 1 or max_expansions < 1:
            raise ValueError("Beam limits must be positive")
        self.width, self.max_expansions = width, max_expansions

    def solve(self, problem):
        # Retain a validated incumbent even when the beam exhausts its budget.
        best = super().solve(problem)
        best.trace.algorithm = "shared-objective-beam"
        best_score = (
            self.objective.score_validated(problem, best.assignments, best.validation)
            if best.status == "feasible"
            else None
        )
        slots = sorted(problem.slots, key=self.candidates._slot_key)
        states = [MealState()]
        expanded = 0
        for position, slot in enumerate(slots):
            options = self.candidates.meal_options(problem, slot)
            if not slot.required and slot.locked_recipe_id is None and not slot.locked_roles:
                options.append(MealOption((), 0))
            trials = []
            prefix = problem.model_copy(update={"slots": slots[: position + 1]})
            for state in states:
                for option in options:
                    if expanded >= self.max_expansions:
                        break
                    expanded += 1
                    if not horizon_permitted(problem, state, option.dishes):
                        continue
                    trial = MealState(state.choices + ((slot.slot_id, option.dishes),))
                    closed = position == len(slots) - 1 or slots[position + 1].planned_date != slot.planned_date
                    if not day_permitted(problem, trial, slot, closed):
                        continue
                    assignments = assignments_of(trial)
                    shopping = self.candidates._build_shopping(prefix, assignments)
                    report = self.candidates.validator.validate(prefix, assignments, shopping)
                    if any(
                        row.remaining_quantity is None
                        or (row.remaining_quantity > 0 and row.selected_product_id is None)
                        for row in shopping
                    ):
                        continue
                    if problem.budget_is_hard and problem.purchase_budget_sgd is not None:
                        if round(report.purchase_total_sgd * 100) > round(problem.purchase_budget_sgd * 100):
                            continue
                    score = self.objective.terms(prefix, assignments, report)
                    if position == len(slots) - 1:
                        if report.status == "passed" and (best_score is None or score < best_score):
                            best_score = score
                            best.status = "feasible"
                            best.assignments, best.shopping, best.validation = assignments, shopping, report
                    trials.append((score, trial.choices, trial))
            states = [t[2] for t in sorted(trials, key=lambda t: (t[0], t[1]))[: self.width]]
            if not states or expanded >= self.max_expansions:
                break
        best.trace.warnings.append(
            f"width={self.width}; expansions={expanded}; max_expansions={self.max_expansions}; "
            "includes greedy incumbent; no optimality proof"
        )
        return best


class RandomizedGreedy(DiversityAwareGreedyPlanner):
    def __init__(self, objective, candidates, rng, top_k):
        super().__init__(objective, candidates)
        self.rng, self.top_k = rng, top_k

    def choose(self, trials):
        return self.rng.choice(sorted(trials, key=lambda item: (item[0], item[1]))[: self.top_k])[2]


class GraspPlanner(DiversityAwareGreedyPlanner):
    def __init__(self, objective, candidates=None, *, seed=0, restarts=8, top_k=3):
        super().__init__(objective, candidates)
        if restarts < 1 or top_k < 1:
            raise ValueError("Restart count and restricted candidate list must be positive")
        self.seed, self.restarts, self.top_k = seed, restarts, top_k

    def solve(self, problem):
        # Include the deterministic baseline so extra restarts cannot worsen it.
        results = [super().solve(problem)]
        rng = Random(self.seed)
        for _ in range(self.restarts - 1):
            results.append(RandomizedGreedy(self.objective, self.candidates, rng, self.top_k).solve(problem))
        feasible = [result for result in results if result.status == "feasible"]
        best = (
            min(feasible, key=lambda r: self.objective.score_validated(problem, r.assignments, r.validation))
            if feasible
            else results[0]
        )
        best.trace.algorithm = "grasp"
        best.trace.warnings.append(f"seed={self.seed}; restarts={self.restarts}; top_k={self.top_k}")
        return best


class LocalSearchPlanner(DiversityAwareGreedyPlanner):
    def __init__(self, objective, candidates=None, *, max_evaluations=100):
        super().__init__(objective, candidates)
        if max_evaluations < 1:
            raise ValueError("Evaluation budget must be positive")
        self.max_evaluations = max_evaluations

    def solve(self, problem):
        best = super().solve(problem)
        best.trace.algorithm = "local-search"
        if best.status != "feasible":
            best.trace.warnings.append("No feasible seed; local search did not run.")
            return best
        slots = sorted(problem.slots, key=self.candidates._slot_key)
        options = {s.slot_id: [o.dishes for o in self.candidates.meal_options(problem, s)] for s in slots}
        choices = tuple(
            (s.slot_id, tuple((a.role_id, a.recipe_id) for a in best.assignments if a.slot_id == s.slot_id))
            for s in slots
        )
        score = self.objective.score_validated(problem, best.assignments, best.validation)
        evaluated = 0
        while evaluated < self.max_evaluations:
            improved = False
            neighbors = []
            for i, (slot_id, _) in enumerate(choices):
                for dishes in options[slot_id]:
                    neighbors.append(choices[:i] + ((slot_id, dishes),) + choices[i + 1 :])
            for i in range(len(choices)):
                for j in range(i + 1, len(choices)):
                    left, right = choices[i], choices[j]
                    if right[1] in options[left[0]] and left[1] in options[right[0]]:
                        swapped = list(choices)
                        swapped[i], swapped[j] = (left[0], right[1]), (right[0], left[1])
                        neighbors.append(tuple(swapped))
            for trial in neighbors:
                if evaluated >= self.max_evaluations:
                    break
                if trial == choices:
                    continue
                evaluated += 1
                assignments = assignments_of(MealState(trial))
                shopping = self.candidates._build_shopping(problem, assignments)
                report = self.candidates.validator.validate(problem, assignments, shopping)
                if report.status != "passed":
                    continue
                trial_score = self.objective.score_validated(problem, assignments, report)
                if trial_score < score:
                    choices, score = trial, trial_score
                    best.assignments, best.shopping, best.validation = assignments, shopping, report
                    improved = True
                    break
            if not improved:
                break
        best.trace.warnings.append(
            f"evaluations={evaluated}; max_evaluations={self.max_evaluations}; no optimality proof"
        )
        return best
