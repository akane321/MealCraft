"""Recompute diversity from frozen roles and assignments, independent of search."""

from collections import Counter

from app.schemas.planning_v2 import PlanningConstraintCheck


def diversity_checks(problem, assigned_by_slot):
    policy = problem.diversity_policy
    if policy is None:
        return []
    checks = []
    counts = Counter()
    seen_recipes = set()
    previous_proteins = set()
    meal_order = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}
    recipes = {r.recipe_id: r for r in problem.recipes}
    packet_cores = {core for item in policy.classifications.values() for core in item.core_ingredient_ids}
    for slot in sorted(problem.slots, key=lambda s: (s.planned_date, meal_order[s.meal_type], s.slot_id)):
        assignment = assigned_by_slot.get(slot.slot_id)
        if assignment is None:
            continue
        recipe_id = assignment.recipe_id
        if recipe_id in seen_recipes:
            checks.append(
                PlanningConstraintCheck(
                    code="diversity_recipe_repeat",
                    status="failed",
                    scope_id=slot.slot_id,
                    detail="A recipe may appear only once in the horizon.",
                )
            )
        seen_recipes.add(recipe_id)
        roles = policy.classifications.get(recipe_id)
        if roles is None:
            checks.append(
                PlanningConstraintCheck(
                    code="diversity_classification",
                    status="indeterminate",
                    scope_id=slot.slot_id,
                    detail="Selected recipe needs versioned core and primary-protein classification.",
                )
            )
            previous_proteins = set()
            continue
        recipe = recipes.get(recipe_id)
        if recipe is None or not set(roles.core_ingredient_ids) <= {i.ingredient_id for i in recipe.ingredients}:
            checks.append(
                PlanningConstraintCheck(
                    code="diversity_classification",
                    status="failed",
                    scope_id=slot.slot_id,
                    detail="Classification names an ingredient absent from the frozen recipe.",
                )
            )
            previous_proteins = set()
            continue
        proteins = set(roles.primary_proteins.values())
        if proteins & previous_proteins:
            checks.append(
                PlanningConstraintCheck(
                    code="diversity_adjacent_protein",
                    status="failed",
                    scope_id=slot.slot_id,
                    detail="Consecutive occupied slots share a primary-protein group.",
                )
            )
        previous_proteins = proteins
        for ingredient in sorted({i.ingredient_id for i in recipe.ingredients} & packet_cores):
            counts[ingredient] += 1
            if counts[ingredient] > policy.max_slots_per_core_ingredient:
                checks.append(
                    PlanningConstraintCheck(
                        code="diversity_core_cap",
                        status="failed",
                        scope_id=slot.slot_id,
                        actual=counts[ingredient],
                        limit=policy.max_slots_per_core_ingredient,
                        detail=f"Core ingredient {ingredient} exceeds its slot cap.",
                    )
                )
    return checks
