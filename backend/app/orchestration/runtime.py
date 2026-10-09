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
    short_prompt,
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


# "Something nice", "a treat", 我想吃点好的: a wish about food that is not yet a planning request. Not a
# greeting ("good morning") and not a question about a dish (这个菜怎么做).
FOOD_WISH = re.compile(
    r"\b(?:hungry|craving|treat|tasty|tastier|yummy|delicious|nicer)\b"
    r"|\bsomething\s+(?:nice|good|special|different)\b|\b(?:eat|eating)\s+(?:well|better|something)\b"
    r"|\b(?:good|nice|better)\s+(?:food|meals?|dinners?|dishes)\b"
    r"|想吃|吃点|吃好|好吃的|饿|馋|美食"
)
# "The dishes are boring", "too repetitive", 菜很单调, 天天都一样: a wish for variety. Not "no repeats" or
# 菜不重样, which state the rule itself.
MONOTONY = re.compile(
    r"\b(?:boring|bored|monotonous|repetitive|samey|same\s+(?:old|thing|dishes|food|every\s*day))\b"
    r"|\b(?:more|no|not\s+(?:much|enough))\s+variety\b|\btoo\s+(?:much\s+)?(?:repetition|repeated)\b"
    r"|单调|没新意|没有新意|吃腻|腻了|老一样|老是一样|总是一样|天天都?一样|都差不多|太重复|重复太多|没什么变化|换换口味|多点花样"
)
# An explicit request for another whole week. This is different from merely saying
# the current week is boring or repetitive: it goes through the full weekly planner.
NEW_WEEK = re.compile(
    r"\b(?:re-?plan(?:\s+the\s+week)?|plan\s+(?:a\s+new|another|the)\s+week(?:\s+again)?)\b"
    r".*\b(?:different\s+dishes|no\s+(?:dish\s+twice|repeats?)|more\s+variety)\b"
    r"|(?:\u91cd\u6392|\u91cd\u65b0(?:\u89c4\u5212|\u5b89\u6392)).*(?:\u4e00\u5468|\u6574\u5468).*(?:\u4e0d\u540c|\u6362\u4e00\u6279|\u4e0d\u91cd\u6837|\u4e0d\u8981?\u91cd\u590d|\u591a\u70b9\u82b1\u6837)"
)

# A complaint about monotony, or an explicit request to swap repeated dishes,
# changes only repeated dishes in the current week.
VARIED_WEEK = re.compile(
    r"\bswap\s+the\s+repeated\s+dishes\b|\u628a\u91cd\u590d\u7684\u83dc\u6362"
    rf"|{MONOTONY.pattern}"
)


def wants_variety(message: str) -> bool:
    return MONOTONY.search(message.lower()) is not None


def wish_options(lang: str, *, planned: bool) -> list[tuple[str, str]]:
    """What a household with only a wish can start from: plan a week, or change a dish of the week they have."""
    if planned:
        return [
            (say("swap_tonight", "en"), say("swap_tonight", lang)),
            (say("swap_other", "en"), say("swap_say", lang)),
        ]
    return [
        (say("plan_week", "en"), say("plan_week_say", lang)),
        (say("plan_varied", "en"), say("plan_varied_say", lang)),
    ]


def variety_options(lang: str) -> list[tuple[str, str]]:
    """Before a week exists, more variety is a week with no dish twice."""
    return [
        (say("plan_varied", "en"), say("plan_varied_say", lang)),
        (say("plan_week", "en"), say("plan_week_say", lang)),
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
        variety = wants_variety(message)
        stated = re.search(r"\d", message) is not None  # "4 of us, the meals are boring": details to read
        if variety and decision.scope_class is ScopeClass.DOMAIN_ACTION and not current_questions and not stated:
            # "These dishes are always the same": a wish, not yet a request, whatever words it uses.
            decision = ScopeDecision(
                scope_class=ScopeClass.AMBIGUOUS,
                unsupported_segments=[message],
                requires_clarification=True,
                reason_code="VARIETY_REQUEST",
            )
        if not decision.should_mutate_state:
            reply = self.boundary_message(decision, lang)
            if decision.scope_class is ScopeClass.AMBIGUOUS:
                # Not a dead end: say what can be done from here, as choices.
                options = wish_options(lang, planned=False)
                if variety:
                    reply, options = say("variety", lang), variety_options(lang)
                elif FOOD_WISH.search(message.lower()):
                    reply = say("wish", lang)
                pending_interaction = say_interaction(
                    options=options,
                    question_id=f"context-{max(context_version, 1)}:message:{len(history)}",
                    context_version=max(context_version, 1),
                    lang=lang,
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
            asked=current_missing_fields[0] if current_missing_fields else None,
        )
        next_context_version = max(context_version + 1, 1)
        missing_fields = list(result["missing_fields"])
        questions = list(result["clarification_questions"])
        refusal = result.get("refusal")
        if refusal is not None:
            # A limit no week meets: the ways out of it, as choices.
            interaction = say_interaction(
                options=list(refusal.options),
                question_id=f"context-{next_context_version}:{refusal.field}",
                context_version=next_context_version,
                lang=lang,
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
            prompt=short_prompt((), lang),
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
