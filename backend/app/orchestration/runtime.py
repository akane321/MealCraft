import re

from pydantic import BaseModel, Field

from app.agent.parser import ConstraintParser
from app.agent.replies import language, say
from app.agent.workflow import AgentConstraintWorkflow, FeasibilityCheck
from app.orchestration.contracts import InteractionRequest, ScopeClass, ScopeDecision
from app.orchestration.interactions import (
    household_size_interaction,
    pantry_quantity_interaction,
    say_interaction,
    unmatched_term_interaction,
)
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


# "Something nice", "a treat", 我想吃点好的: a wish about food that is not yet a planning request.
FOOD_WISH = re.compile(
    r"\b(?:eat|eating|food|hungry|craving|treat|tasty|yummy|delicious|nice|nicer|good)\b|吃|饿|馋|美食|菜"
)


def wish_options(lang: str, *, planned: bool) -> list[tuple[str, str]]:
    """What a household with only a wish can start from: plan a week, or change a dish of the week they have."""
    if planned:
        return [
            (say("swap_tonight", lang), say("swap_tonight", lang)),
            (say("swap_other", lang), say("swap_say", lang)),
        ]
    return [
        (say("plan_week", lang), say("plan_week_say", lang)),
        (say("plan_varied", lang), say("plan_varied_say", lang)),
    ]


class BoundedAgentOrchestrator:
    """Apply deterministic scope policy before the probabilistic constraint parser."""

    def __init__(
        self,
        parser: ConstraintParser,
        *,
        scope_policy: ReferenceScopePolicy | None = None,
        check: FeasibilityCheck | None = None,
    ) -> None:
        self.workflow = AgentConstraintWorkflow(parser, check=check)
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

        lang = language(message, history)
        if not decision.should_mutate_state:
            reply = self.boundary_message(decision, lang)
            if decision.scope_class is ScopeClass.AMBIGUOUS:
                # Not a dead end: say what can be done from here, as choices.
                if FOOD_WISH.search(message.lower()):
                    reply = say("wish", lang)
                pending_interaction = say_interaction(
                    prompt=reply,
                    options=wish_options(lang, planned=False),
                    question_id=f"context-{max(context_version, 1)}:message:{len(history)}",
                    context_version=max(context_version, 1),
                )
            return AgentTurnOutcome(
                constraints=current,
                acknowledged_unknowns=acknowledged_unknowns,
                missing_fields=current_missing_fields,
                clarification_questions=current_questions,
                status=current_status,
                assistant_message=reply,
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
        refusal = result.get("refusal")
        if refusal is not None:
            # A limit no week meets: the ways out of it, as choices.
            interaction = say_interaction(
                prompt=refusal.text,
                options=list(refusal.options),
                question_id=f"context-{next_context_version}:{refusal.field}",
                context_version=next_context_version,
            )
        else:
            interaction = self._interaction_for(
                missing_fields,
                question=questions[0] if questions else None,
                context_version=next_context_version,
                suggestions={
                    item["term"]: item for item in result.get("extraction", {}).get("unmatched_suggestions", [])
                },
                lang=lang,
            )
        assistant_message = str(result["assistant_message"])
        if decision.scope_class is ScopeClass.PARTIALLY_SUPPORTED and decision.unsupported_segments:
            assistant_message = say("partial", lang) + assistant_message
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
        suggestions: dict[str, dict] | None = None,
        lang: str = "en",
    ) -> InteractionRequest | None:
        if not missing_fields:
            return None
        field_path = missing_fields[0]
        question_id = f"context-{context_version}:{field_path}"
        if field_path == "household_size":
            return household_size_interaction(question_id=question_id, context_version=context_version, lang=lang)
        suggestion = (suggestions or {}).get(field_path.removeprefix("unmatched."))
        if field_path.startswith("unmatched.") and question and suggestion and suggestion.get("options"):
            return unmatched_term_interaction(
                term=suggestion["term"],
                meant_for=suggestion["field"],
                options=suggestion["options"],
                prompt=question,
                question_id=question_id,
                context_version=context_version,
                lang=lang,
            )
        prefix = "available_ingredients."
        suffix = ".quantity"
        if field_path.startswith(prefix) and field_path.endswith(suffix):
            ingredient_name = field_path[len(prefix) : -len(suffix)]
            return pantry_quantity_interaction(
                ingredient_name=ingredient_name,
                question_id=question_id,
                context_version=context_version,
                lang=lang,
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
    def boundary_message(decision: ScopeDecision, lang: str = "en") -> str:
        key = decision.scope_class.value
        return say(key if key in BOUNDARY_KEYS else "unsupported", lang)


BOUNDARY_KEYS = {"social", "out_of_scope", "restricted", "adversarial", "ambiguous", "domain_question"}
