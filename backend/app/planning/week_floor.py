"""What any week the planner can build must cost at least, worked out from its candidates without a search.

The candidates are the recommendations `WeeklyMealPlanService.generate` plans from. Each ingredient is
priced at the cheapest price per unit among the candidates' products, an ingredient the household holds a
known quantity of at nothing, and each meal is its dishes at the smallest portion share they can take.
Under a cap on uses ("no dish twice") a role's days take its cheapest dishes, each at most the cap times.
Buying whole packages only adds to that, so a weekly budget below `total_sgd` is one no week from these
candidates meets, and a per-meal budget below a meal's floor is one no meal meets. Nothing here searches
or plans: it bounds what a search could find.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from itertools import accumulate, combinations
from math import inf

from app.data import meal_structure
from app.data.units import in_grams
from app.planning import alternatives
from app.planning.household_slots import present_members
from app.planning.meal_composition import MAIN_ROLE, fills_staple, meal_role_of, portion_shares, role_base
from app.planning.member_coverage import catalog_can_eat, member_limits
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
    # (meal type, member name) no meal of these candidates can cover (ADR-0071 section 1).
    uncovered: list[tuple[str, str]] = field(default_factory=list)


def week_floor(constraints, recommendations, recipes) -> WeekFloor:
    shape = meals_of_the_day(constraints) or [("dinner", ONE_DISH)]
    course = {recipe.id: getattr(recipe, "course", None) or "main" for recipe in recipes}
    tag = {recipe.id: meal_role_of(recipe) for recipe in recipes}
    lines = [
        (item.recipe.id, line)
        for item in recommendations
        for line in (item.grocery_estimate.items if item.grocery_estimate else [])
        if line.product is not None and line.required_quantity is not None
    ]
    # A liquid of known density is priced by the gram whichever way a product or a line measures it: the
    # planner buys it by weight when its dishes measure it both ways (`app.data.units.weighed`), and a floor
    # must stay below either way of buying it.
    unit_price: dict[tuple[str, str], float] = {}
    for _, line in lines:
        size, unit = in_grams(*normalized(line.product.package_size, line.product.package_unit), line.ingredient_name)
        if size:
            key = (line.ingredient_name, unit)
            unit_price[key] = min(unit_price.get(key, inf), line.product.price_sgd / size)
    held = {item.normalized_name for item in constraints.available_ingredients if item.quantity is not None}
    bought: dict[int, float] = {}  # per recipe, every ingredient bought (as the per-meal budget reads it)
    paid: dict[int, float] = {}  # per recipe, what the household holds left out (as the weekly budget reads it)
    # The estimates are for the whole household. A dish is cooked for the members who can eat it (ADR-0071
    # section 1), which can be as few as one, so the smallest member's share of the household is the least any
    # dish could cost. A floor has to stay below every week the planner could build: scaling by the largest
    # share instead would refuse budgets that a week actually fits into.
    smallest = _smallest_share(constraints)
    for recipe_id, line in lines:
        quantity, unit = in_grams(*normalized(line.required_quantity, line.unit), line.ingredient_name)
        price = quantity * unit_price.get((line.ingredient_name, unit), 0.0) * smallest
        bought[recipe_id] = bought.get(recipe_id, 0.0) + price
        paid[recipe_id] = paid.get(recipe_id, 0.0) + (0.0 if line.ingredient_name in held else price)

    policy = PlanningCompositionPolicy()
    total, meal_sgd, empty, stats = 0.0, {}, [], {}
    for meal, composition in shape:
        roles = [role if isinstance(role, dict) else role.model_dump() for role in composition]
        tagged = bool(roles and roles[0].get("meal_roles"))
        week_paid, cheapest_bought = {}, {}
        for role in roles:
            if tagged:
                fits = [item for item in recommendations if tag.get(item.recipe.id) in role["meal_roles"]]
            else:
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
            elif role.get("required", True) and not (tagged and role_base(role["role_id"]) in ("staple", "vegetable")):
                # A structured meal's staple and vegetable may stay empty beside a one-bowl dish (ADR-0070).
                empty.append((meal, role["role_id"]))
        if not any(name == meal for name, _ in empty):
            if tagged:
                total += _structured_floor(roles, week_paid, constraints.day_count)
                meal_sgd[meal] = _structured_floor(roles, {r: [c] for r, c in cheapest_bought.items()}, 1)
            else:
                total += _cheapest_days(roles, week_paid, policy, constraints.day_count)
                meal_sgd[meal] = _cheapest_meal(roles, cheapest_bought, policy)
    uncovered = _uncovered(constraints, shape, recommendations, recipes)
    return WeekFloor(
        constraints.day_count, constraints.day_count * len(shape), total, meal_sgd, empty, stats, uncovered
    )


def _smallest_share(constraints) -> float:
    """The least of the household a single dish can be cooked for: 1 without members, else the smallest
    member's portions over what the grocery estimates were priced for."""
    household = getattr(constraints, "household", None)
    members = household.members if household is not None else None
    size = constraints.household_size or 1
    if not members:
        return 1.0
    return min(1.0, min(member.servings for member in members) / size)


def _meals_each_member_eats(constraints, shape) -> dict[str, set[str]]:
    """Which members are ever home for each meal of the plan, by that meal's own presence rules.

    The kids who eat lunch at school on weekdays are not owed a lunch they never sit down to, so the floor
    asks for their coverage only at the meals they are actually at.
    """
    household = constraints.household
    at_meal: dict[str, set[str]] = {meal: set() for meal, _ in shape}
    for index in range(constraints.day_count):
        day = constraints.start_date + timedelta(days=index)
        for meal, _ in shape:
            at_meal[meal].update(member.name for member in present_members(household, day, meal))
    return at_meal


def _uncovered(constraints, shape, recommendations, recipes) -> list[tuple[str, str]]:
    """Members no lunch or dinner of these candidates can cover (ADR-0071 section 1), as (meal, member name).

    Each member needs a filling core among the dishes that member can eat: a dish that carries its staple, or a
    protein main beside a staple. This proves a member uncoverable from the candidate pool; it does not prove the
    rest coverable together, which only a search can. Coverage is a safety rule (ADR-0068), so a refusal here
    offers the budget, the time and the dish count, never a limit of the member's own.
    """
    members = member_limits(constraints.household)
    if not members:
        return []
    at_meal = _meals_each_member_eats(constraints, shape)
    by_id = {recipe.id: recipe for recipe in recipes}
    uncovered = []
    for meal, composition in shape:
        roles = [role if isinstance(role, dict) else role.model_dump() for role in composition]
        if meal not in ("lunch", "dinner") or not (roles and roles[0].get("meal_roles")):
            continue
        fitting = [by_id[item.recipe.id] for item in recommendations if item.recipe.id in by_id]
        mains = [
            recipe
            for role in roles
            if role_base(role["role_id"]) == MAIN_ROLE
            for recipe in fitting
            if meal_role_of(recipe) in role["meal_roles"]
        ]
        staples = [recipe for recipe in fitting if meal_role_of(recipe) == "staple"]
        has_staple_role = any(role["role_id"] == "staple" for role in roles)
        # An "A or B" line is judged by the option this household cooks, as the planner judges it.
        cooked = {recipe.id: alternatives.lines(recipe, constraints) for recipe in {*mains, *staples}}
        for member in members:
            if member.name not in at_meal.get(meal, set()):
                continue  # never home for this meal, so no plate is owed at it
            mine = [recipe for recipe in mains if catalog_can_eat(member, recipe, cooked[recipe.id])]
            bowl = any(fills_staple(recipe) for recipe in mine)
            staple = has_staple_role and any(catalog_can_eat(member, r, cooked[r.id]) for r in staples)
            if not bowl and not (staple and any(meal_role_of(recipe) == "protein_main" for recipe in mine)):
                uncovered.append((meal, member.name))
    return uncovered


def _structured_floor(roles: list[dict], prices: dict[str, list[float]], days: int) -> float:
    """A structured meal's floor: its filling core alone, at the smallest share a core dish takes (three protein
    mains), on each day. Every other dish of a full meal may move or carry its staple, so only the core is sure.
    ponytail: a loose bound; count the staple and vegetable when no one-bowl dish fits, to tighten it."""
    core = next((role for role in roles if set(role.get("meal_roles") or ()) & {"protein_main", "one_bowl"}), None)
    if core is None or core["role_id"] not in prices:
        return 0.0
    table = meal_structure.portion_shares()
    smallest = min([*table["protein_main"], table["one_bowl"]])
    cheapest = sorted(prices[core["role_id"]])[:days]
    return smallest * sum(cheapest) if len(cheapest) == days else 0.0


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
