from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.parser import ConstraintParser
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


class AgentConstraintWorkflow:
    def __init__(self, parser: ConstraintParser) -> None:
        self.parser = parser
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
    ) -> AgentWorkflowState:
        return self.graph.invoke(
            {
                "message": message,
                "current_constraints": current.model_dump(mode="json"),
                "acknowledged_unknowns": acknowledged_unknowns,
                "history": history,
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

    @staticmethod
    def _assess_constraints(state: AgentWorkflowState) -> AgentWorkflowState:
        current = AgentConstraintState.model_validate(state["current_constraints"])
        extraction = AgentConstraintExtraction.model_validate(state["extraction"])
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
            questions.append("How many people should this weekly plan serve?")

        for item in merged.available_ingredients:
            if item.quantity is None and item.normalized_name not in acknowledged:
                missing.append(f"available_ingredients.{item.normalized_name}.quantity")
                display_name = item.normalized_name.replace("_", " ")
                questions.append(
                    f"How much {display_name} do you already have? "
                    "Reply “unknown” to use it only as a ranking preference."
                )

        status = "ready" if not missing else "collecting"
        parts = [extraction.assistant_summary or "I updated the planning constraints."]
        if extraction.medical_request_detected:
            parts.append(
                "MealCraft does not provide disease-specific or medical dietary advice. "
                "I can still apply general, explicit constraints such as allergens, lower sodium, "
                "lower sugar or user-supplied nutrition targets."
            )
        if questions:
            parts.append(questions[0])
        else:
            parts.append(
                "I have enough information to generate the seven-day plan. "
                "Review the constraints, then confirm when ready."
            )

        return {
            "merged_constraints": merged.model_dump(mode="json"),
            "merged_acknowledged_unknowns": acknowledged,
            "missing_fields": missing,
            "clarification_questions": questions,
            "status": status,
            "assistant_message": " ".join(parts),
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
