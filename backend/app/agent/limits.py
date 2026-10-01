"""The limit a week cannot be planned within, said with the number that shows it, and what to change.

Two moments. Before the assistant says it has everything, `refusal` compares the limits with the floor
under any week's cost (planning/week_floor.py): it refuses only what the floor proves. After the planner
found no week, `planning_failure` names the limit its trace shows the search kept running into; a search
that found nothing proves nothing about every week, so it never says no week exists.
"""

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from app.agent.replies import details, joined, people, say, word
from app.planning.week_floor import WeekFloor

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


def refusal(constraints, floor_of: Callable[..., WeekFloor], lang: str) -> Refusal | None:
    """A limit no week from the planner's candidates meets, or None.

    `floor_of(**changes)` is the floor for these constraints with `changes` made to the plan request.
    """
    floor = floor_of()
    if floor.empty_roles:
        meal, role = floor.empty_roles[0]
        return _no_dish(constraints, floor_of, meal, role, lang)
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
        meal, cheapest = max(floor.meal_sgd.items(), key=lambda item: item[1])
        if cheapest > per_meal + SLACK_SGD:
            text = say("floor_meal", lang, budget=per_meal, meal=word(meal, lang), floor=_cents_down(cheapest))
            return Refusal("budget_per_meal_sgd", text, (_option("raise_meal", lang, amount=math.ceil(cheapest)),))
    weekly, size = constraints.weekly_budget_sgd, constraints.household_size
    if weekly is not None and floor.total_sgd > weekly + SLACK_SGD:
        text = say(
            "floor_weekly",
            lang,
            budget=weekly,
            people=people(size, lang),
            each=weekly / (size * floor.meals),
            meals=floor.meals,
            floor=_cents_down(floor.total_sgd),
        )
        options = [_option("raise_weekly", lang, amount=math.ceil(floor.total_sgd))]
        # Every quantity scales with the people eating, and so does the floor.
        fewer = math.floor(weekly * size / floor.total_sgd)
        if 1 <= fewer < size:
            options.append(_option("fewer_people", lang, count=fewer, people=people(fewer, lang)))
        return Refusal("weekly_budget_sgd", text, tuple(options))
    return None


def _no_dish(constraints, floor_of, meal: str, role: str, lang: str) -> Refusal:
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
            options = (_option("raise_meal", lang, amount=math.ceil(found.cheapest_sgd)),)
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


def planning_failure(status: str | None, trace: dict, constraints, lang: str) -> Refusal:
    """Why the planner found no week, from its trace: the limit its search kept running into."""
    if status == "needs_data":
        return Refusal("plan", say("missing_data", lang), retry=True)
    search = trace.get("search") or {}
    if search.get("exhausted"):
        return Refusal("plan", say("slow", lang), retry=True)
    attempts = trace.get("validation_attempts") or []
    failed = Counter(
        check["code"]
        for attempt in attempts
        for check in attempt.get("checks", [])
        if check.get("hard") and check.get("status") == "failed"
    )
    code = failed.most_common(1)[0][0] if failed else EMPTIED.get(search.get("emptied_by"))
    totals = [attempt["purchase_total_sgd"] for attempt in attempts if attempt.get("purchase_total_sgd") is not None]
    weekly, per_meal = constraints.weekly_budget_sgd, constraints.budget_per_meal_sgd
    minutes = constraints.max_cooking_time_minutes
    detail, options = "", ()
    if code == "purchase_budget" and weekly is not None:
        limit = say("weekly_limit", lang, amount=weekly)
        cheapest = min(totals) if totals else None
        if cheapest is not None and cheapest > weekly:
            detail = say("cheapest_found", lang, amount=cheapest)
        # A week the search finished is one a budget of its cost buys; without one, a suggestion to try.
        options = (_option("try_weekly", lang, amount=math.ceil(cheapest if detail else weekly * 1.25)),)
        field = "weekly_budget_sgd"
    elif code == "per_meal_budget" and per_meal is not None:
        limit, field = say("meal_limit", lang, amount=per_meal), "budget_per_meal_sgd"
        options = (_option("raise_meal", lang, amount=math.ceil(per_meal * 1.25)),)
    elif code in {"time_limit", "dish_time_limit"} and minutes is not None:
        limit, field = say("time_limit", lang, minutes=minutes), "max_cooking_time_minutes"
        if minutes < 240:
            options = (_option("raise_time", lang, minutes=min(240, minutes + 30)),)
    elif code == "repetition_rule":
        limit, field = say("repeat_limit", lang), "max_uses_per_recipe"
    elif code is not None and code.startswith("nutrition"):
        limit, field = say("nutrition_limit", lang), "nutrition_targets"
    elif code == "request":
        limit, field = say("request_limit", lang), "plan"
    else:
        return Refusal("plan", say("search_failed_generic", lang, limits=joined(details(constraints, lang), lang)))
    return Refusal(field, say("search_failed", lang, limit=limit, detail=detail), options)


def _option(key: str, lang: str, **values) -> tuple[str, str]:
    return say(key, lang, **values), say(f"{key}_say", lang, **values)


def _cents_down(amount: float) -> float:
    return math.floor(amount * 100) / 100
