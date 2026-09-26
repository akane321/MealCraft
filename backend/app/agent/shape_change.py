"""Read a request to change which meals a week plans or what a meal holds (ADR-0046 section 2).

Rules only, like the rest of replanning: "also plan lunch", "no breakfast", "lunch just one dish",
"dinners with a soup", "add a soup on Friday", "今晚不要配菜". Anything else is left to the
one-dish events (swap, cancel, lock, can't buy).
"""

import re
from dataclasses import dataclass

from app.schemas.meal_plan import MEAL_PRESETS, MealPlanShapeChangeRequest, PlannedMeal, WeeklyMealPlanResponse

MEAL_NAMES: dict[PlannedMeal, tuple[str, ...]] = {
    "breakfast": ("breakfast", "早饭", "早餐"),
    "lunch": ("lunch", "午饭", "午餐", "中饭"),
    "dinner": ("dinner", "supper", "晚饭", "晚餐"),
}
DISHES = {
    "soup": (("soup", "汤"), ["soup"]),
    "vegetable": (("vegetable", "veg", "side", "salad", "蔬菜", "素菜", "配菜", "沙拉"), ["side", "salad"]),
    "main": (("another main", "meat dish", "second main", "荤菜", "主菜", "肉菜"), ["main"]),
}
ADD = ("also plan", "add", "plan", "with", "plus", "加上", "加", "也要", "安排", "多")
DROP = ("no", "drop", "without", "don't plan", "do not plan", "stop planning", "不要", "不用", "去掉", "别")
# Between the verb and the thing: "add a soup", "without the side", "加个汤", "多一道素菜".
FILLER = r"(?:\s*(?:a|an|the|another|one more|个|一个|一道|道|上)?\s*)?"
ONE_DISH = ("one dish", "just one", "only one", "single dish", "一道菜", "一个菜", "只要一道", "只要一个")
TONIGHT = ("tonight", "今晚")


@dataclass(frozen=True)
class ShapeChangeIntent:
    request: MealPlanShapeChangeRequest
    # What the assistant says it understood, before the preview.
    summary: str


def _alternatives(words: tuple[str, ...]) -> str:
    return "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))


def _has(text: str, words: tuple[str, ...]) -> bool:
    # A trailing "s" still names it: "dinners with a soup".
    return re.search(rf"(?<![a-z])(?:{_alternatives(words)})s?(?![a-z])", text) is not None


def _verb_then(text: str, verbs: tuple[str, ...], words: tuple[str, ...]) -> bool:
    """A verb directly followed by the thing: "no breakfast", but not "no pork for dinner"."""
    pattern = rf"(?<![a-z])(?:{_alternatives(verbs)}){FILLER}(?:{_alternatives(words)})s?(?![a-z])"
    return re.search(pattern, text) is not None


def _next_id(roles: list[dict], base: str) -> str:
    taken = {role["role_id"] for role in roles}
    return base if base not in taken else next(f"{base}-{n}" for n in range(2, 10) if f"{base}-{n}" not in taken)


def read_shape_change(message: str, *, plan: WeeklyMealPlanResponse, day_index: int | None) -> ShapeChangeIntent | None:
    """The shape change a message asks for, or None when it asks for something else.

    `day_index` is the day the message names, if any (read by the replan interpreter); tonight
    names dinner as well as today.
    """
    text = f" {message.strip().lower()} "
    meal = next((name for name, words in MEAL_NAMES.items() if _has(text, words)), None)
    if meal is None and _has(text, TONIGHT):
        meal = "dinner"
    dish = next((role for role, (words, _) in DISHES.items() if _has(text, words)), None)
    target = DISHES[dish][0] if dish else MEAL_NAMES.get(meal or "", ())
    adds, drops = _verb_then(text, ADD, target), _verb_then(text, DROP, target)
    if not (adds or drops or _has(text, ONE_DISH)) or (meal is None and dish is None):
        return None
    meal = meal or "dinner"
    shape = plan.plan_shape.meals if plan.plan_shape is not None else {}
    current = [role.model_dump() for role in shape.get(meal, [])]
    days = [day_index] if day_index is not None else None
    date = next((day.planned_date for day in plan.days if day.day_index == day_index), None)
    when = f"on {date:%A}" if date else "that day" if days else "for the rest of this week"

    if dish is None:
        if _has(text, ONE_DISH):
            roles = list(MEAL_PRESETS[meal].values())[0] if meal != "dinner" else MEAL_PRESETS["dinner"]["one main"]
            summary = f"{meal.capitalize()} as one dish {when}"
        elif drops:
            roles, summary = None, f"No {meal} {when}"
        elif meal not in shape:
            roles, summary = list(MEAL_PRESETS[meal].values())[0], f"{meal.capitalize()} added {when}"
        else:
            return None  # "plan dinner" when dinner is planned: nothing to change
    else:
        if not current:
            current = list(MEAL_PRESETS[meal].values())[0]
        base, courses = dish, DISHES[dish][1]
        if drops:
            kept = [role for role in current if not set(role["courses"]) & set(courses) or role["role_id"] == "main"]
            if dish == "main":
                kept = [role for role in current if role["role_id"] != "main" or len(current) == 1]
            if len(kept) == len(current) or not kept:
                return None
            if not any(role.get("required", True) for role in kept):
                kept[0] = {**kept[0], "required": True}
            roles, summary = kept, f"{meal.capitalize()} without the {dish} {when}"
        elif len(current) >= 6:
            return None
        else:
            role_id = _next_id(current, base)
            roles = [*current, {"role_id": role_id, "courses": courses, "required": True}]
            summary = f"{meal.capitalize()} with {'another' if role_id != base else 'a'} {dish} {when}"
    return ShapeChangeIntent(
        request=MealPlanShapeChangeRequest.model_validate(
            {"meal_type": meal, "roles": roles, "day_indexes": days, "reason": message.strip()}
        ),
        summary=summary,
    )
