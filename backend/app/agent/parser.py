import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from langchain_openai import ChatOpenAI

from app.agent import replies
from app.agent.ingredient_matcher import IngredientMatcher
from app.data import ingredient_hierarchy
from app.data.allergens import checked_allergens
from app.schemas.agent import (
    AgentConstraintExtraction,
    AgentConstraintState,
    AgentMessageResponse,
    UnmatchedTermSuggestion,
)
from app.schemas.recommendation import AvailableIngredientInput, NutritionTargets

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
# "No pork", "we don't eat pork", "exclude mushrooms", "skip the onion".
ENGLISH_EXCLUSION = (
    r"\b(?:no|without|avoid|exclude|excluding|skip|(?:don't|do not|doesn't|does not|can't|cannot|won't|never)"
    r"\s+(?:eat|have|like|want))\s+(?:any\s+|the\s+)?"
)
# "No repeats", "don't repeat any dish", "no dish twice", "don't serve any dish twice", "each dish only once".
ENGLISH_NO_REPEATS = (
    r"\b(?:no|without|avoid|never|don't|do not)\s+(?:any\s+)?repeat(?:s|ed|ing)?\b"
    r"|\b(?:no|not|don't|do not|never)\b[^.,;!?]{0,24}\b(?:dish|meal|recipe)\s+twice\b"
    r"|\b(?:each|every)\s+(?:dish|meal|recipe)\s+(?:only\s+)?once\b"
)
# 不要重复, 菜不要重复, 一周不重样, 别重复, 每道菜只做一次.
CHINESE_NO_REPEATS = r"不(?:要|能|想|准|可以|会)?(?:重复|重样)|别(?:重复|重样)|每[道个种]?菜只(?:做|吃|上|出现)一次"
# A sum of money ("S$10", "$10", "SGD 10", "10 dollars", "10新币", "10块"), the number a budget is ("budget 120",
# 预算70), or a bare number said per meal or per week ("15 per meal", 每餐15, 一周80).
AMOUNT = re.compile(
    r"(?:s\$|sgd|\$)\s*(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s*(?:sgd\b|dollars?\b|bucks\b|新币|新元|块|元)"
    # Not who eats: "budget for 4 is S$40", "budget for the 4 of us".
    r"|(?:budget|预算)[^\d\n.,;，。；]{0,10}?(?<!for )(?<!for the )(\d+(?:\.\d+)?)"
    r"(?!\s*(?:people|persons?|人|个|min|分钟|g\b|kg\b|克|%|of us\b))"
    r"|(\d+(?:\.\d+)?)(?=\s*(?:per|each)\s*(?:meal|dinner)\b)"
    r"|(?:每餐|一餐|每顿|一顿|每周|一周)(?:预算|不超过|最多|大约|约|花)?\s*(\d+(?:\.\d+)?)(?!\s*(?:人|个|分钟|天|次|顿|餐|道))"
)
# What an amount is for, from the words right after it, then right before it. A meal ("S$12 per dinner",
# 每餐不超过15新币) is read first, then the week ("S$10 total", "total of S$10", "S$10 for the week", 一共10新币).
PER_MEAL_AFTER = re.compile(
    r"^[^\d]{0,14}?\b(?:per|each|a|every)\s*(?:meal|dinner|lunch|breakfast)s?\b|^\s*/\s*(?:meal|dinner)\b"
    r"|^[^\d]{0,6}(?:每餐|一餐|每顿|一顿)"
)
PER_MEAL_BEFORE = re.compile(
    r"(?:\b(?:per|each|every)\s+(?:meal|dinner|lunch|breakfast)|每餐|一餐|每顿|一顿)[^\d]{0,10}$"
)
WEEKLY_AFTER = re.compile(
    r"^[^\d]{0,16}?(?:\b(?:total|in total|altogether|overall|all in|week|weekly)\b|/\s*w(?:ee)?k\b"
    r"|\b(?:7|seven)\s+(?:dinners|lunches|breakfasts)\b|一周|每周|这周|本周|整周|总共|一共|合计|总计)"
)
WEEKLY_BEFORE = re.compile(
    r"(?:\b(?:total|altogether|overall|week|weekly)\b|一共|总共|合计|总计|总预算|一周|每周|这周|本周|整周|周预算)[^\d]{0,24}$"
)
# A number after "for" that counts something other than who eats: "for 7 dinners", "for 10 dollars".
NOT_EATERS = (
    r"(?!\s*(?:dollars?|bucks|sgd|新币|新元|块|元|dinners?|meals?|days?|lunch|lunches|breakfasts?"
    r"|minutes?|mins?|hours?|分钟|%))"
)
COUNT = rf"(?:\d+|{'|'.join(NUMBER_WORDS)})"
# Who eats, said between a sum and what it is for ("a week for 4 for S$10", "S$40 for four people for the
# week", "S$40 for the 4 of us for the week", "S$50 for a family of 4 for the week", 10新币给4个人一周): not a
# sum itself.
EATERS = re.compile(
    rf"\bfor\s+{COUNT}(?:\s*(?:people|persons?|of us|adults?))?\b{NOT_EATERS}"
    rf"|\b{COUNT}\s*(?:people|persons?|adults?)\b"
    rf"|\b(?:for\s+)?the\s+{COUNT}\s+of us\b"
    rf"|\b(?:for\s+)?(?:(?:a|my|our|the)\s+)?family\s+of\s+{COUNT}\b"
    r"|[\d一二两三四五六七八九十]+\s*(?:个人|口人|人)"
)
# An amount for each person ("S$3 per person per meal", 每人每餐3块, 人均15): times the people eating.
PER_PERSON_AFTER = re.compile(
    r"^[^\d]{0,6}?\b(?:per|each|a|every)\s+(?:person|head|adult)\b|^\s*/\s*(?:person|head)\b"
    r"|^[^\d]{0,4}(?:每人|每个人|一个人|人均)"
)
PER_PERSON_BEFORE = re.compile(r"(?:\b(?:per|each|every)\s+(?:person|head|adult)|每人|每个人|一个人|人均)[^\d]{0,10}$")
CLAUSE_END = re.compile(r"[,，;；。!！?？]|\.(?:\s|$)")
# 一百块, 五十新币, 八十五元: Chinese numerals before a currency word, read as digits.
CHINESE_SUM = re.compile(r"([零一二两三四五六七八九十百千]+)(?=\s*(?:块|元|新币|新元))")
DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def chinese_number(numeral: str) -> int:
    """一百二十 -> 120, 十五 -> 15, 两千 -> 2000."""
    total = digit = 0
    for character in numeral:
        if character in DIGITS:
            digit = DIGITS[character]
        else:
            total += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[character]
            digit = 0
    return total + digit


def with_digits(text: str) -> str:
    return CHINESE_SUM.sub(lambda match: str(chinese_number(match.group(1))), text)


def budgets(text: str, people: int | None = None) -> tuple[float | None, float | None]:
    """(per-meal, weekly) budgets a lower-cased message states; an amount that says neither is left out.

    An amount for each person is one for the household of `people`; with no household size it is left out.
    """
    text = with_digits(text)
    per_meal = weekly = None
    for match in AMOUNT.finditer(text):
        group = next(index for index, value in enumerate(match.groups(), start=1) if value)
        value = float(match.group(group))
        # The rest of the clause, and everything up to the number itself so the words of the match count too
        # ("每餐预算15", "weekly budget 120"). Each pattern bounds how far its words may be from the sum, measured
        # once who eats is taken out: "S$10 per person for 4 people for the week" is a sum for the week.
        after = CLAUSE_END.split(text[match.end() :], maxsplit=1)[0]
        before = text[: match.start(group)]
        if value <= 0:
            continue
        if PER_PERSON_AFTER.search(after) or PER_PERSON_BEFORE.search(before):
            if people is None:
                continue
            value *= people
            # "per person" said, what is left says meal or week: "S$3 per person per meal".
            after = PER_PERSON_AFTER.sub("", after, count=1)
        # Who eats, on either side, says neither meal nor week: "S$40 for 4 people for the week".
        after, before = EATERS.sub(" ", after), EATERS.sub(" ", before)
        if PER_MEAL_AFTER.search(after) or PER_MEAL_BEFORE.search(before):
            per_meal = per_meal if per_meal is not None else value
        elif WEEKLY_AFTER.search(after) or WEEKLY_BEFORE.search(before):
            weekly = weekly if weekly is not None else value
    return per_meal, weekly


def says_no_repeats(text: str) -> bool:
    """A lower-cased message that asks for no dish twice ("no repeats", 不重样, 菜不要重复)."""
    return re.search(ENGLISH_NO_REPEATS, text) is not None or re.search(CHINESE_NO_REPEATS, text) is not None


def mentions_money(text: str) -> bool:
    """A sum of money, or a number said as a budget: "S$10", "10 dollars", 总共10块, 一百块, 预算70."""
    return AMOUNT.search(with_digits(text.lower())) is not None


def bare_amount(message: str) -> float | None:
    """The sum a message gives, said per meal, per week or neither ("S$50", "ok, 50 dollars then", 那就50新币吧,
    or just "50"): the answer to a question about a budget."""
    text = with_digits(message.strip().lower())
    match = AMOUNT.search(text) or re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", text)
    if match is None:
        return None
    value = float(next(value for value in match.groups() if value))
    return value if value > 0 else None


class AgentConfigurationError(RuntimeError):
    pass


class ConstraintParser(Protocol):
    provider: str

    def parse(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: Sequence[AgentMessageResponse],
    ) -> AgentConstraintExtraction: ...


class RuleBasedConstraintParser:
    provider = "fixture"

    @staticmethod
    def _mentions(text: str, token: str) -> bool:
        # Whole words for Latin tokens, so "shellfish" does not also mean "fish".
        if token.isascii():
            return re.search(rf"\b{re.escape(token)}s?\b", text) is not None
        return token in text

    _ingredient_aliases = {
        "chicken breast": "chicken_breast",
        "鸡胸肉": "chicken_breast",
        "brown rice": "brown_rice",
        "糙米": "brown_rice",
        "firm tofu": "firm_tofu",
        "tofu": "firm_tofu",
        "豆腐": "firm_tofu",
        "lemon": "lemon",
        "柠檬": "lemon",
        "tomato": "tomato",
        "番茄": "tomato",
        "西红柿": "tomato",
        # The exclusions households state most; the hierarchy widens each (pork -> bacon).
        "pork": "pork",
        "猪肉": "pork",
        "beef": "beef",
        "牛肉": "beef",
        "lamb": "lamb",
        "mutton": "lamb",
        "羊肉": "lamb",
        "chicken": "chicken",
        "鸡肉": "chicken",
        "mushroom": "mushroom",
        "蘑菇": "mushroom",
        "onion": "onion",
        "洋葱": "onion",
        "garlic": "garlic",
        "大蒜": "garlic",
        "cilantro": "cilantro",
        "coriander": "cilantro",
        "香菜": "cilantro",
        # Cooking wine is one ingredient, not the whole alcohol family.
        "cooking wine": "wine_cooking",
        "shaoxing wine": "wine_cooking",
        "料酒": "wine_cooking",
        "alcohol": "group:alcohol",
    }
    _allergen_aliases = {
        "peanut": "peanut",
        "花生": "peanut",
        "soy": "soy",
        "大豆": "soy",
        "gluten": "gluten",
        "麸质": "gluten",
        "sesame": "sesame",
        "芝麻": "sesame",
        "dairy": "dairy",
        "乳制品": "dairy",
        "milk": "dairy",
        "牛奶": "dairy",
        "egg": "egg",
        "鸡蛋": "egg",
        "fish": "fish",
        "鱼": "fish",
        "shellfish": "shellfish",
        "shrimp": "shellfish",
        "贝类": "shellfish",
        "虾": "shellfish",
        "tree nut": "tree_nut",
        "坚果": "tree_nut",
        "wheat": "gluten",
        "小麦": "gluten",
    }

    def parse(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: Sequence[AgentMessageResponse],
    ) -> AgentConstraintExtraction:
        del acknowledged_unknowns
        text = message.strip()
        lower = text.lower().replace("’", "'")
        extraction = AgentConstraintExtraction()

        # Who eats. "One of us" or "two of us" is part of the household, not its size: only "the 4 of us" is
        # all of it, and "the one of us who cooks" is one of them.
        people = self._first_number(
            lower,
            [
                r"(\d+)\s*(?:people|persons?|人|个人)",
                r"\bthe\s+(?!1\b)(\d+)\s+of us\b",
                rf"(?:for|serving|family of)\s*(\d+)(?![\d.]){NOT_EATERS}\s*(?:people|persons?)?",
            ],
        )
        if people is None:
            # "Dinners for two", "a family of four", "three people", "the four of us"; not "for seven dinners".
            words = "|".join(NUMBER_WORDS)
            match = (
                re.search(rf"\b(?:for|serving|family of)\s+({words})\b{NOT_EATERS}", lower)
                or re.search(rf"\b({words})\s+(?:people|persons?|adults?)\b", lower)
                or re.search(rf"\bthe\s+(?!one\b)({words})\s+of us\b", lower)
            )
            if match:
                people = NUMBER_WORDS[match.group(1)]
        if people is None:
            # 两个人, 三口人, 四人.
            match = re.search(r"([一二两三四五六七八九十])\s*(?:个人|口人|人)", text)
            if match:
                people = CHINESE_NUMBERS[match.group(1)]
        extraction.household_size = int(people) if people is not None else None

        eaters = extraction.household_size or current.household_size
        extraction.budget_per_meal_sgd, extraction.weekly_budget_sgd = budgets(lower, eaters)
        cooking_time = self._first_number(
            lower,
            [
                r"(\d+)\s*(?:minutes?|mins?|分钟)[^\n]{0,10}(?:cook|cooking|做饭|烹饪)?",
                r"(?:cook|cooking|做饭|烹饪)[^\d]{0,8}(\d+)\s*(?:minutes?|mins?|分钟)",
            ],
        )
        if cooking_time is None:
            # "Under half an hour", "an hour", 半小时, 一小时.
            for pattern, minutes in (
                (r"half\s+an?\s+hour|半(?:个)?小时", 30),
                (r"\b(?:an|one)\s+hour\b|一(?:个)?小时", 60),
            ):
                if re.search(pattern, lower):
                    cooking_time = minutes
                    break
        extraction.max_cooking_time_minutes = int(cooking_time) if cooking_time is not None else None

        if any(token in lower for token in ("low sodium", "lower sodium", "低盐", "少盐")):
            extraction.health_preferences = ["low-sodium"]
        if any(token in lower for token in ("low sugar", "lower sugar", "低糖", "少糖")):
            extraction.health_preferences = [*(extraction.health_preferences or []), "low-sugar"]
        if any(token in lower for token in ("lower calorie", "low calorie", "低热量", "低卡")):
            extraction.health_preferences = [*(extraction.health_preferences or []), "lower-calorie"]

        dietary: list[str] = []
        for token, value in (
            ("vegetarian", "vegetarian"),
            ("素食", "vegetarian"),
            ("vegan", "vegan"),
            ("纯素", "vegan"),
            ("gluten-free", "gluten-free"),
            ("无麸质", "gluten-free"),
            ("dairy-free", "dairy-free"),
            ("无乳", "dairy-free"),
        ):
            if token in lower and value not in dietary:
                dietary.append(value)
        extraction.dietary_preferences = dietary or None

        allergy_context = any(token in lower for token in ("allerg", "过敏"))
        allergens = [
            value for token, value in self._allergen_aliases.items() if allergy_context and self._mentions(lower, token)
        ]
        extraction.allergens = sorted(set(allergens)) or None
        excluded: list[str] = []
        named: list[tuple[int, int]] = []
        aliases = {**self._ingredient_aliases, **self._allergen_aliases}
        # Longest first, so "no chicken breast" does not also exclude every chicken.
        for alias in sorted(aliases, key=len, reverse=True):
            english = re.search(rf"{ENGLISH_EXCLUSION}({re.escape(alias)})s?\b", lower)
            chinese = re.search(rf"(?:不吃|不要|避免|禁用|不放|不加)\s*({re.escape(alias)})", lower)
            for match in (english, chinese):
                if match and not any(start <= match.start(1) < end for start, end in named):
                    named.append(match.span(1))
                    excluded.append(aliases[alias])
        extraction.excluded_ingredients = sorted(set(excluded)) or None

        targets = NutritionTargets(
            calories_kcal=self._target(lower, ("kcal", "calories", "calorie", "千卡", "卡路里")),
            protein_g=self._target(lower, ("protein", "蛋白质")),
            carbohydrate_g=self._target(lower, ("carbs", "carbohydrate", "碳水")),
            fat_g=self._target(lower, ("fat", "脂肪")),
        )
        if any(value is not None for value in targets.model_dump().values()):
            extraction.nutrition_targets = targets
        sodium = self._target(lower, ("sodium", "钠"))
        if sodium is not None:
            extraction.max_sodium_mg_per_meal = sodium

        pending = [item for item in current.available_ingredients if item.quantity is None]
        unknown_reply = bool(re.fullmatch(r"\s*(?:unknown|not sure|不知道|不清楚|不确定)[.!。！]?\s*", lower))
        quantity_reply = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(g|kg|ml|l|克|千克|毫升|升)\s*", lower)
        if unknown_reply and pending:
            extraction.acknowledged_unknown_quantities = [pending[0].normalized_name]
        elif quantity_reply and pending:
            extraction.available_ingredients = [
                AvailableIngredientInput(
                    normalized_name=pending[0].normalized_name,
                    quantity=float(quantity_reply.group(1)),
                    unit=self._normalize_unit(quantity_reply.group(2)),
                )
            ]
        else:
            pantry_context = any(
                token in lower
                for token in ("i have", "already have", "on hand", "pantry", "已有", "现有", "家里有", "我有")
            )
            if pantry_context:
                ingredients: list[AvailableIngredientInput] = []
                held: list[tuple[int, int]] = []
                refused = set(extraction.excluded_ingredients or ())
                # Longest first: "chicken breast" at home is not also "chicken".
                for alias in sorted(self._ingredient_aliases, key=len, reverse=True):
                    normalized_name = self._ingredient_aliases[alias]
                    if alias not in lower or normalized_name.startswith("group:") or normalized_name in refused:
                        continue
                    at = lower.index(alias)
                    if any(start <= at < end for start, end in held):
                        continue
                    held.append((at, at + len(alias)))
                    nearby = lower[max(0, lower.index(alias) - 16) : lower.index(alias) + len(alias) + 16]
                    quantity_match = re.search(r"(\d+(?:\.\d+)?)\s*(g|kg|ml|l|克|千克|毫升|升)", nearby)
                    ingredients.append(
                        AvailableIngredientInput(
                            normalized_name=normalized_name,
                            quantity=float(quantity_match.group(1)) if quantity_match else None,
                            unit=self._normalize_unit(quantity_match.group(2)) if quantity_match else None,
                        )
                    )
                extraction.available_ingredients = ingredients or None

        extraction.pricing_mode = (
            "live" if any(token in lower for token in ("live price", "实时价格", "fairprice")) else None
        )
        if says_no_repeats(lower):
            extraction.max_uses_per_recipe = 1
        extraction.medical_request_detected = any(
            token in lower for token in ("diabetes", "diabetic", "gout", "kidney disease", "糖尿病", "痛风", "肾病")
        )
        extraction.assistant_summary = self._summary(extraction, replies.language(message, history))
        return extraction

    @staticmethod
    def _first_number(text: str, patterns: list[str]) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    @staticmethod
    def _target(text: str, labels: tuple[str, ...]) -> float | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        before = re.search(rf"(\d+(?:\.\d+)?)\s*(?:mg|g|kcal)?\s*(?:{label_pattern})", text)
        after = re.search(rf"(?:{label_pattern})[^\d]{{0,8}}(\d+(?:\.\d+)?)", text)
        match = before or after
        return float(match.group(1)) if match else None

    @staticmethod
    def _normalize_unit(unit: str) -> str:
        return {"克": "g", "千克": "kg", "毫升": "ml", "升": "l"}.get(unit, unit)

    @staticmethod
    def _summary(extraction: AgentConstraintExtraction, lang: str = "en") -> str:
        details = replies.details(extraction, lang)
        if details:
            return replies.say("got_it", lang, details=("，" if lang == "zh" else ", ").join(details))
        return replies.say("noted", lang)


@dataclass(frozen=True)
class ConstraintVocabulary:
    """The words the planner can check a constraint against.

    The planner matches an exclusion to a recipe's ingredient ids exactly, so an
    exclusion written in any other word -- `cooking wine` for `wine_cooking` --
    silently excludes nothing. Protocol v2-multidish found the model doing exactly
    that until it was shown these words (held-out findings, run 4).
    """

    ingredients: frozenset[str]
    allergens: frozenset[str] = frozenset(checked_allergens())
    # Families no ingredient id stands for, group id -> what it covers (ingredient hierarchy, ADR-0039).
    groups: Mapping[str, str] = field(default_factory=dict)
    # Proposes catalog ids for a word outside the vocabulary; the household picks one or none.
    matcher: IngredientMatcher | None = field(default=None, compare=False)

    def prompt(self) -> str:
        text = f"""Allowed words. A constraint written in any other word matches nothing and is lost.
- excluded_ingredients and available_ingredients: only these ingredient ids, and every id that is
  the thing the user named (told "no wine", exclude each wine id):
{", ".join(sorted(self.ingredients))}
- allergens: only {", ".join(sorted(self.allergens))}"""
        if not self.groups:
            return text
        members = "\n".join(f"  {group_id}: {description}" for group_id, description in sorted(self.groups.items()))
        return f"""{text}
- excluded_ingredients may also name a whole family by its group id, which removes every member
  at once. Use the group id when the user names the family (told "no alcohol", write group:alcohol),
  and do not list its members yourself. A single member the user names is that id, not its family:
  "no cooking wine" or 不要料酒 is wine_cooking, not group:alcohol. Groups are for excluded_ingredients only:
{members}"""


def catalog_groups() -> dict[str, str]:
    """The ingredient hierarchy's groups as the agent's vocabulary wants them: id -> description."""
    return {group_id: group["description"] for group_id, group in ingredient_hierarchy.runtime().groups.items()}


def align_to_vocabulary(
    extraction: AgentConstraintExtraction, vocabulary: ConstraintVocabulary
) -> AgentConstraintExtraction:
    """Keep only words the planner can check, and set the rest aside to be asked about.

    Dropping an unmatched exclusion would tell the user it is excluded while it is
    not; keeping it would do the same, because nothing matches it. So it is neither.
    """
    unmatched: dict[str, str] = {}  # term -> the field it was written into

    def known(values: list[str] | None, words: frozenset[str], field_name: str) -> list[str] | None:
        if values is None:
            return None
        for value in values:
            if value not in words:
                unmatched.setdefault(value, field_name)
        return [value for value in values if value in words] or None

    aligned = extraction.model_copy(deep=True)
    aligned.excluded_ingredients = known(
        extraction.excluded_ingredients, vocabulary.ingredients | frozenset(vocabulary.groups), "excluded_ingredients"
    )
    aligned.allergens = known(extraction.allergens, vocabulary.allergens, "allergens")
    if extraction.available_ingredients is not None:
        pantry = [item for item in extraction.available_ingredients if item.normalized_name in vocabulary.ingredients]
        for item in extraction.available_ingredients:
            if item.normalized_name not in vocabulary.ingredients:
                unmatched.setdefault(item.normalized_name, "available_ingredients")
        aligned.available_ingredients = pantry or None
    aligned.unmatched_terms = list(unmatched)
    aligned.unmatched_suggestions = [
        UnmatchedTermSuggestion(
            term=term,
            field=field_name,
            # Allergens are a closed list of nine the household reads in full; ingredients get proposals.
            options=vocabulary.matcher.suggest(term.replace("_", " "))
            if vocabulary.matcher and field_name != "allergens"
            else [],
        )
        for term, field_name in unmatched.items()
    ]
    return aligned


class OpenAIConstraintParser:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        vocabulary: ConstraintVocabulary | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.vocabulary = vocabulary
        self.model = model
        self.structured_model = ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=0,
            timeout=timeout_seconds,
            max_retries=1,
        ).with_structured_output(AgentConstraintExtraction, method="json_schema")

    def parse(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: Sequence[AgentMessageResponse],
    ) -> AgentConstraintExtraction:
        recent_history = "\n".join(f"{item.role}: {item.content}" for item in history[-8:])
        prompt = f"""You extract constraints for a non-medical weekly meal planner.
Return only facts explicitly stated by the user. Use null for missing scalar fields.
household_size is how many people eat: "dinners for two" or "for 2" means 2. A dollar amount for
the week ("this week, around S$90", "S$10 total") is weekly_budget_sgd. An amount for each person
("S$3 per person per meal", 每人每餐3块) is for the whole household: multiply it by household_size from
the message or the current state, and leave it null when the household size is unknown. A bare amount
("S$50", 50新币) answering the assistant's question about a budget is that budget.
General preferences such as low sodium or low sugar are allowed. Disease-specific requests must set
medical_request_detected=true and must never be translated into medical treatment constraints.
Available ingredients with no explicit quantity must keep quantity=null and unit=null.
An allergy is an allergen and nothing more: a dairy allergy is `dairy`, not also a list of dairy
ingredients. Do not add ingredients, preferences or limits the user did not state. A religion or a
cuisine is not a dietary preference: write what it forbids as excluded ingredients. Wanting to use
something up is the opposite of excluding it. Leave unmatched_terms empty.
Return a field only when the latest message states it: never copy a value back from the current
state below, not even a default.
{self.vocabulary.prompt() if self.vocabulary else ""}

Current state: {current.model_dump_json()}
Already acknowledged unknown quantities: {acknowledged_unknowns}
Recent conversation:\n{recent_history}
Latest user message: {message}
"""
        result = self.structured_model.invoke(prompt)
        if not isinstance(result, AgentConstraintExtraction):
            result = AgentConstraintExtraction.model_validate(result)
        aligned = align_to_vocabulary(result, self.vocabulary) if self.vocabulary else result
        # The reply is a template over what was understood, never the model's own sentence.
        aligned.assistant_summary = RuleBasedConstraintParser._summary(aligned, replies.language(message, history))
        return aligned


class FallbackConstraintParser:
    """The live parser, with the rule parser behind it: a model that is slow, down or out of quota costs the
    household some understanding, never the turn. The reply says when the rules answered."""

    OFFLINE_NOTE = replies.REPLIES["offline"][0]

    def __init__(self, primary: "OpenAIConstraintParser", fallback: RuleBasedConstraintParser | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or RuleBasedConstraintParser()
        self.provider = primary.provider
        self.model = primary.model
        self.vocabulary = primary.vocabulary
        self.fell_back = False

    def parse(self, message, *, current, acknowledged_unknowns, history) -> AgentConstraintExtraction:
        try:
            self.fell_back = False
            return self.primary.parse(
                message, current=current, acknowledged_unknowns=acknowledged_unknowns, history=history
            )
        except Exception:  # noqa: BLE001 - any model failure falls back; the rules never call out
            self.fell_back = True
            result = self.fallback.parse(
                message, current=current, acknowledged_unknowns=acknowledged_unknowns, history=history
            )
            lang = replies.language(message, history)
            result.assistant_summary = (result.assistant_summary or replies.say("noted", lang)) + replies.say(
                "offline", lang
            )
            return result
