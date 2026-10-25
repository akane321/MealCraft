"""Validated annealing after a feasible product beam plan; table variety stays primary."""

from collections import defaultdict
from itertools import combinations

from app.planning.algorithm_objective import AlgorithmObjective
from app.planning.algorithm_reference import AnnealingPlanner
from app.planning.meal_beam import MealBeamLimits, MealBeamPlanner
from app.planning.near_duplicate_groups import DishGroups, NearDuplicatePolicy
from app.planning.recipe_quality import dish_kind
from app.schemas.planning_v2 import FinalPlanningSolution, PlanningTrace


class ProductTableObjective(AlgorithmObjective):
    def terms(self, problem, assignments, report, *, partial=False):
        # Member eligibility remains in the validator. Only scoring omits members,
        # so a future offline member-objective update cannot change product policy.
        table = problem.model_copy(update={"slots": [s.model_copy(update={"members": []}) for s in problem.slots]})
        return super().terms(table, assignments, report, partial=partial)


def adjacent_repetitions(problem, assignments):
    free = set(problem.uncounted_roles)
    if problem.repetition_rules is not None:
        free.update(problem.repetition_rules.repeat_ok_roles)
    meals = [
        {a.recipe_id for a in assignments if a.slot_id == slot.slot_id and a.role_id not in free}
        for slot in sorted(problem.slots, key=MealBeamPlanner._slot_key)
    ]
    filled = [meal for meal in meals if meal]
    return sum(len(left & right) for left, right in zip(filled, filled[1:], strict=False))


def improve_product_plan(problem, result, losses, *, steps=50, candidates=None, validate=None):
    """Keep a validated beam incumbent; never invoke CP-SAT or change member eligibility."""
    groups = defaultdict(list)
    for recipe in problem.recipes:
        groups[dish_kind(recipe.title)].append(recipe.recipe_id)
    grouped = tuple(tuple(sorted(ids)) for _, ids in sorted(groups.items()))
    near = tuple(sorted(pair for ids in grouped for pair in combinations(ids, 2)))
    keys = {r.recipe_id: r.recipe_id for r in problem.recipes}
    scales = {
        f"nutrition_{b.metric}_{b.scope}": max(abs(b.lower or 0), abs(b.upper or 0), 1)
        for b in problem.nutrition_bands
        if not b.hard
    }
    objective = ProductTableObjective(
        DishGroups(NearDuplicatePolicy("product-title-kinds", 1, 1, 1), grouped, near, ()),
        keys,
        losses,
        scales,
    )
    initial = FinalPlanningSolution(
        problem_id=problem.problem_id,
        status="feasible",
        assignments=result[0],
        shopping=result[1],
        validation=result[2],
        trace=PlanningTrace(algorithm="product-beam", algorithm_version="1", deterministic=True),
    )
    candidates = candidates or MealBeamPlanner(
        MealBeamLimits(candidates_per_role=len(problem.recipes), meal_options_per_slot=256), local_losses=losses
    )
    before = objective.score_validated(problem, initial.assignments, initial.validation)
    improved = AnnealingPlanner(objective, candidates, seed=0, steps=steps).solve(
        problem, initial=initial, validate=validate
    )
    after = objective.score_validated(problem, improved.assignments, improved.validation)
    before_repeats = adjacent_repetitions(problem, initial.assignments)
    proposed_repeats = adjacent_repetitions(problem, improved.assignments)
    retained = proposed_repeats > before_repeats
    proposed_score = after
    if retained:
        improved, after = initial, before
    return (improved.assignments, improved.shopping, improved.validation), {
        "algorithm": "beam+simulated-annealing",
        "seed": 0,
        "steps": steps,
        "variety_basis": "table-product-dish-kind",
        "before": before,
        "after": after,
        "improved": after < before,
        "adjacent_repetitions_before": before_repeats,
        "adjacent_repetitions_proposed": proposed_repeats,
        "adjacent_repetitions_after": before_repeats if retained else proposed_repeats,
        "retained_beam_reason": "adjacent_repetition_increased" if retained else None,
        "proposed_score": proposed_score,
    }
