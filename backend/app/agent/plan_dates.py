"""When a week starts, read from the request that sets it up (2026-10-12, owner).

Rules only: "next week", "from tomorrow", "starting Wednesday", "from next Monday", "Wednesday onwards",
"starting 19 Oct", "start on 2026-10-19", 下周, 明天开始, 从周三开始, 下周一开始, 10月19日开始. A weekday is read as a
start only with a start word ("from", "starting", 开始, 起), so "no soup on Friday" stays a change to a meal.

With no start said, the week starts today, or tomorrow once today's last planned meal is past.

A short plan (owner, 2026-10-29): `read_span` reads "dinner tonight", "tomorrow's dinner", 明天晚餐, "today", "this
weekend", 周末, "the next 3 days", 接下来三天 and "dinners only" as the days and meals a request plans.
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


# The span of a short plan (owner, 2026-10-29), in a request: the days and the meals it plans.
MEAL_ORDER = ("breakfast", "lunch", "dinner")
_MEAL_EN = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "supper": "dinner", "night": "dinner",
            "evening": "dinner"}  # fmt: skip
_MEAL_ZH = {"早饭": "breakfast", "早餐": "breakfast", "早上": "breakfast", "午饭": "lunch", "午餐": "lunch",
            "中饭": "lunch", "中午": "lunch", "晚饭": "dinner", "晚餐": "dinner", "晚上": "dinner"}  # fmt: skip
_M_EN = "breakfast|lunch|dinner|supper"
_M_ZH = "|".join(_MEAL_ZH)
_LIST_EN = rf"(?:{_M_EN})s?(?:\s*(?:,|and|&|or)\s*(?:{_M_EN})s?)*"
_LIST_ZH = rf"(?:{_M_ZH})(?:[和、及](?:{_M_ZH}))*"
_NUMBERS = {name: n for n, name in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen".split(), start=1)}  # fmt: skip
_ZH_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_N = rf"\d{{1,2}}|{'|'.join(_NUMBERS)}|十[一二三四]?|[一二两三四五六七八九]"
# A meal said no ("no dinner tomorrow") leaves the plan without it.
_NEGATED = re.compile(
    rf"(?<![a-z])(?:no|not|without|skip(?:ping)?|drop|remove|except|don't|do not)\s+(?:the\s+|any\s+|a\s+)?(?:{_M_EN})"
    rf"|(?:不要|不用|不吃|不做|不需要|别|去掉|免了|免掉)\s*(?:{_M_ZH})"
)
# A meal added ("also plan lunch") is for the shape reader, not a meal this span narrows to.
_ADDED = re.compile(
    rf"(?<![a-z])(?:also|add|adding|plus|include|including)\s+(?:plan\s+)?(?:the\s+|a\s+)?(?:{_M_EN})"
    rf"|(?:也要|再加|加上|另外)\s*(?:{_M_ZH})"
)
_CLAUSE = re.compile(r"[,，;；。!！?？\n]|\.(?:\s|$)")
# Words in the clause of a day word that make it something other than a plan request: a negation or an absence ("no
# soup on the weekend", "I'm away this weekend", 周末不做饭), or food at home ("bought tofu today", "expires in 2
# days", 鸡肉放了三天). The rules are high-precision: a message like that names no span here, and the model reads it.
_NOT_A_PLAN = re.compile(
    r"(?<![a-z])(?:no|not|without|skip(?:ping)?|except|drop|remove|never|away|out|off|trip|travell?ing|holiday|vacation"
    r"|bought|buy|got|picked up|purchased|have|has|had|left|leftovers?|expir\w*|use up|using up|fridge"
    r"|last|lasts|fresh|spoil\w*|shelf)(?![a-z])|n't"
    r"|不在|不用|不要|不吃|不做|不需要|别|去掉|免了|免掉|除了|除去|出去|外出|出差|旅行|旅游|出门|买了|买的|刚买|剩|过期"
    r"|到期|冰箱|手上有|家里有|放了|能放|可以放|保质|保鲜|新鲜"
)
# The days of a plan need a plan word with them ("for 3 days", "the next 3 days", "5 days of dinners", 接下来三天,
# 三天的饭), never a duration ("in 2 days", "last 3 days", 放了三天).
_DAYS_CUE = r"(?:for|over|within|next|coming|following|upcoming|plan(?:ning)?(?:\s+for)?|rest\s+of)"
_ENGLISH_DAYS = re.compile(
    rf"\b(?:{_DAYS_CUE}\s+(?:the\s+|another\s+|about\s+)*({_N})\s+(?:more\s+)?days?"
    rf"|({_N})[\s-]days?\s+(?:of\s+)?(?:meal\s+plans?|meals?|dinners?|lunch(?:es)?|breakfasts?|food|cooking|menus?|plans?))\b"
    r"(?!\s*(?:a|per|each|every|ago|before|after|later|old)\b)(?!\s+of\s+the\s+week)"
)
_ZH_DAYS = re.compile(
    rf"(?:接下来的?|未来的?|往后|后面的?|之后的?|连续|安排|规划|计划|排|做)\s*({_N})天(?![一二三四五六日])"
    r"(?!\s*[一二两三四五六七八九十\d]+\s*[餐顿次])"
    rf"|(?<![明今后昨前每第整全周星期一二两三四五六七八九\d])({_N})天的?(?=饭|菜|晚餐|晚饭|午餐|午饭|早餐|早饭|食谱|菜单|计划|餐)"
)
# "On the weekend" and "except the weekend" are rules for a day, not a plan for the weekend.
_WEEKEND = re.compile(
    r"(?<!\bon )(?<!\bon the )(?<!\bduring )(?<!\bduring the )(?<!\bexcept )(?<!\bexcept the )(?<!\bnext )"
    r"(?<!\bevery )(?<!\beach )\bweekend\b|(?<![下每在])(?<!下个)(?<!除了)周末(?:两天)?"
)
_TODAY_TOMORROW = re.compile(
    r"\btoday\s*(?:,|and|&|then|to|through)?\s*(?:and\s+)?tomorrow\b|今天(?:和|与|跟|及|、|到|至|加)?明天"
)
_TONIGHT = re.compile(r"\btonight\b|今晚")
_TODAY = re.compile(r"\btoday\b|今天")
_TOMORROW = re.compile(r"(?<!after )\btomorrow\b|明天|明晚")
# A whole week named with no days: "this week", "the whole week", "a week of dinners", 一周, 下周 (not 下周一).
_WEEK = re.compile(
    r"\b(?:this|next|coming|upcoming)\s+week\b|\b(?:the\s+)?(?:whole|full|entire)\s+week\b"
    r"|\b(?:for|over)\s+(?:the|a)\s+(?:(?:whole|full|entire)\s+)?week\b|\ba\s+(?:(?:whole|full)\s+)?week\s+of\b"
    r"|\brest\s+of\s+(?:the|this)\s+week\b"
    r"|一周|一星期|一个星期|一礼拜|整周|整个星期|整个礼拜|[这本]一?(?:周|星期|礼拜)(?![一二三四五六日天末])"
    r"|下(?:个)?(?:周|星期|礼拜)(?![一二三四五六日天末])"
)
# An amount said per week is a budget, not a week to plan: "S$100 a week", "weekly budget", 每周预算100.
_WEEK_BUDGET = re.compile(
    r"(?:s\$|sgd|\$)\s*\d+(?:\.\d+)?[^\d,;，；。]{0,14}?\b(?:weekly|week|wk)\b|\bweekly\s+budget\b"
    r"|(?:每周|一周|这周|本周|整周)的?(?:预算|不超过|最多|大约|约|花)?\s*\d+|预算[^\d]{0,4}(?:每周|一周)"
)


@dataclass(frozen=True)
class SpanSaid:
    """The days and meals a request plans. `start` is None for the default start; `day_count` is None when the days
    are not said (a meal-only phrase); `meals` None is every meal the household plans."""

    start: date | None
    day_count: int | None
    meals: tuple[str, ...] | None
    # The day words, so a reader of the rest of the message (the meal shape) does not take them for days.
    words: tuple[str, ...] = ()
    # Today's meals were all over, so the plan starts tomorrow.
    moved: bool = False


def _count(word: str) -> int | None:
    if word.isdigit():
        found = int(word)
    elif word in _NUMBERS:
        found = _NUMBERS[word]
    elif word.startswith("十"):
        found = 10 + _ZH_DIGITS.get(word[1:], 0)
    else:
        found = _ZH_DIGITS[word]
    return found if 1 <= found <= 14 else None


def _meals_in(fragment: str, *, loose: bool = True) -> tuple[str, ...]:
    """The meals a fragment names, in the order they are eaten; `loose` takes "night" and "evening" as dinner."""
    names = rf"{_M_EN}|night|evening|{_M_ZH}" if loose else rf"{_M_EN}|{_M_ZH}"
    named = {_MEAL_EN.get(word) or _MEAL_ZH[word] for word in re.findall(names, fragment)}
    return tuple(meal for meal in MEAL_ORDER if meal in named)


def _attached_meals(text: str, found: re.Match) -> tuple[str, ...]:
    """The meals said right with a day: "tomorrow's dinner", "dinner tomorrow", "lunch and dinner today", 明天晚餐."""
    after = re.match(
        rf"(?:'s)?\s*(?:for\s+)?(?:the\s+)?({_LIST_EN}|night|evening)|的?({_LIST_ZH})", text[found.end() :]
    )
    before = re.search(rf"({_LIST_EN})\s+(?:for\s+|on\s+)?$", text[: found.start()])
    hit = after or before
    return _meals_in(hit.group(0) if hit else "")


def _asks(text: str, found: re.Match) -> bool:
    """Whether the clause of a match is a plain request: no negation, absence or food at home (`_NOT_A_PLAN`). A meal
    said no ("no breakfast, tomorrow") is not one: it takes that meal off the plan."""
    start = max((m.end() for m in _CLAUSE.finditer(text, 0, found.start())), default=0)
    end = next((m.start() for m in _CLAUSE.finditer(text, found.end())), len(text))
    return _NOT_A_PLAN.search(_NEGATED.sub(" ", text[start:end])) is None


def _blank(found: re.Match) -> str:
    return " " * len(found.group(0))


def _pick(pattern: re.Pattern, text: str) -> re.Match | None:
    """The first match of `pattern` that is a plain request."""
    return next((found for found in pattern.finditer(text) if _asks(text, found)), None)


def reads_week(message: str) -> bool:
    """Whether a message names a whole week with no days ("this week", "the whole week", "a week of dinners", 一周,
    下周): the plan goes back to the household's week. An amount said per week is a budget, not this."""
    text = _WEEK_BUDGET.sub(" ", message.lower().replace("’", "'"))
    return _pick(_WEEK, text) is not None


def read_span(message: str, now: datetime, household_meals: tuple[str, ...] = MEAL_ORDER) -> SpanSaid | None:
    """The days and meals a request plans, or None when it names none (the week, as before).

    Today (the household's meals not yet past), tonight (today's dinner), tomorrow, today and tomorrow, this weekend
    (the coming Saturday and Sunday; today and tomorrow on a Saturday; today on a Sunday), the next N days (N up to
    14, from the default start), and a meals-only phrase ("dinners only", 只要晚餐), which narrows the meals and not
    the days.
    The meals named anywhere in the message narrow the days ("dinner for 2 tomorrow"); one said no is left out.
    A start the request names ("from Wednesday") is read by `read_start`, so its words are not days here.

    The rules are high-precision (`_NOT_A_PLAN`): a day word next to a negation or an absence, a duration or food at
    home, two kinds of day in one message, or "the day after tomorrow" reads as no span. The model's reading decides.
    """
    today = now.date()
    text = message.lower().replace("’", "'")
    if re.search(r"\bday after\b|后天", text):
        return None
    if (said := read_start(text, today)) is not None:
        text = text.replace(said.words, " ")
    # "Starting today", 从今天开始 move the start of the plan; they are not one day.
    text = re.sub(rf"\b{_START_EN}\s+(?:today|tonight)\b|从?今天(?:开始|起)", " ", text)
    only = re.search(
        rf"\b({_LIST_EN})\s+only\b|\bonly\s+(?:the\s+)?({_LIST_EN})|只(?:要|需要|做|排|安排|吃|煮|有)?({_LIST_ZH})",
        text,
    )
    meals: tuple[str, ...] | None = _meals_in(only.group(0)) if only else None
    # "Today and tomorrow" is read first and blanked, so neither word is read again alone.
    pair = _pick(_TODAY_TOMORROW, text)
    if pair is not None:
        text = text[: pair.start()] + " " * (pair.end() - pair.start()) + text[pair.end() :]
    kinds = [
        (kind, found)
        for kind, found in (
            ("pair", pair),
            ("weekend", _pick(_WEEKEND, text)),
            ("tonight", _pick(_TONIGHT, text)),
            ("today", _pick(_TODAY, text)),
            ("tomorrow", _pick(_TOMORROW, text)),
            ("days", _pick(_ENGLISH_DAYS, text) or _pick(_ZH_DAYS, text)),
        )
        if found is not None
    ]
    kind, word = kinds[0] if len(kinds) == 1 else (None, None)
    start: date | None = None
    days: int | None = None
    if kind == "pair":
        start, days = today, 2
    elif kind == "weekend":
        sunday = today.weekday() == 6
        start, days = (today if sunday else _next(today, 5)), 1 if sunday else 2
    elif kind in {"tonight", "today"}:
        start, days = today, 1
    elif kind == "tomorrow":
        start, days = today + timedelta(days=1), 1
    elif kind == "days":
        if (days := _count(word.group(1) or word.group(2))) is None:  # type: ignore[union-attr]
            return None
    if word is not None:
        # The meals named, not those said no or added: blanked, so the words around a day word stay where they are.
        said = _ADDED.sub(_blank, _NEGATED.sub(_blank, text))
        meals = meals or _attached_meals(said, word) or _meals_in(said, loose=False) or None
        if kind == "tonight" or word.group(0) == "明晚":
            meals = meals or ("dinner",)
        if gone := _meals_in(" ".join(found.group(0) for found in _NEGATED.finditer(text)), loose=False):
            meals = tuple(meal for meal in (meals or household_meals) if meal not in gone)
            if not meals:
                return None
    moved = False
    if kind in {"tonight", "today", "pair"}:
        # A meal of today that is over is not planned: with none left, the plan starts tomorrow. Today and tomorrow
        # keep every meal, for tomorrow's sake, while any of today's is left.
        left = tuple(meal for meal in (meals or household_meals) if now.hour < MEAL_ENDS[meal])
        if left and kind != "pair":
            meals = left
        elif not left:
            start, moved = today + timedelta(days=1), True
            days = 1
    if word is None and meals is None:
        return None
    return SpanSaid(start, days, meals, (word.group(0),) if word else (), moved)


def default_start(now: datetime, meals: list[str]) -> date:
    """Today, or tomorrow once the last meal planned today is over."""
    last = max((MEAL_ENDS.get(meal, 21) for meal in meals), default=21)
    return now.date() + timedelta(days=1) if now.hour >= last else now.date()
