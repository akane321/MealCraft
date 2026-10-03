"""What any week the planner can build must cost at least, worked out from its candidates without a search.

The candidates are the recommendations `WeeklyMealPlanService.generate` plans from. Each ingredient is
priced at the cheapest price per unit among the candidates' products, an ingredient the household holds a
known quantity of at nothing, and each meal is its dishes at the smallest portion share they can take.
Under a cap on uses ("no dish twice") a role's days take its cheapest dishes, each at most the cap times.
Buying whole packages only adds to that, so a weekly budget below `total_sgd` is one no week from these
candidates meets, and a per-meal budget below a meal's floor is one no meal meets. Nothing here searches
or plans: it bounds what a search could find.
"""

from dataclasses import dataclass
from itertools import accumulate, combinations
from math import inf

from app.planning.meal_composition import MAIN_ROLE, portion_shares
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
        week_paid, cheapest_bought = {}, {}
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
                # The role's days at its cheapest dishes, each served at most `cap` times (any number without one).
                dishes = sorted({item.recipe.id: paid.get(item.recipe.id, 0.0) for item in fits}.values())
                uses = constraints.max_uses_per_recipe or constraints.day_count
                week_paid[role["role_id"]] = [cost for cost in dishes for _ in range(uses)][: constraints.day_count]
                cheapest_bought[role["role_id"]] = min(bought.get(item.recipe.id, 0.0) for item in fits)
            elif role.get("required", True):
                empty.append((meal, role["role_id"]))
        if not any(name == meal for name, _ in empty):
            total += _cheapest_days(roles, week_paid, policy, constraints.day_count)
            meal_sgd[meal] = _cheapest_meal(roles, cheapest_bought, policy)
    return WeekFloor(constraints.day_count, constraints.day_count * len(shape), total, meal_sgd, empty, stats)


def _meals(roles: list[dict], filled: dict, policy) -> list[dict[str, float]]:
    """Each way a meal can be served: its required dishes and any optional ones that have a dish, with shares."""
    required = [role["role_id"] for role in roles if role.get("required", True)]
    optional = [role["role_id"] for role in roles if not role.get("required", True) and role["role_id"] in filled]
    meals = []
    for count in range(len(optional) + 1):
        for extra in combinations(optional, count):
            present = [*required, *extra]
            shares = portion_shares(policy, present) if present else None
            if shares is not None:
                meals.append({role: float(shares[role]) for role in present})
    return meals


def _cheapest_meal(roles: list[dict], cheapest: dict[str, float], policy) -> float:
    """The cheapest a meal can be: its required dishes and any optional ones, each at its share of the meal."""
    costs = [sum(share * cheapest[role] for role, share in meal.items()) for meal in _meals(roles, cheapest, policy)]
    return min(costs, default=0.0)


def _cheapest_days(roles: list[dict], prices: dict[str, list[float]], policy, days: int) -> float:
    """The cheapest `days` of a meal can be, when a role's dishes are `prices` (ascending, one per use allowed).

    A share depends only on how many dishes the meal has, and the policy's shares shrink as a meal grows, so
    with the days taken from the fewest dishes to the most, each role's cheapest uses meet its largest shares
    (the rearrangement inequality). The optional dishes' uses are pooled: any optional role's use may fill
    any optional dish of a day, at the smallest share an optional dish takes. That only lets a week be cheaper
    than a real one, as does bounding every role on its own (a dish's cap is shared across roles and meals in
    a real week), so this stays under any real week. One pass over the days, keeping the cheapest days so far
    for each (optional dishes on the last day, pooled uses taken): days x sizes x uses steps, where trying
    every mix of the 2^k ways to serve a meal with k optional dishes took 90 s for five.
    """
    required = [role["role_id"] for role in roles if role.get("required", True)]
    optional = [role["role_id"] for role in roles if not role.get("required", True) and role["role_id"] in prices]
    optional.sort(key=lambda role: role == MAIN_ROLE)  # a main takes a larger share: added last, so never the smallest
    if any(len(prices[role]) < days for role in required):
        return 0.0  # too few dishes for every day: no week, which the refusal says before the floor matters
    pooled = list(accumulate(sorted(cost for role in optional for cost in prices[role]), initial=0.0))
    ways = []  # (optional dishes, each required role's share, the smallest share an optional dish takes)
    for extra in range(len(optional) + 1):
        shares = portion_shares(policy, [*required, *optional[:extra]]) if required or extra else None
        if shares is not None:
            smallest = min((float(shares[role]) for role in optional[:extra]), default=0.0)
            ways.append((extra, [float(shares[role]) for role in required], smallest))
    best = {(0, 0): 0.0}  # (optional dishes on the last day, pooled uses taken) -> the cheapest days so far
    for day in range(days):
        reached: dict[tuple[int, int], float] = {}
        for (fewest, taken), cost in best.items():
            for extra, shares, smallest in ways:
                if extra < fewest or taken + extra >= len(pooled):
                    continue
                today = sum(share * prices[role][day] for role, share in zip(required, shares, strict=True))
                today += smallest * (pooled[taken + extra] - pooled[taken])
                reached[extra, taken + extra] = min(reached.get((extra, taken + extra), inf), cost + today)
        best = reached
    return min(best.values(), default=0.0)
