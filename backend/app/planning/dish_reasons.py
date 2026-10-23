"""Reason tags on a saved week's dishes (layer 08 section 7.2, ADR-0087): short facts that are true of a dish.

Computed when the week is read, from what the week saved, so a swap or a meal change that rewrites an entry
changes its tags with it. Three kinds only, in this order, at most two a dish, none when nothing holds:

- `preference`: a main within the benchmark the recommendation score uses for each health preference the week
  was planned with ("Fits low-sodium").
- `cheap_main`: with at least 4 different mains still to be cooked (a skipped dish is not counted), a main in the
  cheapest quarter per serving. The cost is what the week buys for it, after the pantry covered what it could.
- `quick`: ready in 20 minutes or less.

A main is a `main`, `main-2`, ... role outside breakfast. The tags say what is true of the dish, never why the
planner chose it: they never repeat the engine's own reason strings."""

from collections.abc import Iterable
from decimal import Decimal

from app.planning.recommendation_engine import (
    FLEXIBLE_SODIUM_BENCHMARK_MG,
    FLEXIBLE_SUGAR_BENCHMARK_G,
    LOWER_CALORIE_BENCHMARK_KCAL,
)
from app.schemas.meal_plan import DishReason

MAX_TAGS = 2
QUICK_MINUTES = 20
CHEAP_MIN_MAINS = 4
# Each preference, the nutrient the score reads and its benchmark (`RecipeRecommendationEngine._nutrition_score`).
PREFERENCES = {
    "low-sodium": ("sodium_mg", FLEXIBLE_SODIUM_BENCHMARK_MG),
    "low-sugar": ("sugar_g", FLEXIBLE_SUGAR_BENCHMARK_G),
    "lower-calorie": ("calories_kcal", LOWER_CALORIE_BENCHMARK_KCAL),
}


def is_main(entry) -> bool:
    role = entry.role_id or ""
    return entry.meal_type != "breakfast" and (role == "main" or role.startswith("main-"))


def cost_per_serving(entry, household_size: int) -> float | None:
    """What one serving of the dish costs to buy, after the pantry deduction: its consumed cost over the servings
    it was cooked for, which are the household size at its portion share when no member servings were saved.
    None when the cost is not known."""
    if entry.servings is not None:
        servings = Decimal(str(entry.servings))
    else:
        servings = household_size * Decimal(str(entry.portion_share))
    cost = Decimal(str(entry.consumed_cost_sgd))
    if servings <= 0 or cost <= 0:  # a dish with no grocery estimate is saved at 0, which is not a price
        return None
    return round(float(cost / servings), 2)


def dish_reasons(
    entries: Iterable, *, household_size: int, health_preferences: Iterable[str]
) -> dict[int, list[DishReason]]:
    """Each entry's tags by entry id; an entry with none is left out."""
    entries = list(entries)
    preferences = set(health_preferences)
    # Each different main's cheapest serving in the week; a main cheaper than at least three in four of the others
    # is one of the cheapest. Ties count against it, so a week of equal prices tags nobody.
    main_cost: dict[int, float] = {}
    for entry in entries:
        cost = cost_per_serving(entry, household_size) if is_main(entry) and entry.status != "skipped" else None
        if cost is not None:
            main_cost[entry.recipe_id] = min(cost, main_cost.get(entry.recipe_id, cost))
    cheap_count = len(main_cost) // 4 if len(main_cost) >= CHEAP_MIN_MAINS else 0
    cheap = {
        recipe_id
        for recipe_id, cost in main_cost.items()
        if sum(other <= cost for other in main_cost.values()) <= cheap_count
    }

    tags: dict[int, list[DishReason]] = {}
    for entry in entries:
        found: list[DishReason] = []
        if is_main(entry):
            nutrition = entry.recipe.nutrition
            fits = [
                name
                for name, (nutrient, benchmark) in PREFERENCES.items()
                if name in preferences and float(getattr(nutrition, nutrient)) <= benchmark
            ]
            if fits:
                found.append(DishReason(code="preference", label=f"Fits {', '.join(fits)}"))
            if entry.recipe_id in cheap:
                found.append(DishReason(code="cheap_main", label="One of the week's cheapest mains"))
        minutes = entry.recipe.total_time_minutes
        if 0 < minutes <= QUICK_MINUTES:
            found.append(DishReason(code="quick", label=f"Ready in {minutes} min"))
        if found:
            tags[entry.id] = found[:MAX_TAGS]
    return tags
