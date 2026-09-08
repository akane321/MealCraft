from pydantic import BaseModel, Field

from app.agent.parser import ConstraintParser
from app.agent.workflow import AgentConstraintWorkflow
from app.orchestration.contracts import InteractionRequest, ScopeClass, ScopeDecision
from app.orchestration.interactions import household_size_interaction, pantry_quantity_interaction
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.schemas.agent import AgentConstraintState, AgentMessageResponse


class AgentTurnOutcome(BaseModel):
    constraints: AgentConstraintState
    acknowledged_unknowns: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    status: str
    assistant_message: str
    scope_decision: ScopeDecision
    context_version: int = Field(ge=1)
    pending_interaction: InteractionRequest | None = None
    state_mutated: bool = False


class BoundedAgentOrchestrator:
    """Apply deterministic scope policy before the probabilistic constraint parser."""

    def __init__(self, parser: ConstraintParser, *, scope_policy: ReferenceScopePolicy | None = None) -> None:
        self.workflow = AgentConstraintWorkflow(parser)
        self.scope_policy = scope_policy or ReferenceScopePolicy()

    def process(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: list[AgentMessageResponse],
        current_status: str,
        current_missing_fields: list[str],
        current_questions: list[str],
        context_version: int,
        pending_interaction: InteractionRequest | None = None,
    ) -> AgentTurnOutcome:
        decision = self.scope_policy.classify(message)
        if decision.scope_class is ScopeClass.AMBIGUOUS and current_questions:
            decision = ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["clarification_answer"],
                supported_segments=[message],
                should_mutate_state=True,
                reason_code="PENDING_CLARIFICATION_RESPONSE",
            )

        if not decision.should_mutate_state:
            return AgentTurnOutcome(
                constraints=current,
                acknowledged_unknowns=acknowledged_unknowns,
                missing_fields=current_missing_fields,
                clarification_questions=current_questions,
                status=current_status,
                assistant_message=self.boundary_message(decision),
                scope_decision=decision,
                context_version=max(context_version, 1),
                pending_interaction=pending_interaction,
                state_mutated=False,
            )

        scoped_message = message
        if decision.scope_class is ScopeClass.PARTIALLY_SUPPORTED and decision.supported_segments:
            scoped_message = ". ".join(decision.supported_segments)
        result = self.workflow.run(
            scoped_message,
            current=current,
            acknowledged_unknowns=acknowledged_unknowns,
            history=history,
        )
        next_context_version = max(context_version + 1, 1)
        missing_fields = list(result["missing_fields"])
        questions = list(result["clarification_questions"])
        interaction = self._interaction_for(
            missing_fields,
            question=questions[0] if questions else None,
            context_version=next_context_version,
        )
        assistant_message = str(result["assistant_message"])
        if decision.scope_class is ScopeClass.PARTIALLY_SUPPORTED and decision.unsupported_segments:
            assistant_message = (
                "I handled the meal-planning part only. I cannot help with the unrelated part of that request. "
                + assistant_message
            )
        return AgentTurnOutcome(
            constraints=AgentConstraintState.model_validate(result["merged_constraints"]),
            acknowledged_unknowns=list(result["merged_acknowledged_unknowns"]),
            missing_fields=missing_fields,
            clarification_questions=questions,
            status=str(result["status"]),
            assistant_message=assistant_message,
            scope_decision=decision,
            context_version=next_context_version,
            pending_interaction=interaction,
            state_mutated=True,
        )

    @staticmethod
    def _interaction_for(
        missing_fields: list[str],
        *,
        question: str | None,
        context_version: int,
    ) -> InteractionRequest | None:
        if not missing_fields:
            return None
        field_path = missing_fields[0]
        question_id = f"context-{context_version}:{field_path}"
        if field_path == "household_size":
            return household_size_interaction(question_id=question_id, context_version=context_version)
        prefix = "available_ingredients."
        suffix = ".quantity"
        if field_path.startswith(prefix) and field_path.endswith(suffix):
            ingredient_name = field_path[len(prefix) : -len(suffix)]
            return pantry_quantity_interaction(
                ingredient_name=ingredient_name,
                question_id=question_id,
                context_version=context_version,
            )
        if question is None:
            return None
        return InteractionRequest(
            type="free_text",
            prompt=question,
            field_path=field_path,
            question_id=question_id,
            allow_free_text=True,
            context_version=context_version,
        )

    @staticmethod
    def boundary_message(decision: ScopeDecision) -> str:
        messages = {
            ScopeClass.SOCIAL: ("Hello. I can help plan meals, explain a MealCraft plan, or adjust an existing plan."),
            ScopeClass.OUT_OF_SCOPE: (
                "That request is outside MealCraft's meal-planning scope. I can help with recipes, "
                "dietary constraints, groceries, budgets, or an existing meal plan."
            ),
            ScopeClass.RESTRICTED: (
                "MealCraft does not create disease-treatment diets or medical prescriptions. "
                "I can apply explicit allergens, general preferences, and nutrition targets you provide."
            ),
            ScopeClass.ADVERSARIAL: (
                "I cannot reveal credentials, system instructions, or bypass MealCraft's safety "
                "and authorization rules."
            ),
            ScopeClass.AMBIGUOUS: (
                "I am not sure whether this is a meal-planning request. Tell me what meal, recipe, grocery, "
                "budget, or dietary-planning task you want help with."
            ),
            ScopeClass.DOMAIN_QUESTION: (
                "I can answer questions using the saved MealCraft plan and grounded tool results."
            ),
        }
        return messages.get(
            decision.scope_class,
            "I could not safely process that request. Please restate the supported meal-planning task.",
        )
