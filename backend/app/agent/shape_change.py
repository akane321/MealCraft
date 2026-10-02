"""Read a request to change which meals a week plans or what a meal holds (ADR-0046 section 2).

Rules only, like the rest of replanning: "also plan lunch", "no breakfast", "lunch just one dish",
"dinners with a soup", "add a soup on weekends", "take lunch off Monday to Friday", "今晚不要配菜",
"汤都免了吧", "午饭也帮我们安排上", "周五晚饭只做一道主菜就行". Anything else is left to the
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
    "main": (("main", "another main", "meat dish", "second main", "荤菜", "主菜", "肉菜"), ["main"]),
}
# Chinese verbs also come after the thing: "汤加上", "早饭就不做了", "午饭也帮我们安排上".
ADD_ZH = ("加上", "加", "也要", "安排", "排上", "排", "煮", "做", "多")
DROP_ZH = (
    "不要",
    "不需要",
    "不用",
    "不必",
    "不吃",
    "不做",
    "不煮",
    "不排",
    "不加",
    "别做",
    "别煮",
    "别加",
    "别",
    "去掉",
    "免了",
    "免掉",
)
ADD = ("also plan", "add", "plan", "with", "plus", *ADD_ZH)
DROP = (
    "no",
    "drop",
    "remove",
    "leave out",
    "without",
    "don't plan",
    "do not plan",
    "stop planning",
    "won't need",
    "don't need",
    "do not need",
    "no need for",
    *DROP_ZH,
)
# Between the verb and the thing: "add a soup", "without the side", "加个汤", "多一道素菜",
# "remove weekday lunches".
FILLER = (
    r"(?:\s*(?:a|an|the|another|one more|个|一个|一道|道|上)?\s*)?"
    r"(?:(?:weekday|week day|weekend|weeknight|workday|work day|working day)s?\s+)?"
)
# "lunches", "dinners".
PLURAL = "(?:es|s)?"
# A Chinese cooking verb after the verb: "不用做午饭", "不需要再准备早餐".
COOK_ZH = r"(?:再|也)?(?:做|煮|排|安排|准备)?"
ONE_DISH = (
    "one dish",
    "just one",
    "only one",
    "single dish",
    "一道菜",
    "一个菜",
    "只要一道",
    "只要一个",
    "只做一道",
    "只煮一道",
    "只排一道",
    "一道就好",
    "一道就行",
    "一道就可以",
    "一个就好",
    "一个就行",
    "一个就可以",
)
# "just a main", "只做一道主菜": one dish of that kind, not the meal's usual one-dish preset.
ONLY = ("just", "only", "只做", "只煮", "只排", "只安排", "只要", "只有", "只")
ONE = ("one", "a", "an", "single", "一道", "一个", "一")
TONIGHT = ("tonight", "今晚")


@dataclass(frozen=True)
class ShapeChangeIntent:
    request: MealPlanShapeChangeRequest
    # What the assistant says it understood, before the preview.
    summary: str


def _alternatives(words: tuple[str, ...]) -> str:
    return "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))


def _has(text: str, words: tuple[str, ...]) -> bool:
    # A plural still names it: "dinners with a soup", "weekday lunches off".
    return re.search(rf"(?<![a-z])(?:{_alternatives(words)}){PLURAL}(?![a-z])", text) is not None


def _verb_near(text: str, verbs: tuple[str, ...], after: tuple[str, ...], words: tuple[str, ...]) -> bool:
    """A verb right before the thing ("no breakfast", but not "no pork for dinner"), or a Chinese
    verb a few words after it ("汤都免了吧", "午饭也帮我们安排上")."""
    thing = rf"(?:{_alternatives(words)}){PLURAL}(?![a-z])"
    before = rf"(?<![a-z])(?:{_alternatives(verbs)}){COOK_ZH}{FILLER}{thing}"
    behind = rf"(?<![a-z]){thing}[^,，。.;；]{{0,6}}(?:{_alternatives(after)})"
    return re.search(before, text) is not None or re.search(behind, text) is not None


def _taken_off(text: str, words: tuple[str, ...]) -> bool:
    """ "take lunch off", "leave the soup out", "take it off" once the meal is named, "weekday lunches off"."""
    thing = rf"{FILLER}(?:{_alternatives(words)}){PLURAL}|\s+(?:it|them|that)"
    taken = rf"(?<![a-z])(?:take|leave)(?:{thing})\s+(?:off|out|away)(?![a-z])"
    off = rf"(?<![a-z])(?:{_alternatives(words)}){PLURAL}\s+(?:off|not needed)(?![a-z])"
    return re.search(taken, text) is not None or re.search(off, text) is not None


def _only_one(text: str) -> str | None:
    """The one dish a meal is cut to ("just a main", "只做一道主菜"), or None when no dish is counted."""
    for role, (words, _) in DISHES.items():
        counted = (
            rf"(?:{_alternatives(ONLY)})\s*(?:{_alternatives(ONE)})?\s*(?:{_alternatives(words)}){PLURAL}(?![a-z])"
        )
        if re.search(rf"(?<![a-z]){counted}", text):
            return role
    return None


def _next_id(roles: list[dict], base: str) -> str:
    taken = {role["role_id"] for role in roles}
    return base if base not in taken else next(f"{base}-{n}" for n in range(2, 10) if f"{base}-{n}" not in taken)


def _when(plan: WeeklyMealPlanResponse, days: list[int] | None) -> str:
    """ "on Friday", "on Saturday and Sunday", "on weekdays"; the rest of the week when no day is named."""
    if days is None:
        return "for the rest of this week"
    dates = sorted({day.planned_date for day in plan.days if day.day_index in days}, key=lambda day: day.weekday())
    if not dates:
        return "that day" if len(days) == 1 else "those days"
    if [day.weekday() for day in dates] == [0, 1, 2, 3, 4]:
        return "on weekdays"
    names = [f"{day:%A}" for day in dates]
    return "on " + (f"{', '.join(names[:-1])} and {names[-1]}" if len(names) > 1 else names[0])


def _day_roles(plan: WeeklyMealPlanResponse, meal: str, days: list[int] | None, planned: list[dict]) -> list[dict]:
    """The dish roles the named days' meal has now, read from its dishes: a one-day change ("add a soup on
    Friday", "plan lunch on Friday") may have given a day a dish or a meal the week's shape lacks. The week's
    shape when no day is named, or the days differ."""
    by_day: dict[int, list[str]] = {}
    courses: dict[str, set[str]] = {}
    for dish in plan.days if days else []:
        if dish.day_index in days and dish.meal_type == meal and dish.status != "skipped":
            by_day.setdefault(dish.day_index, []).append(dish.role_id)
            courses.setdefault(dish.role_id, set()).add(dish.recipe.course or "main")
    if len({frozenset(ids) for ids in by_day.values()}) != 1:
        return planned
    # The week's roles, then the presets' in order: a meal the week lacks is added for a day with its first
    # preset, so a lunch "main" added for Friday takes a main, a salad or a soup ("one dish").
    known = {role["role_id"]: role for role in planned}
    for preset in MEAL_PRESETS[meal].values():
        for role in preset:
            known.setdefault(role["role_id"], role)
    roles = []
    for role_id in next(iter(by_day.values())):
        # A dish added in the conversation is "soup", "soup-2", "main-2" (see _next_id).
        base = DISHES.get(role_id.split("-")[0])
        role = known.get(role_id) or (base and {"role_id": role_id, "courses": base[1], "required": True})
        if not role:
            return planned
        # Each role takes the dish the day has: Friday's one-dish lunch may hold a salad as its main on a week
        # whose lunches are a main and a side.
        extra = sorted(courses[role_id] - set(role["courses"]))
        roles.append({**role, "courses": [*role["courses"], *extra]} if extra else role)
    return roles


def _read(message: str) -> tuple[str, str | None, str | None, bool, bool, str | None] | None:
    """The text, meal, dish, add, drop and only-one a message names; None when it changes no meal."""
    text = f" {message.strip().lower()} "
    meal = next((name for name, words in MEAL_NAMES.items() if _has(text, words)), None)
    if meal is None and _has(text, TONIGHT):
        meal = "dinner"
    dish = next((role for role, (words, _) in DISHES.items() if _has(text, words)), None)
    target = DISHES[dish][0] if dish else MEAL_NAMES.get(meal or "", ())
    adds = _verb_near(text, ADD, ADD_ZH, target)
    drops = _verb_near(text, DROP, DROP_ZH, target) or _taken_off(text, target)
    only = _only_one(text)
    if not (adds or drops or only or _has(text, ONE_DISH)) or (meal is None and dish is None):
        return None
    return text, meal, dish, adds, drops, only


def asks_for_shape(message: str) -> bool:
    """Whether a message (or one clause of it) adds, drops or recomposes a meal."""
    return _read(message) is not None


def read_shape_change(
    message: str, *, plan: WeeklyMealPlanResponse, day_indexes: list[int] | None
) -> ShapeChangeIntent | None:
    """The shape change a message asks for, or None when it asks for something else.

    `day_indexes` are the days the message names, if any (read by the replan interpreter); tonight
    names dinner as well as today.
    """
    read = _read(message)
    if read is None:
        return None
    text, meal, dish, adds, drops, only = read
    meal = meal or "dinner"
    shape = plan.plan_shape.meals if plan.plan_shape is not None else {}
    days = day_indexes or None
    current = _day_roles(plan, meal, days, [role.model_dump() for role in shape.get(meal, [])])
    when = _when(plan, days)

    if only:
        roles = [{"role_id": only, "courses": DISHES[only][1], "required": True}]
        summary = f"{meal.capitalize()} as one {only} {when}"
    elif dish is None:
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
