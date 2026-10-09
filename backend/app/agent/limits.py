"""The limit a week cannot be planned within, said with the number that shows it, and what to change.

Two moments. Before the assistant says it has everything, `refusal` compares the limits with the floor
under any week's cost (planning/week_floor.py): a weekly budget under it is refused with what the cheapest
week the search finds costs (the floor itself when it finds none), and any other is planned with the planner
itself, so whatever the planner would answer at Plan is answered now. For meals too big for the planner to
search within a reply, only what the floor proves is refused, and Plan answers the rest. After the planner
found no week, `planning_failure` names the limit its trace shows the search kept running into; a search that
found nothing proves nothing about every week, so it never says no week exists.

A budget is offered only when a real week backs it. The suggestion's amount is checked through the
same budgeted planning path used when the household accepts it, not inferred from an unbudgeted search.
"""

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from app.agent.replies import details, joined, people, planner_message, say, word
from app.data.allergens import checked_allergens
from app.planning.product_path import QUICK_MEAL_DISHES
from app.planning.week_floor import WeekFloor
from app.schemas.meal_plan import default_plan_shape

# The floor is a float sum of per-unit prices; the planner rounds each ingredient's cost to the cent.
SLACK_SGD = 0.05
# What emptied the search (planning/meal_beam.py), as the validator check it stands for.
EMPTIED = {
    "budget": "purchase_budget",
    "repeats": "repetition_rule",
    "requests": "request",
    "day_limits": "nutrition",
    "meal": "meal",
}
ROLE_EN = {"main": "main dish", "vegetable": "vegetable dish", "soup": "soup"}


@dataclass(frozen=True)
class Refusal:
    field: str  # the constraint that binds
    text: str
    options: tuple[tuple[str, str], ...] = ()  # (label, what tapping it says)
    retry: bool = False  # nothing to change: the same request may plan next time


def refusal(
    constraints,
    floor_of: Callable[..., WeekFloor],
    lang: str,
    *,
    check: Callable[..., Exception | None],
    cheapest: Callable[..., float | None],
) -> Refusal | None:
    """A limit no week from the planner's candidates meets, or None.

    Each callable takes `changes` made to the plan request: `floor_of` gives the floor, `check` what the
    planner answers at Plan (None for a week, else its error), `cheapest` what the cheapest week the
    planner's cost-led search finds costs (None for no week), all without saving anything.
    """
    floor = floor_of()
    if max(_dishes(constraints)) > QUICK_MEAL_DISHES:
        check = cheapest = None  # no search within the reply: what the floor proves is refused, Plan answers the rest
    if floor.empty_roles:
        meal, role = floor.empty_roles[0]
        return _no_dish(constraints, floor_of, check, meal, role, lang)
    cap = constraints.max_uses_per_recipe
    for (meal, role), found in floor.roles.items() if cap else ():
        # A dish served at most `cap` times fills a role every day only with enough different dishes.
        needed = math.ceil(floor.days / cap)
        if found.required and found.count < needed:
            rule = say("no_repeats_rule", lang) if cap == 1 else say("cap_rule", lang, count=cap)
            text = say(
                "too_few",
                lang,
                rule=rule,
                needed=needed,
                role=_role(role, lang, plural=True),
                meal=word(meal, lang),
                count=found.count,
            )
            return Refusal("max_uses_per_recipe", text)
    per_meal = constraints.budget_per_meal_sgd
    if per_meal is not None and floor.meal_sgd:
        meal, cheapest_meal = max(floor.meal_sgd.items(), key=lambda item: item[1])
        if cheapest_meal > per_meal + SLACK_SGD:
            text = say("floor_meal", lang, budget=per_meal, meal=word(meal, lang), floor=_cents_down(cheapest_meal))
            return Refusal("budget_per_meal_sgd", text, _raise_meal(check, math.ceil(cheapest_meal), lang))
    weekly = constraints.weekly_budget_sgd
    if weekly is not None and weekly < floor.total_sgd - SLACK_SGD:
        # Under the floor no week fits: what remains to say is what the cheapest week the search finds costs.
        cost = cheapest() if cheapest is not None else None
        if cost is not None:
            return _budget_short(cost, constraints, lang, cheapest)
        # Not searched for, or the search found no week: the floor, with no amount a week backs to offer.
        size, meals = constraints.household_size or 1, floor.meals
        each, least = weekly / (size * meals), _cents_down(floor.total_sgd)
        text = say("floor_week", lang, budget=weekly, people=people(size, lang), each=each, meals=meals, floor=least)
        return Refusal("weekly_budget_sgd", text)
    if check is not None and weekly is not None:
        # Over the floor, whole packages decide, by no ratio that holds: on the release catalog the cheapest week
        # costs 1.6 to 122 times the floor (122 for one person's breakfasts, no dish twice). Plan it as Plan would,
        # and refuse what that refuses.
        error = check()
        failure = planning_failure(error, constraints, lang, cheapest=cheapest) if error is not None else None
        if failure is not None and not failure.retry:  # a slow search or late data may plan at Plan
            return failure
    return None


def _raise_meal(check, amount: int, lang: str) -> tuple[tuple[str, str], ...]:
    """The per-meal budget to offer, only when a week plans with it (never when it cannot be checked)."""
    backed = check is not None and check(budget_per_meal_sgd=amount) is None
    return (_option("raise_meal", lang, amount=amount),) if backed else ()


def _no_dish(constraints, floor_of, check, meal: str, role: str, lang: str) -> Refusal:
    """No candidate fills a dish the meal needs: the first limit that, eased, lets one in."""
    probes = []
    if constraints.budget_per_meal_sgd is not None:
        probes.append(("budget_per_meal_sgd", None))
    if constraints.max_cooking_time_minutes is not None and constraints.max_cooking_time_minutes < 240:
        probes.append(("max_cooking_time_minutes", 240))
    if constraints.dietary_preferences:
        probes.append(("dietary_preferences", []))
    if constraints.max_sodium_mg_per_meal is not None:
        probes.append(("max_sodium_mg_per_meal", None))
    for field, eased in probes:
        found = floor_of(**{field: eased}).roles.get((meal, role))
        if found is None or not found.count:
            continue
        limit, options = say("meal_limit", lang, amount=constraints.budget_per_meal_sgd or 0), ()
        if field == "budget_per_meal_sgd" and found.cheapest_sgd is not None:
            limit = say("limit_meal_budget", lang, budget=constraints.budget_per_meal_sgd, needed=found.cheapest_sgd)
            options = _raise_meal(check, math.ceil(found.cheapest_sgd), lang)
        elif field == "max_cooking_time_minutes" and found.quickest_minutes is not None:
            limit = say("limit_time", lang, minutes=constraints.max_cooking_time_minutes, needed=found.quickest_minutes)
            options = (_option("raise_time", lang, minutes=found.quickest_minutes),)
        elif field == "max_sodium_mg_per_meal" and found.lowest_sodium_mg is not None:
            needed = math.ceil(found.lowest_sodium_mg)
            limit = say("limit_sodium", lang, mg=round(constraints.max_sodium_mg_per_meal), needed=needed)
            options = (_option("raise_sodium", lang, mg=needed),)
        elif field == "dietary_preferences":
            diets = joined((word(diet, lang) for diet in constraints.dietary_preferences), lang)
            limit = say("limit_diet", lang, diet=diets)
        return Refusal(field, _no_dish_text(meal, role, limit, lang), options)
    if probes:
        # No one limit, eased alone, lets a dish in: they bind together.
        limit = say("limit_together", lang, limits=joined(details(constraints, lang), lang))
        return Refusal(probes[0][0], _no_dish_text(meal, role, limit, lang))
    if constraints.allergens or constraints.excluded_ingredients:
        return Refusal("allergens", _no_dish_text(meal, role, say("limit_safety", lang), lang))
    return Refusal("plan_shape", say("no_role", lang, role=_role(role, lang), meal=word(meal, lang)))


def _no_dish_text(meal: str, role: str, limit: str, lang: str) -> str:
    return say("no_dish", lang, role=_role(role, lang), meal=word(meal, lang), limit=limit)


def _role(role: str, lang: str, *, plural: bool = False) -> str:
    """'main dish' (or 'main dishes'), 主菜; a second main ("main-2") is a main too."""
    base = role.split("-")[0]
    if lang == "zh":
        return word(base, lang)
    name = ROLE_EN.get(base, f"{base} dish")
    return name + ("es" if name.endswith("dish") else "s") if plural else name


def planning_failure(error: Exception, constraints, lang: str, *, cheapest=None) -> Refusal:
    """Why the planner found no week, from its error and trace: the limit its search kept running into.

    A request the planner turned down before searching (a budget in fractions of a cent, missing allergen
    data) is passed on as the planner said it. `cheapest(**changes)`, when given, backs a budget refusal's
    options with a smaller household's cheapest week.
    """
    status, trace = getattr(error, "status", None), getattr(error, "trace", None) or {}
    if status in {"needs_clarification", "needs_data"} or not trace:
        text = say("not_planned", lang, reason=planner_message(str(error), lang))
        # Missing allergen coverage stays missing however often the same week is asked for.
        lasting = bool(set(constraints.allergens) - checked_allergens())
        return Refusal("plan", text, retry=status == "needs_data" and not lasting)
    search = trace.get("search") or {}
    if search.get("exhausted"):
        return Refusal("plan", say("slow", lang), retry=True)
    attempts = trace.get("validation_attempts") or []
    failed = Counter(code for attempt in attempts for code in _failed(attempt))
    code = failed.most_common(1)[0][0] if failed else EMPTIED.get(search.get("emptied_by"))
    weekly, per_meal = constraints.weekly_budget_sgd, constraints.budget_per_meal_sgd
    minutes = constraints.max_cooking_time_minutes
    if code == "purchase_budget" and weekly is not None:
        # Weeks of the cheapest-week search that only the budget turned down: each plans under its cost.
        backed = [
            attempt["purchase_total_sgd"]
            for attempt in attempts
            if attempt.get("cheapest_search") and _failed(attempt) == {"purchase_budget"}
        ]
        if backed:
            return _budget_short(min(backed), constraints, lang, cheapest)
        # No week backs an amount. The budget is still what the search ran into when every week it ranked failed
        # the budget alone (or none was ranked: the search emptied on the budget); else it is not all that binds.
        ranked = [_failed(attempt) for attempt in attempts if not attempt.get("cheapest_search")]
        if any(failed != {"purchase_budget"} for failed in ranked):
            code = None
    if code == "purchase_budget" and weekly is not None:
        limit, field = say("weekly_limit", lang, amount=weekly), "weekly_budget_sgd"
    elif code == "per_meal_budget" and per_meal is not None:
        limit, field = say("meal_limit", lang, amount=per_meal), "budget_per_meal_sgd"
    elif code in {"time_limit", "dish_time_limit"} and minutes is not None:
        limit, field = say("time_limit", lang, minutes=minutes), "max_cooking_time_minutes"
    elif code == "repetition_rule":
        limit, field = say("repeat_limit", lang), "max_uses_per_recipe"
    elif code is not None and code.startswith("nutrition"):
        limit, field = say("nutrition_limit", lang), "nutrition_targets"
    elif code == "request":
        limit, field = say("request_limit", lang), "plan"
    else:
        return Refusal("plan", say("search_failed_generic", lang, limits=joined(details(constraints, lang), lang)))
    return Refusal(field, say("search_failed", lang, limit=limit))


def _failed(attempt: dict) -> set[str]:
    return {check["code"] for check in attempt.get("checks", []) if check.get("hard") and check["status"] == "failed"}


def _budget_short(cost: float, constraints, lang: str, cheapest) -> Refusal:
    """A weekly budget under the cheapest week the search found: what it is a person a meal, that week's
    cost, and the budgets a real week backs."""
    weekly, size = constraints.weekly_budget_sgd, constraints.household_size or 1
    meals = 7 * len((constraints.plan_shape or default_plan_shape()).meals)
    text = say(
        "budget_short",
        lang,
        budget=weekly,
        people=people(size, lang),
        each=weekly / (size * meals),
        meals=meals,
        cost=cost,
    )
    whole = math.ceil(cost)
    options = [_option("use_weekly", lang, amount=whole)]
    fewer = size // 2
    # Half the household at its own cheapest week takes a second search: offered for one meal a day of a quick
    # size, where the two take at most 5 s; for more they would take the reply past its time limit (ADR-0046
    # section 3).
    quick = meals == 7 and max(_dishes(constraints)) <= QUICK_MEAL_DISHES and cheapest is not None and fewer >= 1
    smaller = cheapest(household_size=fewer) if quick else None
    # The cheapest-week search is a heuristic, not monotonic in who eats: fewer people can come out dearer than
    # everyone (S$41 for 2 beside S$24 for 4). Offered only when a real week backs it and it costs less.
    if smaller is not None and math.ceil(smaller) < whole:
        # Fewer people buy less: the budget as it is when their cheapest week fits it, else that week's cost.
        if smaller <= weekly:
            options.append(_option("fewer_people", lang, count=fewer, people=people(fewer, lang)))
        else:
            options.append(
                _option("fewer_people_at", lang, count=fewer, people=people(fewer, lang), amount=math.ceil(smaller))
            )
    elif smaller is not None:
        text += " " + say("fewer_not_cheaper", lang, people=people(fewer, lang), amount=math.ceil(smaller))
    return Refusal("weekly_budget_sgd", text, tuple(options))


def _dishes(constraints) -> list[int]:
    """How many dishes each planned meal has."""
    return [len(roles) for roles in (constraints.plan_shape or default_plan_shape()).meals.values()]


def _option(key: str, lang: str, **values) -> tuple[str, str]:
    label_values = {**values}
    if "people" in label_values:
        label_values["people"] = people(values["count"], "en")
    return say(key, "en", **label_values), say(f"{key}_say", lang, **values)


def _cents_down(amount: float) -> float:
    return math.floor(amount * 100) / 100
