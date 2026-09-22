"""A slot's meal as dishes: roles, portion shares and the meal-time estimate (ADR-0036).

A slot without a composition is one dish at the whole meal, so every quantity
and time computed here equals the one-recipe-per-slot arithmetic it replaces.
"""

from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil

from app.schemas.planning_v2 import (
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningCompositionPolicy,
    PlanningRecipeCandidate,
    PlanningSlot,
)

MAIN_ROLE = "main"


def role_key(slot: PlanningSlot, assignment: PlanningAssignment) -> str | None:
    """The role an assignment fills, or None when it names no role of the slot."""
    if slot.composition is None:
        return MAIN_ROLE if assignment.role_id in (None, MAIN_ROLE) else None
    return assignment.role_id if assignment.role_id in {r.role_id for r in slot.composition} else None


def repetition_shortfalls(problem: FinalPlanningProblem, meals: list[list[str]]) -> list[str]:
    """Every stated repetition rule the meals break; `meals` lists each meal's recipe ids."""
    rules = problem.repetition_rules
    if rules is None:
        return []
    uses = Counter(recipe_id for meal in meals for recipe_id in meal)
    recipes = {r.recipe_id: r for r in problem.recipes}
    problems = []
    if rules.max_uses_per_recipe is not None:
        problems += [
            f"{r} used {n} times, the household allows {rules.max_uses_per_recipe}"
            for r, n in sorted(uses.items())
            if n > rules.max_uses_per_recipe
        ]
    for count in rules.recipe_counts:
        n = uses.get(count.recipe_id, 0)
        if n < count.min_uses:
            problems.append(f"{count.recipe_id} used {n} times, the household asked for at least {count.min_uses}")
        if count.max_uses is not None and n > count.max_uses:
            problems.append(f"{count.recipe_id} used {n} times, the household allows {count.max_uses}")
    for wanted in rules.ingredient_meals:
        n = sum(
            any(wanted.ingredient_id in {i.ingredient_id for i in recipes[r].ingredients} for r in meal if r in recipes)
            for meal in meals
        )
        if n < wanted.min_meals:
            problems.append(f"{wanted.ingredient_id} in {n} meals, the household asked for at least {wanted.min_meals}")
    return problems


def require_one_dish_slots(problem: FinalPlanningProblem) -> None:
    """Planners that fill one recipe per slot refuse composed meals rather than half-fill them."""
    if any(slot.composition is not None for slot in problem.slots):
        raise ValueError("This planner fills one dish per slot; composed meals need the multi-dish planner")


def portion_shares(policy: PlanningCompositionPolicy, role_ids: list[str | None]) -> dict[str | None, Fraction] | None:
    """Each filled role's share of the meal, or None for a meal outside the policy's sizes."""
    count = len(role_ids)
    if count == 0 or count > len(policy.main_shares):
        return None
    main = Fraction(str(policy.main_shares[count - 1]))
    other = policy.other_shares[count - 1]
    if count == 1:
        return {role_ids[0]: Fraction(1)}
    return {
        role: main if role == MAIN_ROLE else Fraction(str(other))  # type: ignore[arg-type]
        for role in role_ids
    }


def dish_servings(problem: FinalPlanningProblem, assignments: list[PlanningAssignment]) -> dict[int, Fraction]:
    """Servings each assignment is cooked for, by its index in `assignments`.

    A slot's household eats its meal once: each dish is scaled to
    `servings * share`. Assignments to unknown slots, or meals outside the
    policy's sizes, are left out; the validator reports them.
    """
    slots = {slot.slot_id: slot for slot in problem.slots}
    by_slot: dict[str, list[int]] = defaultdict(list)
    for index, assignment in enumerate(assignments):
        by_slot[assignment.slot_id].append(index)
    servings: dict[int, Fraction] = {}
    for slot_id, indexes in by_slot.items():
        slot = slots.get(slot_id)
        if slot is None:
            continue
        keys = [role_key(slot, assignments[i]) for i in indexes]
        shares = portion_shares(problem.composition_policy, keys)
        if shares is None or len(set(keys)) != len(keys):
            continue
        for index, key in zip(indexes, keys, strict=True):
            servings[index] = slot.servings * shares[key]
    return servings


def hands_on_and_waiting(recipe: PlanningRecipeCandidate, policy: PlanningCompositionPolicy) -> tuple[float, float]:
    if recipe.prep_minutes is None:
        return float(recipe.total_time_minutes), 0.0
    fraction = policy.hands_on_cook_fraction
    hands_on = recipe.prep_minutes + fraction * recipe.cook_minutes
    waiting = (1 - fraction) * recipe.cook_minutes + recipe.passive_minutes
    return hands_on, waiting


def meal_minutes(recipes: list[PlanningRecipeCandidate], policy: PlanningCompositionPolicy) -> int:
    """One cook: hands-on parts in sequence, waiting overlapped, a switch-over per extra dish.

    A single dish is its own total time, unrounded, so one-dish meals keep
    today's limits exactly. Several dishes round up to `round_to_minutes`.
    """
    if len(recipes) == 1:
        return recipes[0].total_time_minutes
    parts = [hands_on_and_waiting(recipe, policy) for recipe in recipes]
    estimate = sum(h for h, _ in parts) + max(w for _, w in parts) + policy.switch_minutes * (len(recipes) - 1)
    step = policy.round_to_minutes
    return ceil(round(estimate, 6) / step) * step


if __name__ == "__main__":
    # The worked example of ADR-0036 section 3, and a one-dish meal unchanged.
    def dish(prep, cook, passive):
        return PlanningRecipeCandidate.model_validate(
            {
                "recipe_id": f"r{prep}{cook}",
                "title": "t",
                "servings": 4,
                "allowed_meal_types": ["dinner"],
                "total_time_minutes": prep + cook + passive,
                "prep_minutes": prep,
                "cook_minutes": cook,
                "passive_minutes": passive,
                "ingredients": [{"ingredient_id": "x"}],
                "nutrients_per_serving": dict.fromkeys(
                    ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g"), 0
                ),
            }
        )

    policy = PlanningCompositionPolicy()
    assert meal_minutes([dish(15, 25, 0), dish(10, 22, 0), dish(15, 30, 0)], policy) == 105
    assert meal_minutes([dish(3, 20, 0)], policy) == 23
    assert portion_shares(policy, ["main", "side", "soup"]) == {
        "main": Fraction(3, 5),
        "side": Fraction(2, 5),
        "soup": Fraction(2, 5),
    }
    print("ok")
