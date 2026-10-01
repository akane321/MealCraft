"""What any week the planner can build must cost at least, worked out from its candidates without a search.

The candidates are the recommendations `WeeklyMealPlanService.generate` plans from. Each ingredient is
priced at the cheapest price per unit among the candidates' products, an ingredient the household holds a
known quantity of at nothing, and each meal is its dishes at the smallest portion share they can take.
Buying whole packages only adds to that, so a weekly budget below `total_sgd` is one no week from these
candidates meets, and a per-meal budget below a meal's floor is one no meal meets. Nothing here searches
or plans: it bounds what a search could find.
"""

from dataclasses import dataclass
from itertools import combinations
from math import inf

from app.planning.meal_composition import portion_shares
from app.planning.product_path import meals_of_the_day, normalized
from app.schemas.planning_v2 import PlanningCompositionPolicy

ONE_DISH = [{"role_id": "main", "courses": ["main"], "required": True}]


@dataclass(frozen=True)
class RoleCandidates:
    count: int  # different dishes that fit the role
    required: bool
    quickest_minutes: int | None
    # The cheapest ingredient-use cost at full portions, as the per-meal budget filter reads it.
    cheapest_sgd: float | None
    lowest_sodium_mg: float | None


@dataclass(frozen=True)
class WeekFloor:
    days: int
    meals: int  # meals in the week
    total_sgd: float  # the week's purchase total is at least this (pantry counted)
    meal_sgd: dict[str, float]  # one meal's ingredient-use cost is at least this, per meal type
    empty_roles: list[tuple[str, str]]  # (meal type, role) a dish is required for and no candidate fills
    roles: dict[tuple[str, str], RoleCandidates]


def week_floor(constraints, recommendations, recipes) -> WeekFloor:
    shape = meals_of_the_day(constraints) or [("dinner", ONE_DISH)]
    course = {recipe.id: getattr(recipe, "course", None) or "main" for recipe in recipes}
    lines = [
        (item.recipe.id, line)
        for item in recommendations
        for line in (item.grocery_estimate.items if item.grocery_estimate else [])
        if line.product is not None and line.required_quantity is not None
    ]
    unit_price: dict[tuple[str, str], float] = {}
    for _, line in lines:
        size, unit = normalized(line.product.package_size, line.product.package_unit)
        if size:
            key = (line.ingredient_name, unit)
            unit_price[key] = min(unit_price.get(key, inf), line.product.price_sgd / size)
    held = {item.normalized_name for item in constraints.available_ingredients if item.quantity is not None}
    bought: dict[int, float] = {}  # per recipe, every ingredient bought (as the per-meal budget reads it)
    paid: dict[int, float] = {}  # per recipe, what the household holds left out (as the weekly budget reads it)
    for recipe_id, line in lines:
        quantity, unit = normalized(line.required_quantity, line.unit)
        price = quantity * unit_price.get((line.ingredient_name, unit), 0.0)
        bought[recipe_id] = bought.get(recipe_id, 0.0) + price
        paid[recipe_id] = paid.get(recipe_id, 0.0) + (0.0 if line.ingredient_name in held else price)

    policy = PlanningCompositionPolicy()
    total, meal_sgd, empty, stats = 0.0, {}, [], {}
    for meal, composition in shape:
        roles = [role if isinstance(role, dict) else role.model_dump() for role in composition]
        cheapest_paid, cheapest_bought = {}, {}
        for role in roles:
            fits = [item for item in recommendations if course.get(item.recipe.id, "main") in role["courses"]]
            known = [item.grocery_estimate.consumed_total_sgd for item in fits if item.grocery_estimate]
            stats[meal, role["role_id"]] = RoleCandidates(
                count=len({item.recipe.id for item in fits}),
                required=role.get("required", True),
                quickest_minutes=min((item.recipe.total_time_minutes for item in fits), default=None),
                cheapest_sgd=min((value for value in known if value is not None), default=None),
                lowest_sodium_mg=min((float(item.recipe.nutrition.sodium_mg) for item in fits), default=None),
            )
            if fits:
                cheapest_paid[role["role_id"]] = min(paid.get(item.recipe.id, 0.0) for item in fits)
                cheapest_bought[role["role_id"]] = min(bought.get(item.recipe.id, 0.0) for item in fits)
            elif role.get("required", True):
                empty.append((meal, role["role_id"]))
        if not any(name == meal for name, _ in empty):
            total += _cheapest_meal(roles, cheapest_paid, policy) * constraints.day_count
            meal_sgd[meal] = _cheapest_meal(roles, cheapest_bought, policy)
    return WeekFloor(constraints.day_count, constraints.day_count * len(shape), total, meal_sgd, empty, stats)


def _cheapest_meal(roles: list[dict], cheapest: dict[str, float], policy) -> float:
    """The cheapest a meal can be: its required dishes and any optional ones, each at its share of the meal."""
    required = [role["role_id"] for role in roles if role.get("required", True)]
    optional = [role["role_id"] for role in roles if not role.get("required", True) and role["role_id"] in cheapest]
    best = inf
    for count in range(len(optional) + 1):
        for extra in combinations(optional, count):
            present = [*required, *extra]
            shares = portion_shares(policy, present) if present else None
            if shares is not None:
                best = min(best, sum(float(shares[role]) * cheapest[role] for role in present))
    return 0.0 if best == inf else best
