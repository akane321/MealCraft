"""Expose the implemented Sprint 2 algorithm ladder through baseline scoring.

The search implementations live in :mod:`app.planning`; this module only
adapts their validated assignments to ``BaselineResponse`` and the shared
mapping/recomputation pipeline.  It deliberately does not add missing rungs
(LNS and the optional genetic algorithm).
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.baseline_output import (
    BaselineDish,
    BaselineIngredient,
    BaselineMeal,
    BaselinePlan,
    BaselineResponse,
)
from app.evaluation.multidish_runner import build_problem, greedy_selector, rule_constraints
from app.evaluation.pure_llm_baseline import (
    BaselineResources,
    EpisodeResult,
    GenerationResult,
    ModelUsage,
    load_episodes,
    load_resources,
    result_payload,
    score_generation,
)
from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.algorithm_search import GraspPlanner, LocalSearchPlanner, SharedObjectiveBeamPlanner
from app.planning.diversity_greedy import DiversityAwareGreedyPlanner
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.meal_composition import dish_servings
from app.planning.native_algorithm_cp_sat import NativeSharedScoreCpSat
from app.planning.near_duplicate_groups import DishGroups, NearDuplicatePolicy
from app.schemas.planning_v2 import FinalPlanningProblem, FinalPlanningSolution, PlanningAssignment, PlanningTrace


@dataclass(frozen=True)
class AlgorithmArm:
    system_id: str
    rung: str
    solve: Callable[[FinalPlanningProblem, AlgorithmObjective], FinalPlanningSolution]


def _planner(planner_type):
    return lambda problem, objective: planner_type(objective).solve(problem)


def _naive(problem: FinalPlanningProblem, _objective: AlgorithmObjective) -> FinalPlanningSolution:
    return greedy_selector(problem)


def _cp_sat(problem: FinalPlanningProblem, objective: AlgorithmObjective) -> FinalPlanningSolution:
    result = NativeSharedScoreCpSat(objective).solve_exact(problem)
    if result["status"] != "optimal_for_native_model":
        return _empty_solution(problem, f"CP-SAT ended with {result['status']}")
    assignments = [PlanningAssignment.model_validate(row) for row in result["assignments"]]
    reference = FinalScopeReferencePlanner()
    shopping = reference._build_shopping(problem, assignments)
    validation = reference.validator.validate(problem, assignments, shopping)
    return FinalPlanningSolution(
        problem_id=problem.problem_id,
        status="feasible" if validation.status == "passed" else "candidate_rejected",
        assignments=assignments,
        shopping=shopping,
        validation=validation,
        trace=PlanningTrace(
            algorithm="native-shared-score-cp-sat",
            algorithm_version="algorithm-ladder-dev-v1",
            deterministic=True,
            warnings=[f"status={result['status']}; scope={result['scope']}"],
        ),
    )


ARMS = {
    arm.system_id: arm
    for arm in (
        AlgorithmArm("algorithm-rung-0-naive-greedy", "0", _naive),
        AlgorithmArm("algorithm-rung-1-diversity-greedy", "1", _planner(DiversityAwareGreedyPlanner)),
        AlgorithmArm("algorithm-rung-2-grasp", "2", _planner(GraspPlanner)),
        AlgorithmArm("algorithm-rung-3-local-search", "3-local", _planner(LocalSearchPlanner)),
        AlgorithmArm("algorithm-rung-3-simulated-annealing", "3-annealing", _planner(AnnealingPlanner)),
        AlgorithmArm("algorithm-current-shared-objective-beam", "current-beam", _planner(SharedObjectiveBeamPlanner)),
        AlgorithmArm("algorithm-rung-6-cp-sat", "6", _cp_sat),
    )
}


def implemented_system_ids() -> tuple[str, ...]:
    return tuple(ARMS)


def generate(episode: dict[str, Any], *, system_id: str) -> GenerationResult:
    if system_id not in ARMS:
        raise ValueError(f"unknown algorithm baseline arm: {system_id}")
    started = time.perf_counter()
    response = _plan_response(episode, ARMS[system_id])
    return GenerationResult(
        response=response,
        attempts=1,
        elapsed_seconds=time.perf_counter() - started,
        usage=ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0),
        parse_errors=(),
    )


def run_episode(episode: dict[str, Any], *, system_id: str, resources: BaselineResources) -> EpisodeResult:
    return score_generation(
        episode,
        generate(episode, system_id=system_id),
        system_id=system_id,
        resources=resources,
    )


def _plan_response(episode: dict[str, Any], arm: AlgorithmArm) -> BaselineResponse:
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id, or id")
    understood = rule_constraints(episode)
    if understood.clarify or understood.household_size is None:
        return BaselineResponse(episode_id=episode_id, system_id=arm.system_id, status="clarification")
    problem = build_problem(episode, understood)
    solution = arm.solve(problem, _objective(problem))
    if solution.status != "feasible" or solution.validation.status != "passed":
        return BaselineResponse(episode_id=episode_id, system_id=arm.system_id, status="infeasible")
    return _response_from_solution(problem, solution, system_id=arm.system_id)


def _objective(problem: FinalPlanningProblem) -> AlgorithmObjective:
    recipe_ids = sorted(recipe.recipe_id for recipe in problem.recipes)
    keys = {recipe_id: recipe_id for recipe_id in recipe_ids}
    groups = DishGroups(
        policy=NearDuplicatePolicy("algorithm-baseline-recipe-id-v1", 1.0, 1.0, 1.0),
        groups=tuple((recipe_id,) for recipe_id in recipe_ids),
        unknown_pairs=(),
        near_pairs=(),
    )
    denominator = max(1, len(recipe_ids) - 1)
    ranking = {recipe_id: index / denominator for index, recipe_id in enumerate(recipe_ids)}
    return AlgorithmObjective(groups, keys, ranking)


def _response_from_solution(
    problem: FinalPlanningProblem, solution: FinalPlanningSolution, *, system_id: str
) -> BaselineResponse:
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    servings = dish_servings(problem, solution.assignments)
    meals = []
    for index, assignment in enumerate(solution.assignments):
        recipe = recipes[assignment.recipe_id]
        scale = float(servings[index]) / recipe.servings
        meals.append(
            BaselineMeal(
                slot_id=assignment.slot_id,
                role_id=assignment.role_id,
                dishes=[
                    BaselineDish(
                        name=recipe.title,
                        cooking_time_minutes=recipe.total_time_minutes,
                        ingredients=[
                            BaselineIngredient(name=item.ingredient_id, quantity_g=item.quantity * scale)
                            for item in recipe.ingredients
                            if item.quantity is not None and item.quantity > 0 and item.unit == "g"
                        ],
                    )
                ],
            )
        )
    return BaselineResponse(
        episode_id=problem.problem_id,
        system_id=system_id,
        status="plan",
        plan=BaselinePlan(meals=meals),
    )


def _empty_solution(problem: FinalPlanningProblem, warning: str) -> FinalPlanningSolution:
    reference = FinalScopeReferencePlanner()
    validation = reference.validator.validate(problem, [], [])
    return FinalPlanningSolution(
        problem_id=problem.problem_id,
        status="candidate_rejected",
        assignments=[],
        shopping=[],
        validation=validation,
        trace=PlanningTrace(
            algorithm="native-shared-score-cp-sat",
            algorithm_version="algorithm-ladder-dev-v1",
            deterministic=True,
            warnings=[warning],
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", choices=implemented_system_ids(), required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resources = load_resources()
    results = [
        run_episode(episode, system_id=args.arm, resources=resources) for episode in load_episodes(args.episodes)
    ]
    report = {
        "system_id": args.arm,
        "model": None,
        "episodes": [result_payload(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.arm}: {sum(result.valid_output for result in results)}/{len(results)} valid outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
