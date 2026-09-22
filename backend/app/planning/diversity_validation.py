"""Recompute diversity from frozen roles and assignments, independent of search."""

from collections import Counter

from app.schemas.planning_v2 import PlanningConstraintCheck


def diversity_checks(problem, meals):
    """`meals` maps a slot to its assignment, or to the list of dishes it holds.

    Counting runs over dishes (ADR-0036 section 4): a recipe appears once in the
    horizon, core caps count dishes, two dishes of one meal never share a
    primary-protein group, and consecutive meals share none either.
    """
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
        dishes = meals.get(slot.slot_id)
        if dishes is None:
            continue
        if not isinstance(dishes, list):
            dishes = [dishes]
        if not dishes:
            continue
        meal_proteins = set()
        unclassified = False
        for assignment in dishes:
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
                unclassified = True
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
                unclassified = True
                continue
            proteins = set(roles.primary_proteins.values())
            if proteins & meal_proteins:
                checks.append(
                    PlanningConstraintCheck(
                        code="meal_duplicate_protein",
                        status="failed",
                        scope_id=slot.slot_id,
                        detail="Two dishes of one meal share a primary-protein group.",
                    )
                )
            if proteins & previous_proteins:
                checks.append(
                    PlanningConstraintCheck(
                        code="diversity_adjacent_protein",
                        status="failed",
                        scope_id=slot.slot_id,
                        detail="Consecutive occupied slots share a primary-protein group.",
                    )
                )
            meal_proteins |= proteins
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
        # An unclassified dish leaves the next meal's adjacency unknown, as before.
        previous_proteins = set() if unclassified else meal_proteins
    return checks
