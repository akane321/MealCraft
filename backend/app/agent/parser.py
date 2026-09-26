import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from langchain_openai import ChatOpenAI

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
        del acknowledged_unknowns, history
        text = message.strip()
        lower = text.lower()
        extraction = AgentConstraintExtraction()

        people = self._first_number(
            lower,
            [r"(?:for|serving)\s*(\d+)\s*(?:people|persons?)?", r"(\d+)\s*(?:people|persons?|人|个人)"],
        )
        if people is None:
            # "Dinners for two", "a family of four", "three people".
            words = "|".join(NUMBER_WORDS)
            match = re.search(rf"\b(?:for|serving|family of)\s+({words})\b", lower) or re.search(
                rf"\b({words})\s+(?:people|persons?|adults?)\b", lower
            )
            if match:
                people = NUMBER_WORDS[match.group(1)]
        if people is None and re.search(r"(?:两|二)\s*(?:人|个人)", text):
            people = 2
        extraction.household_size = int(people) if people is not None else None

        per_meal = self._first_number(
            lower,
            [
                r"(?:s\$|\$)?\s*(\d+(?:\.\d+)?)\s*(?:per\s*meal|each\s*meal)",
                r"(?:每餐|一餐)(?:预算|不超过|最多|大约|约)?\s*(?:s\$|\$|新币)?\s*(\d+(?:\.\d+)?)",
                r"(?:预算|budget)[^\d]{0,8}(\d+(?:\.\d+)?)[^\n]{0,12}(?:每餐|per\s*meal)",
            ],
        )
        extraction.budget_per_meal_sgd = per_meal
        weekly = self._first_number(
            lower,
            [
                r"(?:weekly|per\s*week)\s*(?:budget)?[^\d]{0,8}(\d+(?:\.\d+)?)",
                # "this week, around S$90": a dollar amount in a sentence about the week.
                r"\bweek\b[^\d$]{0,24}(?:s\$|\$)\s*(\d+(?:\.\d+)?)(?!\s*(?:per|each|a)\s*meal)",
                r"(?:每周|一周)(?:预算|不超过|最多|大约|约)?\s*(?:s\$|\$|新币)?\s*(\d+(?:\.\d+)?)",
            ],
        )
        extraction.weekly_budget_sgd = weekly
        cooking_time = self._first_number(
            lower,
            [
                r"(\d+)\s*(?:minutes?|mins?|分钟)[^\n]{0,10}(?:cook|cooking|做饭|烹饪)?",
                r"(?:cook|cooking|做饭|烹饪)[^\d]{0,8}(\d+)\s*(?:minutes?|mins?|分钟)",
            ],
        )
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
        for alias, normalized_name in {**self._ingredient_aliases, **self._allergen_aliases}.items():
            english_exclusion = re.search(rf"\b(?:no|without|avoid)\s+{re.escape(alias)}s?\b", lower)
            chinese_exclusion = re.search(rf"(?:不吃|不要|避免|禁用)\s*{re.escape(alias)}", lower)
            if english_exclusion or chinese_exclusion:
                excluded.append(normalized_name)
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
                for alias, normalized_name in self._ingredient_aliases.items():
                    if alias not in lower:
                        continue
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
        extraction.medical_request_detected = any(
            token in lower for token in ("diabetes", "diabetic", "gout", "kidney disease", "糖尿病", "痛风", "肾病")
        )
        extraction.assistant_summary = self._summary(extraction)
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
    def _summary(extraction: AgentConstraintExtraction) -> str:
        details: list[str] = []
        if extraction.household_size:
            details.append(f"{extraction.household_size} people")
        if extraction.budget_per_meal_sgd:
            details.append(f"S${extraction.budget_per_meal_sgd:g} per meal")
        if extraction.health_preferences:
            details.extend(value.replace("-", " ") for value in extraction.health_preferences)
        if extraction.allergens:
            details.append("allergens: " + ", ".join(extraction.allergens))
        if extraction.excluded_ingredients:
            details.append("excluded: " + ", ".join(extraction.excluded_ingredients))
        if extraction.available_ingredients:
            details.append(
                "available: "
                + ", ".join(item.normalized_name.replace("_", " ") for item in extraction.available_ingredients)
            )
        if details:
            return "I captured " + "; ".join(details) + "."
        return "I checked that message against the planning constraints."


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
  and do not list its members yourself. Groups are for excluded_ingredients only:
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

    def __init__(self, *, api_key: str, model: str, vocabulary: ConstraintVocabulary | None = None) -> None:
        self.vocabulary = vocabulary
        self.structured_model = ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=0,
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
the week ("this week, around S$90") is weekly_budget_sgd.
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
        return align_to_vocabulary(result, self.vocabulary) if self.vocabulary else result
