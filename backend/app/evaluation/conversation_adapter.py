"""Synthetic-only phase-one conversation apparatus (ADR-0092).

No episode loader, gold, scorer, provider, network client or initial-state seeding.
Template/schema/message bytes are DRAFTS pending registration and independent review.
The callback is the system under test, not a parser that constructs requests for it.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from app.core import clock
from app.orchestration.contracts import ScopeClass
from app.schemas.agent import AgentSessionResponse
from app.schemas.meal_plan import WeeklyMealPlanResponse

VERSION = "conversation-adapter-draft-v1"
CONFIRMATION_MESSAGE = "I confirm. Please proceed."
CLOCK_SENTENCE = "Today is {day} ({weekday}); timezone: Asia/Singapore."
SHARED_TEMPLATE = (
    "{clock_sentence}\n"
    "Initial state: {{}}\n"
    "Use only this conversation and your own previous responses. "
    "Return JSON conforming to the following shared output schema. "
    "Set awaiting_confirmation only when waiting for confirmation, not when asking for missing information.\n"
    "{schema}"
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeConfig(StrictModel):
    """One global configuration, never supplied or derived per question."""

    anchor_date: date
    timezone: Literal["Asia/Singapore"] = "Asia/Singapore"

    @property
    def instant(self) -> datetime:
        # A fixed noon, not the machine's current time. Draft bytes/time need registration.
        return datetime.combine(self.anchor_date, time(12), clock.SINGAPORE)

    @property
    def clock_sentence(self) -> str:
        return CLOCK_SENTENCE.format(day=self.anchor_date.isoformat(), weekday=WEEKDAYS[self.anchor_date.weekday()])


class PlanDish(StrictModel):
    name: str
    role: str | None = None
    recipe_reference: str | None = None
    servings: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    not_for: list[str] = Field(default_factory=list)
    status: Literal["planned", "completed", "skipped"] | None = None
    locked: bool | None = None
    # Model arms without a catalog can provide their own ingredient/step evidence here.
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class PlanMeal(StrictModel):
    date: date
    meal_type: str
    dishes: list[PlanDish] = Field(min_length=1)


class PlanOutput(StrictModel):
    meals: list[PlanMeal] = Field(min_length=1)
    household_size: int | None = Field(default=None, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    horizon_days: int | None = Field(default=None, ge=1)
    shopping: list[dict[str, JsonValue]] = Field(default_factory=list)
    total_cost_sgd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class UnifiedOutput(StrictModel):
    # Slots coexist: an answer can also contain a plan or ask a question.
    plan: PlanOutput | None = None
    clarification: list[str] = Field(default_factory=list)
    refusal: str | None = None
    answer: str | None = None
    request_fields: dict[str, JsonValue] = Field(default_factory=dict)
    awaiting_confirmation: StrictBool = False


def shared_instructions(config: RuntimeConfig) -> str:
    schema = json.dumps(UnifiedOutput.model_json_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return SHARED_TEMPLATE.format(clock_sentence=config.clock_sentence, schema=schema)


class Exchange(StrictModel):
    message: str
    automatic_confirmation: bool
    output: UnifiedOutput


class ConversationResult(StrictModel):
    system_id: str
    exchanges: list[Exchange]
    confirmation_count: int

    @property
    def final(self) -> UnifiedOutput:
        return self.exchanges[-1].output


# A system receives original message bytes, its own history, and the same instructions.
Responder = Callable[[str, tuple[Exchange, ...], str], UnifiedOutput]


class ConversationHarness:
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.instructions = shared_instructions(config)
        self.confirmation_counts: Counter[str] = Counter()

    def run(self, system_id: str, turns: Sequence[str], respond: Responder) -> ConversationResult:
        if isinstance(turns, (str, bytes)) or not turns or any(not isinstance(t, str) or not t for t in turns):
            raise ValueError("Pass a nonempty sequence of original user strings, not an episode object")
        history: list[Exchange] = []  # never another system's output or a previous case
        count = 0

        def send(message: str, automatic: bool) -> UnifiedOutput:
            own_history = tuple(item.model_copy(deep=True) for item in history)
            output = respond(message, own_history, self.instructions)
            if not isinstance(output, UnifiedOutput):
                raise TypeError("The system must return UnifiedOutput; malformed output is not infeasibility")
            stored = output.model_copy(deep=True)
            history.append(Exchange(message=message, automatic_confirmation=automatic, output=stored))
            return stored

        with clock.frozen(self.config.instant):
            for turn in turns:
                output = send(turn, False)
                if output.awaiting_confirmation and not output.clarification:
                    # Deliberately not a while loop: at most once for this authored turn.
                    count += 1
                    self.confirmation_counts[system_id] += 1
                    send(CONFIRMATION_MESSAGE, True)
        return ConversationResult(system_id=system_id, exchanges=history, confirmation_count=count)


def normalize_product(session: AgentSessionResponse, plan: WeeklyMealPlanResponse | None = None) -> UnifiedOutput:
    """Observe actual product outputs only. No gold, category, ID lookup or inferred constraints.

    request_fields preserves the product's echoed native constraint keys; a later,
    independently reviewed dictionary mapping is NOT implemented here.
    """
    if session.plan_id is not None and (plan is None or plan.id != session.plan_id):
        raise ValueError("Provide this session's actual saved plan; do not silently hide a plan or substitute another")
    if plan is not None and session.plan_id != plan.id:
        raise ValueError("The plan is not this session's output")
    answer = next((m.content for m in reversed(session.messages) if m.role == "assistant"), None)
    questions = list(session.clarification_questions)
    if session.pending_interaction is not None:
        questions.append(session.pending_interaction.prompt)
    decision = session.last_scope_decision
    refusal = (
        answer
        if decision is not None
        and decision.scope_class in {ScopeClass.OUT_OF_SCOPE, ScopeClass.RESTRICTED, ScopeClass.ADVERSARIAL}
        else None
    )
    normalized_plan = None
    if plan is not None and plan.days:
        meals: dict[tuple[date, str], list[PlanDish]] = {}
        for dish in plan.days:
            meals.setdefault((dish.planned_date, dish.meal_type), []).append(
                PlanDish(
                    name=dish.recipe.title,
                    role=dish.role_id,
                    recipe_reference=dish.recipe.slug,
                    servings=dish.servings if dish.servings is not None else plan.household_size * dish.portion_share,
                    not_for=list(dish.not_for),
                    status=dish.status,
                    locked=dish.is_locked,
                    evidence={"nutrition_per_person": dish.nutrition_per_person.model_dump(mode="json")},
                )
            )
        normalized_plan = PlanOutput(
            meals=[PlanMeal(date=day, meal_type=meal, dishes=dishes) for (day, meal), dishes in sorted(meals.items())],
            household_size=plan.household_size,
            start_date=plan.start_date,
            end_date=plan.end_date,
            horizon_days=plan.day_count,
            shopping=[line.model_dump(mode="json") for line in plan.grocery_estimate.items],
            total_cost_sgd=plan.grocery_estimate.purchase_total_sgd,
        )
    return UnifiedOutput(
        plan=normalized_plan,
        clarification=questions,
        refusal=refusal,
        answer=answer,
        request_fields=session.constraints.model_dump(mode="json"),
        # can_confirm alone is saved session state: an unrelated/QA turn can leave
        # it true. It is not a fresh confirmation invitation from that turn. A change
        # preview the session links and has not applied waits the same way (ADR-0098);
        # a preview that is applied, or left over from an earlier turn, does not invite.
        awaiting_confirmation=(
            (
                session.can_confirm
                or (session.pending_replan is not None and session.pending_replan.status == "previewed")
            )
            and decision is not None
            and decision.scope_class == ScopeClass.DOMAIN_ACTION
            and decision.should_mutate_state
        ),
    )
