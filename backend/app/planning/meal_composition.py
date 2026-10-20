"""A slot's meal as dishes: roles, portion shares and the meal-time estimate (ADR-0036).

A slot without a composition is one dish at the whole meal, so every quantity
and time computed here equals the one-recipe-per-slot arithmetic it replaces.
"""

from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil

from app.data import meal_structure
from app.planning.vegetable_led import candidate_vegetable_led, catalog_vegetable_led, vegetable_role
from app.schemas.planning_v2 import (
    NON_MEAL_ROLES,
    STAPLE_ROLE,
    FinalPlanningProblem,
    PlanningAssignment,
    PlanningCompositionPolicy,
    PlanningMealRole,
    PlanningRecipeCandidate,
    PlanningSlot,
    core_role,
    structured,
)

MAIN_ROLE = "main"
# The tags a meal's structure rests on. One the model decided is read only once its batch is reviewed.
GATED_TAGS = ("meal_role", "contains_staple", "protein_sources")


def unreviewed(recipe) -> bool:
    """A catalog recipe whose meal role, staple or protein sources the model decided and nobody has reviewed yet
    (`python -m app.data.recipe_tags --accept-batch`): the structured planner treats it as untagged."""
    estimated = getattr(recipe, "estimated", None) or {}
    return any(
        (estimated.get(name) or {}).get("method") == "llm" and (estimated.get(name) or {}).get("reviewed") is not True
        for name in GATED_TAGS
    )


def meal_role_of(recipe) -> str | None:
    """Admissible role: retain catalog facts, but unknown main sources cannot satisfy no-repeat constraints."""
    role = getattr(recipe, "meal_role", None)
    unknown_sources = (
        role in {"protein_main", "one_bowl"} and hasattr(recipe, "protein_sources") and recipe.protein_sources is None
    )
    return None if unreviewed(recipe) or unknown_sources else role


def role_admits(role: PlanningMealRole, recipe: PlanningRecipeCandidate) -> bool:
    """A role takes a recipe of one of its courses, or for a structured role of one of its meal roles; a vegetable
    role only one led by vegetables (ADR-0054). A recipe with no meal-role tag fills no structured role."""
    if role.meal_roles:
        admitted = meal_role_of(recipe) in role.meal_roles
    else:
        admitted = recipe.course in role.courses
    return admitted and (not vegetable_role(role.role_id) or candidate_vegetable_led(recipe))


def catalog_role_admits(role: PlanningMealRole, recipe) -> bool:
    """`role_admits` for a catalog recipe (`app.models.recipe.Recipe`), as a swap reads it."""
    if role.meal_roles:
        admitted = meal_role_of(recipe) in role.meal_roles
    else:
        admitted = (recipe.course or "main") in role.courses
    return admitted and (not vegetable_role(role.role_id) or catalog_vegetable_led(recipe))


def fills_staple(recipe) -> bool:
    """A one-bowl dish, or one tagged as carrying its staple, fills the meal's staple too (ADR-0070 section 2)."""
    return getattr(recipe, "meal_role", None) == "one_bowl" or getattr(recipe, "contains_staple", None) is True


def structured_slot(slot: PlanningSlot) -> bool:
    return structured(slot.composition)


def role_base(role_id: str | None) -> str:
    """ "main-2" -> "main": the kind of dish a role id names."""
    return (role_id or MAIN_ROLE).split("-")[0]


def equipment_met(needs, missing) -> bool:
    """Every group of the recipe's equipment has an item the kitchen has; no needs or nothing missing is met."""
    if not needs or not missing:
        return True
    absent = set(missing)
    return all(set(group) - absent for group in needs)


def meal_shares(
    problem: FinalPlanningProblem, slot: PlanningSlot, dishes, recipes: dict | None = None
) -> dict[str | None, Fraction] | None:
    """Each filled role's share of the meal: `portion_shares` for a meal of course roles (unchanged), else the
    structured shares (data/planning/meal-structure-v1.json). `dishes` are (role id, recipe id) pairs."""
    if not structured_slot(slot):
        return portion_shares(problem.composition_policy, [role for role, _ in dishes])
    recipes = recipes if recipes is not None else {r.recipe_id: r for r in problem.recipes}
    roles = [role for role, _ in dishes]
    mains = [role for role in roles if role_base(role) == MAIN_ROLE]
    bowl = STAPLE_ROLE not in roles and any(
        role_base(role) == MAIN_ROLE and fills_staple(recipes[recipe_id]) for role, recipe_id in dishes
    )
    return structured_shares(
        problem.composition_policy, roles, len(mains), sum(role_base(r) == "vegetable" for r in roles), bowl, dishes
    )


def structured_shares(policy, roles, mains: int, vegetables: int, bowl: bool, dishes) -> dict[str | None, Fraction]:
    table = policy.structured_shares or meal_structure.portion_shares()
    if len(roles) == 1:
        return {roles[0]: Fraction(1)}  # one dish is the whole meal, as a one-dish slot is

    def pick(values, count: int) -> Fraction:
        values = values if isinstance(values, list) else [values]
        return Fraction(str(values[min(count, len(values)) - 1]))

    shares: dict[str | None, Fraction] = {}
    for role in roles:
        base = role_base(role)
        if base == MAIN_ROLE:
            shares[role] = pick(table["protein_main"], mains)
        elif base == "vegetable":
            shares[role] = pick(table["vegetable"], vegetables)
        elif base == "soup":
            shares[role] = pick(table["soup"], 1)
        else:
            shares[role] = pick(table["staple"], 1)
    if bowl:
        # The dish that carries the staple is a whole serving: its rice or noodles are the meal's staple.
        for role, _ in dishes:
            if role_base(role) == MAIN_ROLE:
                shares[role] = pick(table["one_bowl"], 1)
                break
    return shares


def meal_energy(dishes, recipes: dict, shares) -> float:
    """kcal per serving of the meal: its dishes at their shares."""
    return sum(
        float(shares[role]) * recipes[recipe_id].nutrients_per_serving.calories_kcal for role, recipe_id in dishes
    )


def real_meal_issues(
    slot: PlanningSlot, dishes, recipes: dict, shares
) -> list[tuple[str, str, float | None, float | None]]:
    """Every real-meal rule a structured meal breaks (ADR-0070 sections 3 and 4) as (code, detail, actual, limit).

    Empty for a meal of course roles. The search keeps only meals with none; the validator reports each. A lunch
    or dinner has a filling core (a protein main and its staple, or a dish that carries its staple), no non-meal
    dish, at most one dish moved from its default, distinct protein sources across its mains and its energy
    floor; a structured breakfast only fills its roles with dishes of their tags."""
    roles = slot.composition or []
    if not structured(roles):
        return []
    issues: list[tuple[str, str, float | None, float | None]] = []
    filled = {role: recipes[recipe_id] for role, recipe_id in dishes}
    by_id = {role.role_id: role for role in roles}
    for role_id, recipe in filled.items():
        role = by_id.get(role_id)
        if role is not None and meal_role_of(recipe) not in (role.meal_roles or ()):
            issues.append(
                ("meal_role_tag", f"A {recipe.meal_role or 'untagged'} dish cannot fill {role_id}.", None, None)
            )
    meal = slot.meal_type in ("lunch", "dinner")
    core = core_role(roles) if meal else None
    dish = filled.get(core.role_id) if core is not None else None
    bowl = dish is not None and fills_staple(dish)
    vegetable = next((role for role in roles if role_base(role.role_id) == "vegetable"), None)
    for role in roles:
        # Beside a dish that carries its staple, the staple and the first vegetable dish may stay empty.
        exempt = bowl and (role.role_id == STAPLE_ROLE or role is vegetable)
        if role.required and role.role_id not in filled and not exempt:
            issues.append(("meal_role_missing", f"Required role {role.role_id} is empty.", None, None))
    if not meal:
        return issues
    for role_id, recipe in filled.items():
        base = role_base(role_id)
        if recipe.meal_role in NON_MEAL_ROLES:
            detail = f"A {recipe.meal_role} dish is no part of a {slot.meal_type}."
            issues.append(("meal_nonmeal_dish", detail, None, None))
        elif recipe.meal_role == "salad" and base != "vegetable":
            issues.append(("meal_nonmeal_dish", "A salad fills only the vegetable dish.", None, None))
        elif recipe.meal_role == "soup" and base != "soup":
            issues.append(("meal_nonmeal_dish", "A soup fills only the soup.", None, None))
    has_staple = STAPLE_ROLE in filled
    if dish is None:
        issues.append(("meal_filling_core", "The meal has no filling core.", None, None))
    elif bowl and has_staple:
        issues.append(("meal_filling_core", "A dish that carries its staple takes no second staple.", None, None))
    elif not bowl and not (has_staple and meal_role_of(dish) == "protein_main"):
        issues.append(("meal_filling_core", "A protein main needs a staple.", None, None))
    # The planner may move one dish from the default (section 0.2): an optional dish left out, or the vegetable
    # dish beside a dish that carries its staple (section 0.4). That staple left out is no move.
    moved = sum(1 for role in roles if not role.required and role.role_id not in filled)
    moved += bool(vegetable is not None and vegetable.required and vegetable.role_id not in filled)
    if moved > 1:
        issues.append(("meal_dish_count", f"{moved} dishes moved from the meal's default; one may be.", moved, 1))
    mains = [recipe for role_id, recipe in filled.items() if role_base(role_id) == MAIN_ROLE]
    if any(recipe.protein_sources is None for recipe in mains):
        issues.append(("meal_protein_unknown", "A protein main has unknown protein sources.", None, None))
    sources = [set(recipe.protein_sources) for recipe in mains if recipe.protein_sources is not None]
    if sum(len(group) for group in sources) != len(set().union(*sources)):
        issues.append(("meal_protein_repeat", "Two protein mains share a protein source.", None, None))
    if slot.min_energy_kcal is not None and shares is not None:
        energy = meal_energy(dishes, recipes, shares)
        if energy - slot.min_energy_kcal < -1e-6:
            detail = "The meal gives less than its energy floor per serving."
            issues.append(("meal_energy_floor", detail, round(energy, 1), slot.min_energy_kcal))
    return issues


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
    recipes = {recipe.recipe_id: recipe for recipe in problem.recipes}
    by_slot: dict[str, list[int]] = defaultdict(list)
    for index, assignment in enumerate(assignments):
        by_slot[assignment.slot_id].append(index)
    servings: dict[int, Fraction] = {}
    for slot_id, indexes in by_slot.items():
        slot = slots.get(slot_id)
        if slot is None:
            continue
        keys = [role_key(slot, assignments[i]) for i in indexes]
        if structured_slot(slot) and any(assignments[i].recipe_id not in recipes for i in indexes):
            continue
        shares = meal_shares(
            problem, slot, [(key, assignments[i].recipe_id) for key, i in zip(keys, indexes, strict=True)], recipes
        )
        if shares is None or len(set(keys)) != len(keys):
            continue
        for index, key in zip(indexes, keys, strict=True):
            servings[index] = Fraction(str(slot.servings)) * shares[key]
    return servings


def hands_on_and_waiting(recipe: PlanningRecipeCandidate, policy: PlanningCompositionPolicy) -> tuple[float, float]:
    if recipe.prep_minutes is None:
        return float(recipe.total_time_minutes), 0.0
    if policy.staple_hands_off_cook and getattr(recipe, "meal_role", None) == STAPLE_ROLE:
        # An idealization (ADR-0068): the rice cooker or the pot of noodles cooks while the other dishes are made.
        return float(recipe.prep_minutes), float(recipe.cook_minutes + recipe.passive_minutes)
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
