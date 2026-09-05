import re

from app.orchestration.contracts import ScopeClass, ScopeDecision


class ReferenceScopePolicy:
    """Deterministic starter policy, not the final multilingual scope classifier."""

    _social_patterns = (
        r"^(?:hi|hello|hey|thanks|thank you)[!. ]*$",
        r"^(?:你好|您好|谢谢|多谢)[！!。,. ]*$",
    )
    _domain_tokens = (
        "meal",
        "dinner",
        "recipe",
        "cook",
        "diet",
        "nutrition",
        "calorie",
        "protein",
        "budget",
        "fairprice",
        "grocery",
        "snack",
        "食谱",
        "菜谱",
        "做饭",
        "饮食",
        "营养",
        "热量",
        "蛋白质",
        "预算",
        "购物清单",
        "食材",
        "零食",
    )
    _off_topic_tokens = (
        "movie",
        "film",
        "cinema",
        "flight",
        "hotel",
        "stock price",
        "write my essay",
        "电影",
        "机票",
        "酒店",
        "股票",
        "写论文",
    )
    _medical_tokens = (
        "diabetes",
        "gout",
        "kidney disease",
        "糖尿病",
        "痛风",
        "肾病",
    )
    _treatment_tokens = (
        "treat",
        "cure",
        "prescribe",
        "治疗",
        "治愈",
        "处方",
    )
    _adversarial_tokens = (
        "ignore previous instructions",
        "reveal system prompt",
        "show api key",
        "database password",
        "忽略之前的指令",
        "输出系统提示词",
        "显示 api key",
        "数据库密码",
    )

    def classify(self, message: str) -> ScopeDecision:
        text = message.strip()
        lower = text.lower()
        if any(token in lower for token in self._adversarial_tokens):
            return ScopeDecision(
                scope_class=ScopeClass.ADVERSARIAL,
                unsupported_segments=[text],
                reason_code="PROMPT_OR_SECRET_BOUNDARY",
            )

        for pattern in self._social_patterns:
            if re.fullmatch(pattern, lower, flags=re.IGNORECASE):
                return ScopeDecision(
                    scope_class=ScopeClass.SOCIAL,
                    supported_segments=[text],
                    reason_code="SOCIAL_ENVELOPE",
                )

        has_domain = any(token in lower for token in self._domain_tokens)
        has_off_topic = any(token in lower for token in self._off_topic_tokens)
        has_medical = any(token in lower for token in self._medical_tokens)
        asks_for_treatment = any(token in lower for token in self._treatment_tokens)

        if has_medical and asks_for_treatment:
            return ScopeDecision(
                scope_class=ScopeClass.RESTRICTED,
                unsupported_segments=[text],
                reason_code="MEDICAL_TARGET_DERIVATION_NOT_ALLOWED",
            )
        if has_domain and has_off_topic:
            return ScopeDecision(
                scope_class=ScopeClass.PARTIALLY_SUPPORTED,
                detected_intents=["create_plan"],
                supported_segments=[text],
                unsupported_segments=["non-meal recommendation segment"],
                should_mutate_state=True,
                should_call_tools=True,
                reason_code="MIXED_SUPPORTED_AND_UNSUPPORTED",
            )
        if has_off_topic:
            return ScopeDecision(
                scope_class=ScopeClass.OUT_OF_SCOPE,
                unsupported_segments=[text],
                reason_code="OUT_OF_DOMAIN",
            )
        if has_domain:
            return ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["create_plan"],
                supported_segments=[text],
                should_mutate_state=True,
                should_call_tools=True,
                reason_code="SUPPORTED_MEAL_PLANNING_REQUEST",
            )
        return ScopeDecision(
            scope_class=ScopeClass.AMBIGUOUS,
            unsupported_segments=[text],
            requires_clarification=True,
            reason_code="DOMAIN_RELATION_UNCLEAR",
        )
