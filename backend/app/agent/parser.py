import re
from collections.abc import Sequence
from typing import Protocol

from langchain_openai import ChatOpenAI

from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState, AgentMessageResponse
from app.schemas.recommendation import AvailableIngredientInput, NutritionTargets


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
        allergens = [value for token, value in self._allergen_aliases.items() if token in lower and allergy_context]
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


class OpenAIConstraintParser:
    provider = "openai"

    def __init__(self, *, api_key: str, model: str) -> None:
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
General preferences such as low sodium or low sugar are allowed. Disease-specific requests must set
medical_request_detected=true and must never be translated into medical treatment constraints.
Available ingredients with no explicit quantity must keep quantity=null and unit=null.

Current state: {current.model_dump_json()}
Already acknowledged unknown quantities: {acknowledged_unknowns}
Recent conversation:\n{recent_history}
Latest user message: {message}
"""
        result = self.structured_model.invoke(prompt)
        if not isinstance(result, AgentConstraintExtraction):
            return AgentConstraintExtraction.model_validate(result)
        return result
