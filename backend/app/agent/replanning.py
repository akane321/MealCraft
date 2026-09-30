import re
from datetime import date, timedelta

from app.planning.recipe_similarity import wanted
from app.schemas.agent import AgentReplanDraft
from app.schemas.meal_plan import WeeklyMealPlanResponse

MEAL_WORDS = {
    "breakfast": ("breakfast", "早饭", "早餐"),
    "lunch": ("lunch", "午饭", "午餐", "中饭"),
    "dinner": ("dinner", "supper", "tonight", "晚饭", "晚餐", "今晚"),
}


class AgentReplanInterpreter:
    """Deterministically translate a short user message into one meal-plan event draft."""

    _ingredient_aliases = {
        "chicken breast": "chicken_breast",
        "chicken": "chicken_breast",
        "鸡胸肉": "chicken_breast",
        "鸡肉": "chicken_breast",
        "brown rice": "brown_rice",
        "糙米": "brown_rice",
        "firm tofu": "firm_tofu",
        "tofu": "firm_tofu",
        "豆腐": "firm_tofu",
        "soba noodle": "soba_noodle",
        "soba": "soba_noodle",
        "荞麦面": "soba_noodle",
        "lemon": "lemon",
        "柠檬": "lemon",
        "tomato": "tomato",
        "番茄": "tomato",
        "西红柿": "tomato",
    }
    # Words that name a dish role of a composed meal (ADR-0036).
    _role_aliases = {
        "main": ("main", "主菜", "荤菜"),
        "vegetable": ("vegetable", "veg", "side", "salad", "蔬菜", "配菜", "素菜", "沙拉"),
        "soup": ("soup", "汤"),
    }
    _weekday_aliases = {
        0: ("monday", "mon", "周一", "星期一", "礼拜一"),
        1: ("tuesday", "tue", "tues", "周二", "星期二", "礼拜二"),
        2: ("wednesday", "wed", "周三", "星期三", "礼拜三"),
        3: ("thursday", "thu", "thur", "thurs", "周四", "星期四", "礼拜四"),
        4: ("friday", "fri", "周五", "星期五", "礼拜五"),
        5: ("saturday", "sat", "周六", "星期六", "礼拜六"),
        6: ("sunday", "sun", "周日", "周天", "星期日", "星期天", "礼拜日", "礼拜天"),
    }
    _weekday_of = {alias: weekday for weekday, aliases in _weekday_aliases.items() for alias in aliases}
    _weekday_pattern = re.compile(
        "(?<![a-z])(?:" + "|".join(map(re.escape, sorted(_weekday_of, key=len, reverse=True))) + ")(?![a-z])"
    )
    # Several days in one word; "Monday to Friday" / "周一到周五" reads as a range of named days.
    _several_days = {
        (5, 6): ("weekend", "周末", "双休日"),
        (0, 1, 2, 3, 4): (
            "weekday",
            "week day",
            "weeknight",
            "workday",
            "work day",
            "working day",
            "during the week",
            "工作日",
            "平日",
            "上班日",
            "周中",
        ),
    }
    _range_words = ("to", "through", "thru", "till", "until", "-", "–", "—", "~", "～", "到", "至")
    # "except weekends", "除了周末": the days named are the ones left alone.
    _except = re.compile(r"(?<![a-z])(?:except|other than)(?![a-z])|除了|除去")
    # "..., weekends as usual", "周末照常": a clause naming the days that stay as they are.
    _clause_break = re.compile(r"[,，;；。.!！?？]|(?<![a-z])but(?![a-z])|但是|但|不过")
    _kept = re.compile(
        r"(?<![a-z])(?:as usual|as normal|as before|as is|keep|kept|stays?|unchanged|the same|untouched)(?![a-z])"
        r"|照常|照旧|照样|保留|不变|正常|保持|一样"
    )
    # "周一到五", "星期一至五": the range's end without its "周" / "星期".
    _short_range = re.compile(r"(周|星期|礼拜)([一二三四五六日天])(\s*(?:到|至|-|~|～)\s*)([一二三四五六日天])")

    def parse(
        self,
        message: str,
        *,
        plan: WeeklyMealPlanResponse,
        current: AgentReplanDraft,
    ) -> tuple[AgentReplanDraft, list[str]]:
        text = message.strip()
        lower = text.lower()
        draft = current.model_copy(deep=True)

        event_type = self._event_type(lower)
        if event_type is not None:
            draft.event_type = event_type

        day_index = self.day_index(lower, plan)
        if day_index is not None:
            draft.day_index = day_index
            draft.entry_id = None
        if draft.entry_id is None and draft.day_index is not None:
            draft.entry_id = self._dish_entry(lower, plan, draft.day_index)

        ingredient = self._ingredient(lower, plan)
        if ingredient is not None:
            draft.unavailable_ingredient = ingredient

        draft.reason = text
        question = self._first_question(draft, chinese=bool(re.search(r"[\u4e00-\u9fff]", text)), plan=plan)
        return draft, [question] if question else []

    @staticmethod
    def _event_type(text: str) -> str | None:
        if any(
            token in text
            for token in ("unavailable", "out of stock", "can't buy", "cannot buy", "买不到", "缺货", "没货")
        ):
            return "ITEM_UNAVAILABLE"
        if any(
            token in text
            for token in (
                "lock",
                "keep unchanged",
                "don't change",
                "do not change",
                "锁定",
                "保留",
                "不要改",
                "保持不变",
            )
        ):
            return "LOCK_MEAL"
        if any(token in text for token in ("cancel", "skip", "取消", "不吃这顿", "跳过")):
            return "CANCEL_MEAL"
        if any(
            token in text
            for token in (
                "replace",
                "swap",
                "instead",
                "change meal",
                "different meal",
                "换掉",
                "替换",
                "换餐",
                "换一顿",
                "换成",
                "改成",
            )
        ):
            return "REPLACE_MEAL"
        return None

    def day_index(self, text: str, plan: WeeklyMealPlanResponse) -> int | None:
        numbered = re.search(r"(?:day\s*|第\s*)([1-7一二三四五六七])(?:\s*天)?", text)
        if numbered:
            value = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}.get(
                numbered.group(1), int(numbered.group(1)) if numbered.group(1).isdigit() else 0
            )
            return next((day.day_index for day in plan.days if day.day_index == value), None)

        iso_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_date:
            return next((d.day_index for d in plan.days if d.planned_date.isoformat() == iso_date.group(1)), None)

        for tokens, offset in ((("today", "tonight", "今天", "今晚"), 0), (("tomorrow", "明天"), 1)):
            if any(token in text for token in tokens):
                wanted = date.today() + timedelta(days=offset)
                return next((day.day_index for day in plan.days if day.planned_date == wanted), None)

        named = [self._weekday_of[match.group()] for match in self._weekday_pattern.finditer(text)]
        if named:
            return next((day.day_index for day in plan.days if day.planned_date.weekday() == min(named)), None)
        return None

    def day_indexes(self, text: str, plan: WeeklyMealPlanResponse) -> list[int] | None:
        """Every day the message names, in the week's order; None when it names none (the whole week).

        "on weekends", "weekdays", "during the week", "Monday to Friday", "Wednesday and Friday",
        "except weekends" and the same in Chinese ("工作日", "平日", "周一到五", "除了周末").
        A shape change reads its days here; a one-dish event still takes one day (`day_index`).
        Days named only in a clause that keeps them ("no lunch on weekdays, weekends as usual") are
        not changed.
        """
        text = self._short_range.sub(r"\1\2\3\1\4", text)
        clauses = [(clause, self._named_days(clause)) for clause in self._clause_break.split(text)]
        changed = [days for clause, days in clauses if days and not self._kept.search(clause)]
        weekdays = set().union(*(changed or [days for _, days in clauses]))
        if not weekdays:
            day = self.day_index(text, plan)
            return [day] if day is not None else None
        return sorted({day.day_index for day in plan.days if day.planned_date.weekday() in weekdays}) or None

    def _named_days(self, text: str) -> set[int]:
        """The weekdays (0 = Monday) one clause names; "except weekends" names the other five."""
        weekdays = {
            weekday
            for days, words in self._several_days.items()
            if any(re.search(rf"(?<![a-z]){re.escape(word)}s?(?![a-z])", text) for word in words)
            for weekday in days
        }
        named = list(self._weekday_pattern.finditer(text))
        for first, second in zip(named, named[1:], strict=False):
            if text[first.end() : second.start()].strip() in self._range_words:
                start, end = self._weekday_of[first.group()], self._weekday_of[second.group()]
                weekdays.update((start + n) % 7 for n in range((end - start) % 7 + 1))
        weekdays.update(self._weekday_of[match.group()] for match in named)
        if weekdays and self._except.search(text):
            weekdays = set(range(7)) - weekdays  # "no lunch except on weekends": the other days
        return weekdays

    def _dish_entry(self, text: str, plan: WeeklyMealPlanResponse, day_index: int) -> int | None:
        """The day's one dish, or the dish whose role or title the message names; None while ambiguous."""
        dishes = [day for day in plan.days if day.day_index == day_index]
        # "Tomorrow's lunch": a named meal narrows the day to that meal's dishes (ADR-0046).
        meal = next((m for m, words in MEAL_WORDS.items() if any(word in text for word in words)), None)
        if meal is not None:
            dishes = [dish for dish in dishes if dish.meal_type == meal] or dishes
        if len(dishes) == 1:
            return dishes[0].entry_id
        named = [
            dish
            for dish in dishes
            if any(
                re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text)
                for alias in self._role_aliases.get(dish.role_id, (dish.role_id,))
            )
            or dish.recipe.title.lower() in text
        ]
        if len(named) == 1:
            return named[0].entry_id
        # "Can tomorrow be fish instead?": what someone asks for instead is a main dish, and with
        # several meals in the day, dinner's unless another meal was named.
        if wanted(text):
            mains = [dish for dish in dishes if dish.role_id == "main"]
            main = next((dish for dish in mains if dish.meal_type == (meal or "dinner")), None)
            if main is not None:
                return main.entry_id
        return None

    def _ingredient(self, text: str, plan: WeeklyMealPlanResponse) -> str | None:
        for alias in sorted(self._ingredient_aliases, key=len, reverse=True):
            if alias in text:
                return self._ingredient_aliases[alias]
        for item in plan.grocery_estimate.items:
            candidates = (item.ingredient_name, item.ingredient_display_name.lower())
            if any(candidate.replace("_", " ") in text for candidate in candidates):
                return item.ingredient_name
        return None

    @staticmethod
    def _first_question(
        draft: AgentReplanDraft, *, chinese: bool, plan: WeeklyMealPlanResponse | None = None
    ) -> str | None:
        if draft.event_type is None:
            return (
                "你希望替换、取消、锁定某餐，还是处理缺货食材？"
                if chinese
                else "Should I replace, cancel, lock a meal, or handle an unavailable ingredient?"
            )
        if draft.entry_id is None and draft.day_index is not None and plan is not None:
            titles = [day.recipe.title for day in plan.days if day.day_index == draft.day_index]
            return (
                f"那天有 {len(titles)} 道菜（{'、'.join(titles)}），你想调整哪一道？"
                if chinese
                else f"That day has {len(titles)} dishes ({', '.join(titles)}); which one should I adjust?"
            )
        if draft.entry_id is None:
            return "你想调整哪一天的餐食？" if chinese else "Which day should I adjust?"
        if draft.event_type == "ITEM_UNAVAILABLE" and draft.unavailable_ingredient is None:
            return "哪一种食材买不到？" if chinese else "Which ingredient is unavailable?"
        return None
