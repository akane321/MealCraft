"""The strong-rule baseline arm: hand-written rules only, no language model (02-baselines.md section 1; #396).

It answers through the conversation harness like every other arm (`baseline_arms`), from the user's own strings:

1. **Read the request with rules.** The product's rule parser (`RuleBasedConstraintParser`, the same rules the
   product falls back to without a model) reads household size, allergens, exclusions, diet, halal, time and
   budget; `plan_dates` reads the days and meals; this module's keyword table reads each meal's dishes ("a main
   and a vegetable", 一荤一素一汤). Missing household size is asked for, as one clarification.
2. **Filter the frozen catalog with rules.** Release v3 recipes the frozen snapshot can price
   (`load_release_catalog`), kept when the meal type and course fit the dish role, the cooking time fits, no
   ingredient carries a stated allergen or has unknown allergens while one is stated, no ingredient is excluded
   (with the ingredient hierarchy's expansion), the diet tag is there, and, for halal, every ingredient is
   labelled halal without a certified product.
3. **Pick with a fixed priority.** Cheapest estimated cost for the household first (cheapest frozen package price
   per gram, no package rounding), then shorter time, then recipe id; never the same dish twice in one day or on
   the next day when another fits, and at most twice a week (once when the user says no repeats).

There is no search, scoring model, repair or budget look-ahead: it is the plain rule a careful person could write,
the counterpart of the product's planner. Nutrition targets are not read. The plan is applied at once, so it never
waits for a confirmation.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.agent import plan_dates
from app.agent.parser import RuleBasedConstraintParser, chinese_number
from app.core import clock
from app.core.paths import repository_root
from app.data.halal import recipe_halal_status
from app.data.ingredient_hierarchy import expand_exclusions
from app.evaluation import baseline_arms
from app.evaluation.baseline_resources import RELEASE, BaselineResources
from app.evaluation.conversation_adapter import (
    Exchange,
    PlanDish,
    PlanMeal,
    PlanOutput,
    Responder,
    UnifiedOutput,
)
from app.evaluation.release_catalog import load_release_catalog
from app.planning.vegetable_led import row_vegetable_led
from app.schemas.agent import AgentConstraintState

SYSTEM_ID = "strong-rule"
MEALS = ("breakfast", "lunch", "dinner")
MEAL_WORDS = {
    "breakfast": r"breakfasts?|早餐|早饭|早点",
    "lunch": r"lunch(?:es)?|午餐|午饭|中饭",
    "dinner": r"dinners?|suppers?|晚餐|晚饭",
}
ALL_MEALS = r"three meals|all (?:three )?meals|every meal|三餐|三顿|早中晚"
# Dish roles and the courses a role takes (the roles the development episodes name).
COURSES = {
    "breakfast": ("breakfast", "baked_good"),
    "single": ("main", "salad", "soup"),
    "main": ("main",),
    "vegetable": ("side", "salad"),
    "soup": ("soup",),
}
TWO_MAINS = r"two (?:different )?(?:meat|main)s?(?: dishes)?|两荤|两个荤菜"
ROLE_WORDS = (
    ("main", r"\bmains?\b|main dish|meat dish|荤"),
    ("vegetable", r"\bveg(?:etables?|gies?)?\b|\bsides?\b|\bsalads?\b|素|蔬菜"),
    ("soup", r"\bsoups?\b|汤"),
)
# A dish that is too small to be a meal is not served: energy per serving at least this (kcal), by role kind.
ENERGY_FLOOR = {"breakfast": 250, "single": 350, "main": 350, "vegetable": 60, "soup": 100}
# A main is a meal's protein: protein per serving at least this (g). A side or soup has no floor.
PROTEIN_FLOOR = {"breakfast": 8, "single": 15, "main": 15}
NO_LIMIT_MINUTES = 240
MAX_USES = 2
SOLO = r"just me|only me|for one\b|myself|我一个人|一个人吃"
ZH_FAMILY = r"([一二两三四五六七八九十\d]+)口(?:之家|人)|一家([一二两三四五六七八九十\d]+)口"
CLARIFY_SIZE = "How many people should the plan feed?"


@dataclass(frozen=True)
class Request:
    household_size: int | None
    start: date
    days: int
    meals: dict[str, tuple[str, ...]]  # meal -> dish roles
    allergens: tuple[str, ...] = ()
    excluded: frozenset[str] = frozenset()
    diet: tuple[str, ...] = ()
    halal: bool = False
    max_minutes: int | None = None
    weekly_budget_sgd: float | None = None
    max_uses: int = MAX_USES


@dataclass
class Candidate:
    recipe: dict
    cost_sgd: float
    minutes: int
    steps: list[str] = field(default_factory=list)


def _clauses(text: str) -> list[str]:
    return [part for part in re.split(r"[,.;:!?，。；：！？\n]", text.lower()) if part.strip()]


def _roles(clause: str) -> tuple[str, ...]:
    roles: list[str] = []
    if re.search(TWO_MAINS, clause):
        roles += ["main", "main-2"]
    for role, pattern in ROLE_WORDS:
        if re.search(pattern, clause) and role not in roles:
            roles.append(role)
    if not roles or roles == ["main"]:
        return ("main",)
    if "main" not in roles:
        roles.insert(0, "main")
    return tuple(roles)


def read_meals(text: str, said: tuple[str, ...] | None) -> dict[str, tuple[str, ...]]:
    """Which meals, and each meal's dish roles, from keyword rules. A meal with no dish words gets one dish."""
    lowered = text.lower()
    if said:
        meals = [meal for meal in MEALS if meal in said]
    elif re.search(ALL_MEALS, lowered):
        meals = list(MEALS)
    else:
        meals = [meal for meal in MEALS if re.search(MEAL_WORDS[meal], lowered)] or ["dinner"]
    shapes = {meal: ("main",) for meal in meals}
    for clause in _clauses(lowered):
        named = [meal for meal in meals if re.search(MEAL_WORDS[meal], clause)]
        if not named and len(meals) == 1 and any(re.search(p, clause) for _, p in ROLE_WORDS):
            named = meals
        for meal in named[-1:]:  # "breakfast and dinner with a main and a veg": the dishes are dinner's
            roles = _roles(clause)
            # Clauses add dishes: "two meat dishes, a vegetable dish and a soup" is four dishes.
            shapes[meal] = tuple(dict.fromkeys((*shapes[meal], *roles)))
    return shapes


def _household_size(text: str, parsed: int | None) -> int | None:
    if parsed:
        return parsed
    lowered = text.lower()
    if re.search(SOLO, lowered):
        return 1
    if found := re.search(ZH_FAMILY, lowered):
        word = found.group(1) or found.group(2)
        return int(word) if word.isdigit() else chinese_number(word)
    return None


def read_request(turns: list[str], now: datetime) -> Request:
    parser = RuleBasedConstraintParser()
    state = AgentConstraintState()
    merged: dict = {}
    for turn in turns:
        extraction = parser.parse(turn, current=state, acknowledged_unknowns=[], history=[])
        merged |= extraction.model_dump(exclude_none=True)
    text = " ".join(turns)
    span = None
    start = None
    for turn in turns:
        span = plan_dates.read_span(turn, now) or span
        said = plan_dates.read_start(turn.lower(), now.date())
        start = said.start if said else start
    days = (span.days if span and span.days else None) or merged.get("plan_day_count") or 7
    meals = read_meals(text, span.meals if span else tuple(merged.get("plan_meals") or ()) or None)
    start = (span.start if span and span.start else None) or start or plan_dates.default_start(now, list(meals))
    minutes = merged.get("max_cooking_time_minutes")
    return Request(
        household_size=_household_size(text, merged.get("household_size")),
        start=start,
        days=int(days),
        meals=meals,
        allergens=tuple(sorted(set(merged.get("allergens") or []))),
        excluded=frozenset(expand_exclusions(merged.get("excluded_ingredients") or [])),
        diet=tuple(sorted(set(merged.get("dietary_preferences") or []))),
        halal=bool(merged.get("requires_halal")),
        max_minutes=minutes if minutes and minutes < NO_LIMIT_MINUTES else None,
        weekly_budget_sgd=merged.get("weekly_budget_sgd"),
        max_uses=1 if merged.get("max_uses_per_recipe") == 1 else MAX_USES,
    )


@lru_cache(maxsize=1)
def _catalog(root: Path) -> tuple[list[dict], dict[str, float], dict[str, list[str]]]:
    """Priced recipes, the cheapest frozen price per gram of each ingredient, and each recipe's steps."""
    import json

    catalog = load_release_catalog(root, RELEASE)
    per_gram: dict[str, float] = {}
    for product in catalog.products:
        if product["package_size"] > 0:
            price = product["price_sgd"] / product["package_size"]
            key = product["ingredient_id"]
            per_gram[key] = min(price, per_gram.get(key, price))
    steps = {}
    for line in (root / RELEASE / "recipes.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        steps[record["recipe_id"]] = [str(step) for step in record.get("instructions") or [] if str(step).strip()]
    return catalog.recipes, per_gram, steps


def candidates(request: Request, resources: BaselineResources, root: Path) -> dict[str, list[Candidate]]:
    """Each meal-role's eligible recipes in the fixed priority order."""
    recipes, per_gram, steps = _catalog(root)
    people = request.household_size or 1
    eligible: list[Candidate] = []
    for recipe in recipes:
        keys = [line["ingredient"] for line in recipe["ingredients"]]
        minutes = recipe["prep_time_minutes"] + recipe["cook_time_minutes"]
        if request.max_minutes is not None and minutes > request.max_minutes:
            continue
        if any(key in request.excluded for key in keys):
            continue
        if request.allergens:
            facts = [resources.ingredient_facts.get(key) for key in keys]
            if any(fact is None or fact.allergens is None for fact in facts):
                continue  # unknown allergens are never served to a household that stated one
            if any(set(fact.allergens) & set(request.allergens) for fact in facts):  # type: ignore[union-attr]
                continue
        if any(tag not in recipe["dietary_tags"] for tag in request.diet):
            continue
        if request.halal and recipe_halal_status(keys) != "halal":
            continue
        scale = people / recipe["servings"]
        cost = sum(line["quantity"] * scale * per_gram.get(line["ingredient"], 0.0) for line in recipe["ingredients"])
        eligible.append(Candidate(recipe, round(cost, 4), minutes, steps.get(recipe["slug"]) or [recipe["title"]]))
    eligible.sort(key=lambda item: (item.cost_sgd, item.minutes, item.recipe["slug"]))
    by_role: dict[str, list[Candidate]] = {}
    for meal, roles in request.meals.items():
        for role in roles:
            kind = "breakfast" if meal == "breakfast" else "single" if len(roles) == 1 else role.split("-")[0]
            by_role[f"{meal}/{role}"] = [
                c for c in eligible if meal in c.recipe["meal_types"] and _fits(c.recipe, kind)
            ]
    return by_role


def _fits(recipe: dict, kind: str) -> bool:
    """The course a role takes, big enough for it, a main with its protein, a vegetable dish led by vegetables."""
    nutrients = recipe["nutrients"]
    return (
        recipe["course"] in COURSES[kind]
        and nutrients["calories_kcal"] >= ENERGY_FLOOR[kind]
        and nutrients["protein_g"] >= PROTEIN_FLOOR.get(kind, 0)
        and (kind != "vegetable" or row_vegetable_led(recipe))
    )


def plan(request: Request, resources: BaselineResources, root: Path) -> UnifiedOutput:
    pools = candidates(request, resources, root)
    people = request.household_size or 1
    uses: Counter[str] = Counter()
    yesterday: set[str] = set()
    meals: list[PlanMeal] = []
    missing: list[str] = []
    total = 0.0
    for offset in range(request.days):
        day = request.start + timedelta(days=offset)
        today: set[str] = set()
        for meal, roles in request.meals.items():
            dishes: list[PlanDish] = []
            for role in roles:
                pool = pools[f"{meal}/{role}"]
                fresh = [
                    c
                    for c in pool
                    if c.recipe["slug"] not in today | yesterday and uses[c.recipe["slug"]] < request.max_uses
                ]
                allowed = fresh or [
                    c for c in pool if c.recipe["slug"] not in today and uses[c.recipe["slug"]] < request.max_uses
                ]
                if not allowed:
                    missing.append(f"{day.isoformat()} {meal} {role}")
                    continue
                chosen = allowed[0]
                slug = chosen.recipe["slug"]
                uses[slug] += 1
                today.add(slug)
                total += chosen.cost_sgd
                scale = people / chosen.recipe["servings"]
                dishes.append(
                    PlanDish(
                        name=chosen.recipe["title"],
                        role=role,
                        recipe_reference=slug,
                        servings=people,
                        evidence={
                            "ingredients": [
                                {
                                    "name": resources.names.get(line["ingredient"], line["ingredient"]),
                                    "quantity_g": grams,
                                }
                                for line in chosen.recipe["ingredients"]
                                if (grams := round(line["quantity"] * scale, 1)) > 0
                            ],
                            "steps": chosen.steps,
                            "cooking_time_minutes": chosen.minutes,
                        },
                    )
                )
            if dishes:
                meals.append(PlanMeal(date=day, meal_type=meal, dishes=dishes))
        yesterday = today
    if not meals:
        return UnifiedOutput(refusal="No recipe in the catalog satisfies the stated limits.")
    answer = f"Planned {len(meals)} meals for {people}; estimated groceries S${total:.2f}."
    if request.weekly_budget_sgd is not None and total * 7 / request.days > request.weekly_budget_sgd:
        answer += f" This is above the stated budget of S${request.weekly_budget_sgd:.2f}."
    if missing:
        answer += f" No eligible dish for: {', '.join(missing)}."
    return UnifiedOutput(
        plan=PlanOutput(
            meals=meals,
            household_size=people,
            start_date=request.start,
            end_date=request.start + timedelta(days=request.days - 1),
            horizon_days=request.days,
            total_cost_sgd=round(total, 2),
        ),
        answer=answer,
    )


def respond_to(turns: list[str], now: datetime, resources: BaselineResources, root: Path) -> UnifiedOutput:
    request = read_request(turns, now)
    if request.household_size is None:
        return UnifiedOutput(clarification=[CLARIFY_SIZE])
    return plan(request, resources, root)


def make_responder(context: baseline_arms.ArmContext, root: Path | None = None) -> Responder:
    root = root or repository_root()

    def respond(message: str, own_history: tuple[Exchange, ...], instructions: str) -> UnifiedOutput:
        # The user's own strings so far; the harness's automatic confirmation is not a user turn.
        turns = [item.message for item in own_history if not item.automatic_confirmation] + [message]
        return respond_to(turns, clock.now().astimezone(clock.SINGAPORE), context.resources, root)

    return respond


def fingerprint() -> dict[str, str]:
    return {"system_id": SYSTEM_ID, "runner_sha256": baseline_arms.source_sha256(__file__)}


ARM = baseline_arms.Arm(system_id=SYSTEM_ID, paid=False, fingerprint=fingerprint, responder=make_responder)
