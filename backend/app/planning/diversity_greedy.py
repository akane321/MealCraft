"""Developer algorithm-ladder arm using shared meal candidates and validation.

Fractional completion bounds reserve spending for later meals; one-step
lookahead checks exact packages. Neither proves whole-horizon feasibility.
"""

import json
from collections import defaultdict
from dataclasses import asdict

from app.planning.algorithm_budget import CompletionBudget
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.input_audit import require_finite_problem
from app.planning.meal_beam import (
    MealBeamPlanner,
    MealOption,
    MealState,
    assignments_of,
    day_permitted,
    horizon_permitted,
    request_progress,
    requests_reachable,
)
from app.schemas.planning_v2 import FinalPlanningSolution, PlanningTrace


class DiversityAwareGreedyPlanner:
    def __init__(self, objective: AlgorithmObjective, candidates: MealBeamPlanner | None = None):
        self.objective = objective
        self.candidates = candidates or MealBeamPlanner(local_losses=objective.ranking)

    def choose(self, trials):
        return min(trials, key=lambda item: (item[0], item[1]))[2]

    def solve(self, problem) -> FinalPlanningSolution:
        require_finite_problem(problem)
        if {r.recipe_id for r in problem.recipes} != set(self.objective.keys):
            raise ValueError("Objective and planner must use the same candidate recipes")
        slots = sorted(problem.slots, key=self.candidates._slot_key)
        options = {s.slot_id: self.candidates.meal_options(problem, s) for s in slots}
        for slot in slots:
            if not slot.required and slot.locked_recipe_id is None and not slot.locked_roles:
                options[slot.slot_id].append(MealOption((), 0))
        state = MealState()
        completion = CompletionBudget(problem, slots, options)
        evaluated = 0
        stopped = False

        def extension(previous, slot, option, position):
            if not horizon_permitted(problem, previous, option.dishes):
                return None
            trial = MealState(previous.choices + ((slot.slot_id, option.dishes),))
            if not requests_reachable(problem, trial, len(slots) - position - 1) or not completion.permits(trial):
                return None
            day_closed = position == len(slots) - 1 or slots[position + 1].planned_date != slot.planned_date
            if not day_permitted(problem, trial, slot, day_closed):
                return None
            assignments = assignments_of(trial)
            shopping = self.candidates._build_shopping(problem, assignments)
            if any(
                row.remaining_quantity is None or (row.remaining_quantity > 0 and row.selected_product_id is None)
                for row in shopping
            ):
                return None
            costs = defaultdict(float)
            for row in shopping:
                costs[row.trip] += row.purchase_cost_sgd
            cost = max((round(value * 100) for value in costs.values()), default=0)
            if (
                problem.budget_is_hard
                and problem.purchase_budget_sgd is not None
                and cost > round(problem.purchase_budget_sgd * 100)
            ):
                return None
            return trial

        for position, slot in enumerate(slots):
            trials = []
            for option in options[slot.slot_id]:
                evaluated += 1
                trial = extension(state, slot, option, position)
                if trial is None:
                    continue
                if position + 1 < len(slots):
                    following = slots[position + 1]
                    if not any(
                        extension(trial, following, next_option, position + 1) is not None
                        for next_option in options[following.slot_id]
                    ):
                        continue
                assignments = assignments_of(trial)
                # Recompute nutrition for the selected prefix; this report is
                # ordering evidence only and never certifies a complete plan.
                prefix = problem.model_copy(update={"slots": slots[: position + 1]})
                shopping = self.candidates._build_shopping(prefix, assignments)
                report = self.candidates.validator.validate(prefix, assignments, shopping)
                score = (
                    -request_progress(problem, trial),
                    self.objective.terms(prefix, assignments, report, partial=True),
                )
                trials.append((score, trial.choices, trial))
            if not trials:
                stopped = True
                break
            state = self.choose(trials)
        assignments = assignments_of(state)
        shopping = self.candidates._build_shopping(problem, assignments)
        report = self.candidates.validator.validate(problem, assignments, shopping)
        status = {"passed": "feasible", "failed": "candidate_rejected", "indeterminate": "needs_data"}[report.status]
        if stopped:
            status = "candidate_rejected" if report.status != "indeterminate" else "needs_data"
        if status == "feasible":
            self.objective.score_validated(problem, assignments, report)
        return FinalPlanningSolution(
            problem_id=problem.problem_id,
            status=status,
            assignments=assignments,
            shopping=shopping,
            validation=report,
            trace=PlanningTrace(
                algorithm="diversity-aware-greedy",
                algorithm_version="algorithm-ladder-dev-v1",
                deterministic=True,
                candidate_limit=self.candidates.limits.candidates_per_role,
                warnings=[
                    "Developer arm; fractional completion bound and one-step checkout lookahead; no optimality proof.",
                    f"policy={json.dumps(asdict(self.objective.groups.policy), sort_keys=True)}",
                    f"candidate_limits={json.dumps(asdict(self.candidates.limits), sort_keys=True)}",
                    f"options_evaluated={evaluated}; stopped={stopped}; "
                    f"unknown_similarity_pairs={len(self.objective.unknown)}",
                    f"ranking_losses={json.dumps(self.objective.ranking, sort_keys=True)}",
                    f"nutrition_scales={json.dumps(self.objective.scales, sort_keys=True)}",
                ],
            ),
        )
