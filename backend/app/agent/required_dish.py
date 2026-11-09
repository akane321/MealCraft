"""A dish the household names for this plan: found in the catalog and placed in a role, never against what keeps
anyone safe (owner, 2026-11-09). Several recipes can share a name; the one that fits the limits and costs least
stands for it. A name no title holds, or that several different dishes hold, is asked about, not guessed.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from math import inf

from app.agent.limits import Refusal, day_name
from app.agent.replies import listed, say, word
from app.data import meal_structure
from app.planning import alternatives
from app.planning.household_slots import slot_servings
from app.planning.meal_composition import catalog_role_admits
from app.planning.member_coverage import catalog_can_eat, member_limits
from app.planning.product_path import dish_cost
from app.planning.recipe_pair_similarity import RecipePairIndex
from app.planning.recipe_similarity import in_english, recipe_key, shared_words
from app.schemas.agent import DishAsked, OfferedChange
from app.schemas.display import shown_title
from app.schemas.meal_plan import RequiredDish, WeeklyMealPlanRequest
from app.schemas.planning_v2 import structured

FIELD = "required_dish"
# Words a name can drop without naming another dish: "chicken and rice" is "Chicken & Rice".
NOT_NAMING = {"and", "with", "the"}
# Recipes of one name, and dishes of no name, looked at; the rest of a long list adds nothing to ask about.
LOOKED_AT = 8
OFFERED = 3


@dataclass(frozen=True)
class Replacement:
    """A dish that could take the pinned dish's place, and what it saves: its cost to cook, its kcal a serving."""

    dish: RequiredDish
    saved_sgd: float
    saved_kcal: float


def _name_words(text: str) -> set[str]:
    return {found.removesuffix("s") for found in re.findall(r"[a-z]{3,}|\d+", text.lower())} - NOT_NAMING


def _kcal(recipe) -> float:
    return float(recipe.nutrition.calories_kcal)


def _place(recipe, request: WeeklyMealPlanRequest, meal: str | None) -> tuple[str, str] | None:
    """The (meal, role) a dish takes: the meal it was named for, else the latest meal that has a role for it."""
    for name in [meal] if meal else ["dinner", "lunch", "breakfast"]:
        for role in request.plan_shape.meals.get(name, []):
            if (role.min_people or 0) <= request.household_size and catalog_role_admits(role, recipe):
                return name, role.role_id
    return None


def _why(reasons: list[str], lang: str) -> str:
    def kind(reason: str) -> str:
        if "halal" in reason:
            return "pin_halal"
        if "excluded" in reason or "mentions" in reason:
            return "pin_excluded"
        if "requirement" in reason or "dietary" in reason:
            return "pin_diet"
        return "pin_never" if "again" in reason else "pin_allergy"

    return listed([say(key, lang) for key in dict.fromkeys(map(kind, reasons))], lang)


def resolve(
    asked: DishAsked,
    request: WeeklyMealPlanRequest,
    recipes: list,
    ranked: list,
    blockers: Callable[..., list[str] | None],
    lang: str,
    every_course: Callable[[], list] = list,
) -> RequiredDish | Refusal:
    """The dish `asked` names, placed in this plan, or the reply that says why not (a question when it can ask one).

    `blockers(recipe)` says why the household's limits rule a recipe out, [] for none, None for no price;
    `every_course()` is the recipes this plan's meals do not draw on, to tell a dish with no place from no such dish."""
    days = [(request.start_date + timedelta(days=day)).strftime("%A").lower() for day in range(request.day_count)]
    if asked.weekday is not None and asked.weekday not in days:
        return Refusal(FIELD, say("pin_not_in_plan", lang, day=day_name(asked.weekday, lang)))
    if asked.meal is not None and asked.meal not in request.plan_shape.meals:
        return Refusal(FIELD, say("pin_not_in_plan", lang, day=word(asked.meal, lang)))
    cost = {item.recipe.slug: dish_cost(item) for item in ranked}
    ceiling = request.nutrition_constraints[0].upper if request.nutrition_constraints else None

    def pinned(recipe) -> RequiredDish:
        meal, role_id = _place(recipe, request, asked.meal)
        return RequiredDish(
            recipe_slug=recipe.slug,
            title=shown_title(recipe.title),
            meal=meal,
            role_id=role_id,
            weekday=asked.weekday,
            kcal=_kcal(recipe),
        )

    members = member_limits(request.household)

    def trouble(recipe) -> list[str] | None:
        """What stops this household eating the recipe: [] for nothing, None when it has no price."""
        found = blockers(recipe)
        lines = alternatives.lines(recipe, request)
        out = [member.name for member in members if not catalog_can_eat(member, recipe, lines)]
        return found if found is None or found or not out else [f"member:{name}" for name in out]

    def too_late(recipe) -> bool:
        """Its fresh food would not keep to the day named (ADR-0072's days after a shopping trip)."""
        rules_on = request.household is not None or structured(
            request.plan_shape.meals[_place(recipe, request, asked.meal)[0]]
        )
        since_trip = days.index(asked.weekday) % meal_structure.trip_days() + 1 if asked.weekday else 1
        fresh = any(line.ingredient.perishable is True for line in recipe.recipe_ingredients)
        return rules_on and fresh and since_trip > meal_structure.perishable_days()

    def first_safe(group: list) -> tuple[object | None, list[str] | None]:
        """The recipe of this name that fits the limits and costs least, else why the first of them cannot be."""

        def fits_best(recipe) -> tuple:
            return (
                too_late(recipe),
                ceiling is not None and _kcal(recipe) > ceiling,
                cost.get(recipe.slug, inf),
                recipe.slug,
            )

        first_trouble: list[str] | None = None
        for index, recipe in enumerate(sorted(group, key=fits_best)[:LOOKED_AT]):
            found = trouble(recipe)
            if found == []:
                return recipe, None
            if index == 0:
                first_trouble = found
        return None, first_trouble

    def kept_fresh(recipe) -> RequiredDish | Refusal:
        """The dish pinned, or the reply when its fresh food would not keep to the day named."""
        dish, days_kept = pinned(recipe), meal_structure.perishable_days()
        if not too_late(recipe):
            return dish
        latest = dish.model_copy(update={"weekday": days[days_kept - 1]})
        day, last = day_name(dish.weekday, lang), day_name(latest.weekday, lang)
        said = say("pin_move", "en", day=last)
        text = say("pin_not_fresh", lang, title=dish.title, kept=days_kept, day=day, last=last)
        return Refusal(FIELD, text, ((said, said),), changes=(OfferedChange(value=said, required_dish=latest),))

    def said_unsafe(group: list, found: list[str] | None) -> Refusal:
        title = shown_title(group[0].title)
        names = [reason.removeprefix("member:") for reason in found or () if reason.startswith("member:")]
        if found is None:
            return Refusal(FIELD, say("pin_unpriced", lang, title=title))
        why = say("pin_member", lang, names=listed(names, lang)) if names else _why(found, lang)
        return Refusal(FIELD, say("pin_unsafe", lang, title=title, why=why))

    def ask(titles: list[str], groups: dict, key: str) -> Refusal:
        """The dishes `asked` may mean, each a tap, for those that are safe and have a place in this plan."""
        offered = []
        for title in titles:
            recipe, _ = first_safe(groups[title])
            if recipe is not None and not too_late(recipe):
                offered.append((title, pinned(recipe)))
            if len(offered) == OFFERED:
                break
        if not offered:
            return Refusal(FIELD, say("pin_no_match", lang, name=asked.name))
        options = tuple((title, title) for title, _ in offered)
        changes = tuple(OfferedChange(value=title, required_dish=dish) for title, dish in offered)
        return Refusal(FIELD, say(key, lang, name=asked.name), options, changes=changes)

    wanted = _name_words(in_english(asked.name))
    named = [
        recipe
        for recipe in recipes
        if wanted and wanted <= _name_words(shown_title(recipe.title)) and _place(recipe, request, asked.meal)
    ]
    if not named:
        titled = [r for r in [*recipes, *every_course()] if wanted and wanted <= _name_words(shown_title(r.title))]
        if titled:  # the dish exists; no meal of this plan has a role for it
            return Refusal(FIELD, say("pin_no_place", lang, title=shown_title(titled[0].title)))
        placed = [recipe for recipe in recipes if _place(recipe, request, asked.meal)]
        scores = shared_words(in_english(asked.name), placed)
        near = sorted((r for r in placed if scores.get(r.id)), key=lambda r: (-scores[r.id], r.slug))
        groups = _groups(near[:LOOKED_AT])
        return ask(list(groups), groups, "pin_not_found")
    same = [recipe for recipe in named if _name_words(shown_title(recipe.title)) == wanted]
    groups = _groups(named)
    if same or len(groups) == 1:
        group = same or named
        recipe, found = first_safe(group)
        return kept_fresh(recipe) if recipe is not None else said_unsafe(group, found)
    # Fewest extra words first: the title closest to what was said.
    return ask(sorted(groups, key=lambda title: (len(_name_words(title)), title)), groups, "pin_which")


def _groups(recipes: list) -> dict[str, list]:
    groups: dict[str, list] = {}
    for recipe in recipes:
        groups.setdefault(shown_title(recipe.title), []).append(recipe)
    return groups


def _home_share(pin: RequiredDish, request: WeeklyMealPlanRequest) -> float:
    """The part of the household at the pinned meal: a dish's cost is for all of it, the meal is cooked for who is home
    (the first day it can go, as the planner places it)."""
    household = request.household
    if household is None or household.members is None:
        return 1.0
    days = [request.start_date + timedelta(days=day) for day in range(request.day_count)]
    home = [
        slot_servings(household, day, pin.meal) for day in days if pin.weekday in (None, day.strftime("%A").lower())
    ]
    return next(filter(None, home), request.household_size) / request.household_size


def similar(pin: RequiredDish, request: WeeklyMealPlanRequest, recipes: list, ranked: list) -> list[Replacement]:
    """Dishes that could fill the pinned dish's role and that everyone can eat, the most alike first (the catalog's
    embeddings where both have one, else the ingredients they share)."""
    by_slug, items = {recipe.slug: recipe for recipe in recipes}, {item.recipe.slug: item for item in ranked}
    pinned = by_slug.get(pin.recipe_slug)
    role = next((role for role in request.plan_shape.meals.get(pin.meal, []) if role.role_id == pin.role_id), None)
    if pinned is None or pin.recipe_slug not in items or role is None:
        return []
    members = member_limits(request.household)
    others = [
        by_slug[slug]
        for slug in items
        if slug in by_slug
        and slug != pin.recipe_slug
        and shown_title(by_slug[slug].title) != pin.title  # "Chicken Curry, instead of Chicken Curry" says nothing
        and catalog_role_admits(role, by_slug[slug])
        and all(
            catalog_can_eat(member, by_slug[slug], alternatives.lines(by_slug[slug], request)) for member in members
        )
    ]
    index = RecipePairIndex([pinned, *others])

    def likeness(recipe) -> float:
        signals = index.compare(recipe_key(pinned), recipe_key(recipe))
        return signals.vector_cosine if signals.vector_cosine is not None else signals.ingredient_overlap or 0.0

    cost, share = dish_cost(items[pin.recipe_slug]), _home_share(pin, request)
    return [
        Replacement(
            RequiredDish(
                recipe_slug=recipe.slug,
                title=shown_title(recipe.title),
                meal=pin.meal,
                role_id=pin.role_id,
                weekday=pin.weekday,
                kcal=_kcal(recipe),
            ),
            round((cost - dish_cost(items[recipe.slug])) * share, 2),
            round(pin.kcal - _kcal(recipe)),
        )
        for recipe in sorted(others, key=lambda r: (-likeness(r), r.slug))
    ]
