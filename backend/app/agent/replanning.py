import re
from datetime import date

from app.schemas.agent import AgentReplanDraft
from app.schemas.meal_plan import WeeklyMealPlanResponse


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
    _weekday_aliases = {
        0: ("monday", "mon", "周一", "星期一"),
        1: ("tuesday", "tue", "tues", "周二", "星期二"),
        2: ("wednesday", "wed", "周三", "星期三"),
        3: ("thursday", "thu", "thur", "thurs", "周四", "星期四"),
        4: ("friday", "fri", "周五", "星期五"),
        5: ("saturday", "sat", "周六", "星期六"),
        6: ("sunday", "sun", "周日", "周天", "星期日", "星期天"),
    }

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

        entry_id = self._entry_id(lower, plan)
        if entry_id is not None:
            draft.entry_id = entry_id

        ingredient = self._ingredient(lower, plan)
        if ingredient is not None:
            draft.unavailable_ingredient = ingredient

        draft.reason = text
        question = self._first_question(draft, chinese=bool(re.search(r"[\u4e00-\u9fff]", text)))
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
            for token in ("lock", "keep unchanged", "don't change", "do not change", "锁定", "不要改", "保持不变")
        ):
            return "LOCK_MEAL"
        if any(token in text for token in ("cancel", "skip", "取消", "不吃这顿", "跳过")):
            return "CANCEL_MEAL"
        if any(
            token in text
            for token in ("replace", "swap", "change meal", "different meal", "换掉", "替换", "换餐", "换一顿")
        ):
            return "REPLACE_MEAL"
        return None

    def _entry_id(self, text: str, plan: WeeklyMealPlanResponse) -> int | None:
        numbered = re.search(r"(?:day\s*|第\s*)([1-7一二三四五六七])(?:\s*天)?", text)
        if numbered:
            value = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}.get(
                numbered.group(1), int(numbered.group(1)) if numbered.group(1).isdigit() else 0
            )
            return next((day.entry_id for day in plan.days if day.day_index == value), None)

        iso_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_date:
            return next((day.entry_id for day in plan.days if day.planned_date.isoformat() == iso_date.group(1)), None)

        if any(token in text for token in ("today", "今天")):
            today = date.today()
            return next((day.entry_id for day in plan.days if day.planned_date == today), None)

        for weekday, aliases in self._weekday_aliases.items():
            if any(re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text) for alias in aliases):
                return next((day.entry_id for day in plan.days if day.planned_date.weekday() == weekday), None)
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
    def _first_question(draft: AgentReplanDraft, *, chinese: bool) -> str | None:
        if draft.event_type is None:
            return (
                "你希望替换、取消、锁定某餐，还是处理缺货食材？"
                if chinese
                else "Should I replace, cancel, lock a meal, or handle an unavailable ingredient?"
            )
        if draft.entry_id is None:
            return "你想调整哪一天的餐食？" if chinese else "Which day should I adjust?"
        if draft.event_type == "ITEM_UNAVAILABLE" and draft.unavailable_ingredient is None:
            return "哪一种食材买不到？" if chinese else "Which ingredient is unavailable?"
        return None
