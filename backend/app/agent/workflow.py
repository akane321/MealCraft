from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent import replies
from app.agent.limits import Refusal
from app.agent.parser import ConstraintParser, bare_amount
from app.agent.replies import language, say
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState, AgentMessageResponse
from app.schemas.recommendation import AvailableIngredientInput, NutritionTargets


class AgentWorkflowState(TypedDict, total=False):
    message: str
    current_constraints: dict
    acknowledged_unknowns: list[str]
    history: list[AgentMessageResponse]
    extraction: dict
    merged_constraints: dict
    merged_acknowledged_unknowns: list[str]
    missing_fields: list[str]
    clarification_questions: list[str]
    status: str
    assistant_message: str
    language: str
    refusal: Refusal | None
    asked: str | None


BUDGET_FIELDS = {"weekly_budget_sgd", "budget_per_meal_sgd"}
# Before the assistant says it has everything: a limit no week can meet, or None (agent/limits.py).
FeasibilityCheck = Callable[[AgentConstraintState, str], Refusal | None]


class AgentConstraintWorkflow:
    def __init__(self, parser: ConstraintParser, *, check: FeasibilityCheck | None = None) -> None:
        self.parser = parser
        self.check = check
        graph = StateGraph(AgentWorkflowState)
        graph.add_node("parse_message", self._parse_message)
        graph.add_node("assess_constraints", self._assess_constraints)
        graph.add_edge(START, "parse_message")
        graph.add_edge("parse_message", "assess_constraints")
        graph.add_edge("assess_constraints", END)
        self.graph = graph.compile()

    def run(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: list[AgentMessageResponse],
        asked: str | None = None,
    ) -> AgentWorkflowState:
        """`asked` is the field the assistant's last question was about, if any."""
        return self.graph.invoke(
            {
                "message": message,
                "current_constraints": current.model_dump(mode="json"),
                "acknowledged_unknowns": acknowledged_unknowns,
                "history": history,
                "language": language(message, history),
                "asked": asked,
            }
        )

    def _parse_message(self, state: AgentWorkflowState) -> AgentWorkflowState:
        current = AgentConstraintState.model_validate(state["current_constraints"])
        extraction = self.parser.parse(
            state["message"],
            current=current,
            acknowledged_unknowns=state["acknowledged_unknowns"],
            history=state["history"],
        )
        return {"extraction": extraction.model_dump(mode="json")}

    def _assess_constraints(self, state: AgentWorkflowState) -> AgentWorkflowState:
        lang = state["language"]
        current = AgentConstraintState.model_validate(state["current_constraints"])
        extraction = AgentConstraintExtraction.model_validate(state["extraction"])
        asked = state.get("asked")
        if asked in BUDGET_FIELDS and extraction.weekly_budget_sgd is None and extraction.budget_per_meal_sgd is None:
            # Asked for a budget, "S$50" or 那就50新币吧 answers it, though it says neither meal nor week.
            amount = bare_amount(state["message"])
            if amount is not None:
                setattr(extraction, asked, amount)
                extraction.assistant_summary = say(
                    "got_it", lang, details=replies.details(AgentConstraintExtraction(**{asked: amount}), lang)[0]
                )
        merged = AgentConstraintWorkflow._merge_constraints(current, extraction)
        acknowledged = list(
            dict.fromkeys([*state["acknowledged_unknowns"], *extraction.acknowledged_unknown_quantities])
        )
        known_quantities = {item.normalized_name for item in merged.available_ingredients if item.quantity is not None}
        acknowledged = [item for item in acknowledged if item not in known_quantities]

        missing: list[str] = []
        questions: list[str] = []
        if merged.household_size is None:
            missing.append("household_size")
            questions.append(say("ask_people", lang))

        options = {item.term: item.options for item in extraction.unmatched_suggestions}
        for term in extraction.unmatched_terms:
            missing.append(f"unmatched.{term}")
            question = say("unmatched", lang, term=term)
            if options.get(term):
                names = replies.joined((replies.word(option, lang) for option in options[term]), lang)
                question += say("unmatched_options", lang, names=names)
            else:
                question += say("unmatched_open", lang)
            questions.append(question)

        for item in merged.available_ingredients:
            if item.quantity is None and item.normalized_name not in acknowledged:
                missing.append(f"available_ingredients.{item.normalized_name}.quantity")
                questions.append(say("ask_quantity", lang, name=replies.word(item.normalized_name, lang)))

        # Everything is known: before saying so, a limit no week can meet is refused with its reason.
        refusal = self.check(merged, lang) if self.check is not None and not missing else None
        if refusal is not None:
            missing, questions = [refusal.field], [refusal.text]
        status = "ready" if not missing else "collecting"
        if refusal is not None:
            parts = [refusal.text]
            if extraction.medical_request_detected:
                parts.append(say("medical", lang))
        else:
            parts = [extraction.assistant_summary or say("noted", lang)]
            if extraction.medical_request_detected:
                parts.append(say("medical", lang))
            parts.append(questions[0] if questions else say("ready", lang))

        return {
            "merged_constraints": merged.model_dump(mode="json"),
            "merged_acknowledged_unknowns": acknowledged,
            "missing_fields": missing,
            "clarification_questions": questions,
            "status": status,
            "assistant_message": ("" if lang == "zh" else " ").join(parts),
            "refusal": refusal,
        }

    @staticmethod
    def _merge_constraints(
        current: AgentConstraintState,
        extraction: AgentConstraintExtraction,
    ) -> AgentConstraintState:
        state = current.model_dump(mode="json")
        for field in (
            "household_size",
            "max_cooking_time_minutes",
            "budget_per_meal_sgd",
            "weekly_budget_sgd",
            "max_sodium_mg_per_meal",
            "pricing_mode",
            "max_uses_per_recipe",
        ):
            value = getattr(extraction, field)
            if value is not None:
                state[field] = value

        for field in ("allergens", "excluded_ingredients", "dietary_preferences", "health_preferences"):
            values = getattr(extraction, field)
            if values:
                state[field] = list(dict.fromkeys([*state[field], *values]))

        if extraction.nutrition_targets is not None:
            current_targets = NutritionTargets.model_validate(state["nutrition_targets"]).model_dump()
            for field, value in extraction.nutrition_targets.model_dump().items():
                if value is not None:
                    current_targets[field] = value
            state["nutrition_targets"] = current_targets

        if extraction.available_ingredients:
            by_name = {
                item.normalized_name: item for item in AgentConstraintState.model_validate(state).available_ingredients
            }
            for item in extraction.available_ingredients:
                by_name[item.normalized_name] = AvailableIngredientInput.model_validate(item)
            state["available_ingredients"] = [item.model_dump(mode="json") for item in by_name.values()]

        return AgentConstraintState.model_validate(state)
