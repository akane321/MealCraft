"""Bounded deterministic beam search using the existing reference scoring policy."""

from dataclasses import dataclass

from app.planning.constraint_compiler import compile_search_domains
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_scoring import local_recipe_loss
from app.planning.search_bounds import SearchBounds
from app.schemas.planning_v2 import FinalPlanningProblem, FinalPlanningSolution, PlanningAssignment, PlanningTrace


@dataclass(frozen=True)
class BeamLimits:
    width: int = 32
    max_expansions: int = 10000

    def __post_init__(self):
        if self.width < 1 or self.max_expansions < 1:
            raise ValueError("Beam limits must be positive")


@dataclass(frozen=True)
class SearchState:
    choices: tuple[tuple[str, str], ...] = ()
    loss: float = 0.0


class BeamPlanner(FinalScopeReferencePlanner):
    """Retain multiple partial plans; independently validate every retained completion.

    Shopping construction is reused from the reference, while validation remains
    separate. This is a bounded search, not an optimality or infeasibility proof.
    """

    def __init__(self, limits: BeamLimits | None = None):
        super().__init__()
        self.limits = limits or BeamLimits()

    def solve(self, problem: FinalPlanningProblem) -> FinalPlanningSolution:
        compiled = compile_search_domains(problem)
        domains = {slot.slot_id: slot for slot in compiled.slots}
        recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
        states = [SearchState()]
        expansions = 0
        pruned = False
        exhausted = False
        ordered_slots = sorted(problem.slots, key=self._slot_key)
        bounds = SearchBounds(problem, ordered_slots, domains)
        nutrition_pruned = dominated = 0
        # Chronological order preserves the reference policy's adjacency meaning.
        for slot_index, slot in enumerate(ordered_slots):
            domain = domains[slot.slot_id]
            candidates = list(domain.eligible_recipe_ids)
            if not domain.must_assign:
                candidates.append(None)
            next_states = []
            for state in states:
                for recipe_id in candidates:
                    if expansions >= self.limits.max_expansions:
                        exhausted = True
                        break
                    expansions += 1
                    if recipe_id is None:
                        next_states.append(state)
                        continue
                    previous = [chosen for _, chosen in state.choices]
                    loss = (
                        local_recipe_loss(
                            recipes[recipe_id],
                            max_time_minutes=slot.max_time_minutes,
                            health_preferences=problem.health_preferences,
                        )
                        + previous.count(recipe_id) * 0.10
                        + (0.35 if previous and previous[-1] == recipe_id else 0.0)
                    )
                    next_states.append(SearchState(state.choices + ((slot.slot_id, recipe_id),), state.loss + loss))
                if exhausted:
                    break
            if exhausted:
                states = []  # A partial horizon must never be returned as a complete plan.
                break
            survivors = {}
            for state in next_states:
                if not bounds.nutrition_possible(state, slot_index + 1):
                    nutrition_pruned += 1
                    continue
                key = bounds.dominance_key(state)
                previous = survivors.get(key)
                if previous is not None:
                    dominated += 1
                if previous is None or (state.loss, state.choices) < (previous.loss, previous.choices):
                    survivors[key] = state
            next_states = sorted(
                survivors.values(),
                key=lambda state: (bounds.loss_lower_bound(state, slot_index + 1), state.loss, state.choices),
            )
            pruned = pruned or len(next_states) > self.limits.width
            states = next_states[: self.limits.width]
            if not states:
                break

        results = []
        for state in states:
            assignments = [PlanningAssignment(slot_id=slot, recipe_id=recipe) for slot, recipe in state.choices]
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
        if exhausted or not states:
            status = "candidate_rejected"
        return FinalPlanningSolution(
            problem_id=problem.problem_id,
            status=status,
            assignments=assignments,
            shopping=shopping,
            validation=report,
            trace=PlanningTrace(
                algorithm="deterministic-beam-search",
                algorithm_version="beam-reference-policy-v1",
                deterministic=True,
                warnings=[
                    f"beam_width={self.limits.width}; max_expansions={self.limits.max_expansions}; "
                    f"expansions={expansions}",
                    f"beam_pruned={pruned}; expansion_limit_reached={exhausted}; completed_candidates={len(results)}",
                    f"nutrition_pruned={nutrition_pruned}; dominated={dominated}",
                    "Uses reference local loss and repetition penalties. No global infeasibility or optimality claim.",
                ],
            ),
        )
