"""Run the deterministic strong-rule Sprint 2 baseline.

This arm uses the existing rule parser, frozen candidate-packet adapter, strong
rule selector, and independent planning validator.  Its BaselineResponse then
passes through the same ingredient mapping, coverage verification, nutrition,
allergen, and frozen whole-package pricing pipeline as the other baselines.
It makes no model, retrieval, web, or external-tool calls.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from app.evaluation.baseline_output import (
    BaselineDish,
    BaselineIngredient,
    BaselineMeal,
    BaselinePlan,
    BaselineResponse,
)
from app.evaluation.multidish_runner import build_problem, rule_constraints, strong_rule_selector
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
from app.planning.meal_composition import dish_servings

SYSTEM_ID = "strong-rule-baseline"


def generate(episode: dict[str, Any]) -> GenerationResult:
    """Plan once with deterministic rules and return the common output shape."""
    started = time.perf_counter()
    response = _plan_response(episode)
    return GenerationResult(
        response=response,
        attempts=1,
        elapsed_seconds=time.perf_counter() - started,
        usage=ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0),
        parse_errors=(),
    )


def run_episode(episode: dict[str, Any], *, resources: BaselineResources) -> EpisodeResult:
    """Run rules only, then use the shared baseline evaluation pipeline."""
    generated = generate(episode)
    return score_generation(episode, generated, system_id=SYSTEM_ID, resources=resources)


def _plan_response(episode: dict[str, Any]) -> BaselineResponse:
    episode_id = str(episode.get("episode_id") or episode.get("scenario_id") or episode.get("id") or "")
    if not episode_id:
        raise ValueError("episode has no episode_id, scenario_id, or id")

    understood = rule_constraints(episode)
    if understood.clarify or understood.household_size is None:
        return BaselineResponse(episode_id=episode_id, system_id=SYSTEM_ID, status="clarification")

    problem = build_problem(episode, understood)
    solution = strong_rule_selector(problem)
    required_roles_filled = all(
        {assignment.role_id for assignment in solution.assignments if assignment.slot_id == slot.slot_id}
        >= {role.role_id for role in slot.composition or [] if role.required}
        for slot in problem.slots
    )
    if not required_roles_filled or solution.validation.status != "passed":
        return BaselineResponse(episode_id=episode_id, system_id=SYSTEM_ID, status="infeasible")

    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    servings = dish_servings(problem, solution.assignments)
    meals: list[BaselineMeal] = []
    for index, assignment in enumerate(solution.assignments):
        recipe = recipes[assignment.recipe_id]
        cooked_servings = servings[index]
        ingredients = [
            BaselineIngredient(
                name=item.ingredient_id,
                quantity_g=float(cooked_servings) * item.quantity / recipe.servings,
            )
            for item in recipe.ingredients
            if item.quantity is not None and item.quantity > 0
        ]
        meals.append(
            BaselineMeal(
                slot_id=assignment.slot_id,
                role_id=assignment.role_id,
                dishes=[
                    BaselineDish(
                        name=recipe.title,
                        cooking_time_minutes=recipe.total_time_minutes,
                        ingredients=ingredients,
                    )
                ],
            )
        )
    return BaselineResponse(
        episode_id=episode_id,
        system_id=SYSTEM_ID,
        status="plan",
        plan=BaselinePlan(meals=meals),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resources = load_resources()
    results = [run_episode(episode, resources=resources) for episode in load_episodes(args.episodes)]
    report = {
        "system_id": SYSTEM_ID,
        "model": None,
        "episodes": [result_payload(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"strong-rule baseline: {sum(result.valid_output for result in results)}/{len(results)} valid outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
