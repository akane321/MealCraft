"""When a week starts, read from the request that sets it up (2026-10-12, owner).

Rules only: "next week", "from tomorrow", "starting Wednesday", "from next Monday", "Wednesday onwards",
"starting 19 Oct", "start on 2026-10-19", 下周, 明天开始, 从周三开始, 下周一开始, 10月19日开始. A weekday is read as a
start only with a start word ("from", "starting", 开始, 起), so "no soup on Friday" stays a change to a meal.

With no start said, the week starts today, or tomorrow once today's last planned meal is past.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3,
    "thurs": 3, "thur": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}  # fmt: skip
ZH_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
MONTHS = {
    name: index
    for index, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
         ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
         ("nov", "november"), ("dec", "december")],
        start=1,
    )
    for name in names
}  # fmt: skip
# Past this hour (Singapore) a meal of today is over: a week planned later starts tomorrow.
MEAL_ENDS = {"breakfast": 10, "lunch": 15, "dinner": 21}

_WEEKDAY = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
# Before a number "may" is the verb ("I may 3 ..."); "3 May" still reads as a date.
_MONTH_FIRST = "|".join(sorted((m for m in MONTHS if m != "may"), key=len, reverse=True))
_START_EN = r"(?:from|starting(?:\s+on)?|start(?:ing)?\s+on|start|beginning(?:\s+on)?|begin(?:ning)?)"
_ZH_DAY = r"(?:周|星期|礼拜)([一二三四五六日天])"


@dataclass(frozen=True)
class StartSaid:
    start: date
    # The words that said it, so a reader of the rest of the message (the meal shape) does not take them for days.
    words: str


def _next(today: date, weekday: int, *, next_week: bool = False) -> date:
    """The coming `weekday`, today included; "next Monday" is the following week's."""
    if next_week:
        monday = today + timedelta(days=7 - today.weekday())
        return monday + timedelta(days=weekday)
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _on_or_after(today: date, month: int, day: int) -> date | None:
    """A day and month without a year: this year's, or next year's once it is well past."""
    try:
        found = date(today.year, month, day)
    except ValueError:
        return None
    return found if found >= today - timedelta(days=60) else found.replace(year=today.year + 1)


def read_start(message: str, today: date) -> StartSaid | None:
    """The first day of the week a request names, or None when it names none."""
    text = message.lower()
    if found := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        try:
            return StartSaid(date(*map(int, found.groups())), found.group(0))
        except ValueError:
            return None
    if found := re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\b|\b({_MONTH_FIRST})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text
    ):
        day, month = (found.group(1), found.group(2)) if found.group(1) else (found.group(4), found.group(3))
        start = _on_or_after(today, MONTHS[month], int(day))
        return StartSaid(start, found.group(0)) if start else None
    if found := re.search(r"(\d{1,2})月(\d{1,2})[日号]", text):
        start = _on_or_after(today, int(found.group(1)), int(found.group(2)))
        return StartSaid(start, found.group(0)) if start else None
    if found := re.search(r"\bnext\s+week\b|下(?:个)?(?:周|星期|礼拜)(?![一二三四五六日天])", text):
        return StartSaid(_next(today, 0, next_week=True), found.group(0))
    if found := re.search(rf"\b{_START_EN}\s+tomorrow\b|\btomorrow\s+onwards?\b|从?明天(?:开始|起)", text):
        return StartSaid(today + timedelta(days=1), found.group(0))
    if found := re.search(rf"\b{_START_EN}\s+(next\s+)?({_WEEKDAY})\b|\b(next\s+)?({_WEEKDAY})\s+onwards?\b", text):
        nxt, name = (found.group(1), found.group(2)) if found.group(2) else (found.group(3), found.group(4))
        return StartSaid(_next(today, WEEKDAYS[name], next_week=bool(nxt)), found.group(0))
    if found := re.search(rf"从?(下)?{_ZH_DAY}(?:开始|起)", text):
        return StartSaid(_next(today, ZH_WEEKDAYS[found.group(2)], next_week=bool(found.group(1))), found.group(0))
    return None


def default_start(now: datetime, meals: list[str]) -> date:
    """Today, or tomorrow once the last meal planned today is over."""
    last = max((MEAL_ENDS.get(meal, 21) for meal in meals), default=21)
    return now.date() + timedelta(days=1) if now.hour >= last else now.date()
