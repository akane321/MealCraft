import re
from collections.abc import Callable
from datetime import date, timedelta
from uuid import uuid4

from pydantic_core import to_jsonable_python

from app.agent import limits, model_client
from app.agent.parser import ConstraintParser
from app.agent.replanning import AgentReplanInterpreter
from app.agent.replies import language, listed, planner_message, say, weekday, word
from app.agent.shape_change import read_shape_change
from app.models.agent import AgentRun, AgentSession
from app.orchestration.contracts import (
    AgentRunStatus,
    InteractionAnswer,
    InteractionOption,
    InteractionRequest,
    InteractionType,
    ScopeClass,
    ScopeDecision,
    ToolEffect,
    ToolRunStatus,
)
from app.orchestration.interactions import (
    SAY_FIELD,
    InteractionAnswerError,
    say_interaction,
    short_prompt,
    typed_choice,
    validate_interaction_answer,
)
from app.orchestration.run_lifecycle import (
    AgentRunLifecycle,
    AgentRunLifecycleError,
    AgentRunNotFoundError,
    StartedRun,
)
from app.orchestration.runtime import (
    FOOD_WISH,
    VARIED_WEEK,
    AgentTurnOutcome,
    BoundedAgentOrchestrator,
    wants_variety,
    wish_options,
)
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.products.provider import ProductProviderError
from app.repositories.agent import AgentSessionRepository
from app.repositories.agent_runs import AgentRunRepository
from app.retrieval.evidence import grocery_packet, packet_digest, verify_grocery_totals
from app.schemas.agent import (
    AgentConfirmationResponse,
    AgentConstraintState,
    AgentMessageResponse,
    AgentReplanConfirmationResponse,
    AgentReplanDraft,
    AgentRunCollectionResponse,
    AgentRunResponse,
    AgentSessionCollectionResponse,
    AgentSessionResponse,
)
from app.schemas.meal_plan import (
    MealPlanReplanEventResponse,
    MealPlanReplanPreviewRequest,
    MealPlanShape,
    WeeklyMealPlanRequest,
    WeeklyMealPlanResponse,
    default_plan_shape,
)
from app.services.meal_plan import WeeklyMealPlanService
from app.services.replanning import (
    MealPlanReplanningService,
    MealPlanReplanValidationError,
)

KEEP_SHAPE_FIELD = "plan_shape.keep"
# Whole replies to "Should new weeks plan meals this way too?" (a tap sends "Keep it as our usual" or "Just this
# week"). Anything else is a new instruction, not an answer: "no lunch on weekdays" starts with "no", "noodles"
# with "no", and "keep Monday's dinner as it is" with "keep".
KEEP_YES = {
    *("yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "please do", "do it", "yes please"),
    *("sounds good", "sounds great", "good", "great", "perfect", "fine", "alright", "all right", "that's fine"),
    *("keep", "keep it", "keep them", "keep it as our usual", "keep it as usual", "make it our usual"),
    *("save", "save it", "yes keep it", "yes save it", "always", "every week", "from now on", "yes every week"),
    *("好", "是", "对", "要", "可以", "行", "保存", "保存为常用安排", "保存为我们的常用安排", "常用"),
    *("以后也这样", "以后都这样", "以后每周也这样", "每周都这样", "每周也这样"),
}
KEEP_NO = {
    *("no", "n", "nope", "nah", "not now", "just this week", "only this week", "this week only"),
    *("just this once", "only this once", "no just this week", "no only this week"),
    *("不", "不要", "不用", "不必", "否", "只这周", "只这一周", "只改这周", "只改这一周", "就这周", "就这一周"),
    *("这周就行", "这周就好", "只是这周", "下不为例"),
}
# Turns the scope gate answers as they were meant (a greeting, a question about the plan): complete, not degraded.
ANSWERED_SCOPES = {ScopeClass.SOCIAL, ScopeClass.DOMAIN_QUESTION}


# A bare yes or no that only leads into the answer ("ok keep it", "no thanks, just this week").
KEEP_LEAD = re.compile(r"^(?:yes|yeah|yep|sure|ok|okay|alright|no|nope|nah)(?:\s+(?:thanks|thank you|please))?\s+")
KEEP_BARE = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "no", "n", "nope", "nah", "好", "是", "对", "不"}


def keep_shape_answer(message: str) -> bool | None:
    """True to keep a changed shape as the household's usual one, False for this week only, None when the
    message is not an answer to that question: every part of it ("Yes, keep it as our usual", "no thanks, just
    this week") must be a whole answer, never a word inside a longer instruction ("no lunch on weekdays")."""
    parts = []
    for part in re.split(r"[,.!?;:~，。！？；：、～]+", message.lower()):
        text = re.sub(r"(?:\s+(?:please|thanks|thank you)|[吧啊呀哦的了])+$", "", " ".join(part.split())).strip()
        led = KEEP_LEAD.sub("", text)
        if text:
            parts.append(led if led in KEEP_YES | KEEP_NO else text)
    # A bare yes or no beside a fuller answer only leads into it: "yes, just this week" is this week only.
    said = [part for part in parts if part not in KEEP_BARE] or parts
    answers = {True if part in KEEP_YES else False if part in KEEP_NO else None for part in said}
    return answers.pop() if len(answers) == 1 else None


class AgentSessionNotFoundError(LookupError):
    pass


def _variety_decision(message: str) -> ScopeDecision:
    """A wish for more variety in a planned week, answered with choices or a new week."""
    return ScopeDecision(
        scope_class=ScopeClass.DOMAIN_ACTION,
        detected_intents=["more_variety"],
        supported_segments=[message],
        should_mutate_state=True,  # a question with choices, as a replanning question is
        reason_code="VARIETY_REQUEST",
    )


class AgentSessionNotReadyError(ValueError):
    pass


class AgentPlanNotFoundError(LookupError):
    pass


def profile_constraints(version) -> AgentConstraintState:
    """The saved household version as the starting point of a conversation."""
    return AgentConstraintState.model_validate(
        {
            "household_size": version.planning_household_size,
            "max_cooking_time_minutes": version.max_cooking_time_minutes,
            "budget_per_meal_sgd": version.budget_per_meal_sgd,
            "weekly_budget_sgd": version.weekly_budget_sgd,
            "allergens": version.allergens,
            "excluded_ingredients": version.excluded_ingredients,
            "dietary_preferences": version.dietary_preferences,
            "health_preferences": version.health_preferences,
            "nutrition_targets": version.nutrition_targets,
            "max_sodium_mg_per_meal": version.max_sodium_mg_per_meal,
            "available_ingredients": version.available_ingredients,
            "pricing_mode": version.pricing_mode,
            "plan_shape": version.plan_shape
            or ({"meals": {"dinner": version.meal_composition}} if version.meal_composition else None),
        }
    )


def _vector_meta(relative: str) -> str | None:
    """The model and size of a stored vector file (`model@dimensions`), or None when it is absent."""
    import json

    from app.core.paths import repository_root

    path = repository_root() / relative
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        head = handle.read(4096)
    model = re.search(r'"model"\s*:\s*"([^"]+)"', head)
    dimensions = re.search(r'"dimensions"\s*:\s*(\d+)', head)
    if model is None:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return f"{meta.get('model')}@{meta.get('dimensions')}"
    return f"{model.group(1)}@{dimensions.group(1) if dimensions else '?'}"


def _replay_input(message: str, **turn) -> dict:
    """A turn's full input, taken before the turn runs, so the console can re-run it (ADR-0047)."""
    return {"message": message, **to_jsonable_python(turn)}


def _replay_record(turn_input: dict, outcome: AgentTurnOutcome | None) -> dict:
    return {
        "input": turn_input,
        "outcome": (
            None
            if outcome is None
            else to_jsonable_python(
                outcome.model_dump(include={"constraints", "assistant_message", "status", "missing_fields"})
            )
        ),
    }


class AgentSessionService:
    def __init__(
        self,
        *,
        repository: AgentSessionRepository,
        parser: ConstraintParser,
        meal_plan_service: WeeklyMealPlanService,
        replanning_service: MealPlanReplanningService,
        run_repository: AgentRunRepository,
        actor_user_id: int,
        household_id: int,
        max_history_messages: int = 20,
        starting_constraints: AgentConstraintState | None = None,
        keep_plan_shape: Callable[[MealPlanShape], None] | None = None,
    ) -> None:
        # A new conversation starts from the saved household, so it does not ask what the
        # profile already says; anything the message states is merged over it.
        self.starting_constraints = starting_constraints
        self.repository = repository
        self.parser = parser
        self.orchestrator = BoundedAgentOrchestrator(parser, check=self._refusal)
        self.scope_policy = ReferenceScopePolicy()
        self.meal_plan_service = meal_plan_service
        self.replanning_service = replanning_service
        self.replan_interpreter = AgentReplanInterpreter()
        self.run_lifecycle = AgentRunLifecycle(run_repository)
        self.actor_user_id = actor_user_id
        self.household_id = household_id
        self.max_history_messages = max_history_messages
        # Saves a shape changed in the conversation as the household's usual one, on a yes (ADR-0046).
        self.keep_plan_shape = keep_plan_shape

    # Count this turn from its start, before its run exists.
    @model_client.counting()
    def create(
        self, message: str, *, idempotency_key: str | None = None, plan_id: int | None = None
    ) -> AgentSessionResponse:
        current = (self.starting_constraints or AgentConstraintState()).model_copy(deep=True)
        if plan_id is not None:
            # A change to a week no open conversation planned (one made on the profile page): the new
            # conversation starts as that week's, and the message changes it rather than planning another.
            self._require_plan(plan_id)
            agent_session = self.repository.create_for_plan(
                provider=self.parser.provider, constraints=current, plan_id=plan_id
            )
            return self.reply(agent_session.id, message, idempotency_key=idempotency_key)
        turn_input = _replay_input(
            message,
            current=current,
            acknowledged_unknowns=[],
            history=[],
            current_status="collecting",
            current_missing_fields=[],
            current_questions=[],
            context_version=0,
        )
        result = self.orchestrator.process(
            message,
            current=current,
            acknowledged_unknowns=[],
            history=[],
            current_status="collecting",
            current_missing_fields=[],
            current_questions=[],
            context_version=0,
        )
        agent_session = self.repository.create(
            provider=self.parser.provider,
            user_message=message,
            assistant_message=result.assistant_message,
            constraints=result.constraints,
            status=result.status,
            missing_fields=result.missing_fields,
            clarification_questions=result.clarification_questions,
            acknowledged_unknowns=result.acknowledged_unknowns,
            context_version=result.context_version,
            scope_decision=result.scope_decision,
            pending_interaction=result.pending_interaction,
        )
        started = self._start_run(
            agent_session_id=agent_session.id,
            intent="create_plan",
            input_payload={"message": message},
            context_version=result.context_version,
            idempotency_key=idempotency_key,
            scope_decision=result.scope_decision,
        )
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        self._finish_turn_run(
            run,
            result_status=result.status,
            scope_decision=result.scope_decision,
            replay=_replay_record(turn_input, result),
        )
        return self._to_response(self.repository.get(agent_session.id) or agent_session)

    def get(self, session_id: int) -> AgentSessionResponse | None:
        agent_session = self.repository.get(session_id)
        return self._to_response(agent_session) if agent_session is not None else None

    def list_recent(self, *, limit: int) -> AgentSessionCollectionResponse:
        return AgentSessionCollectionResponse(
            items=[self._to_response(item) for item in self.repository.list_recent(limit=limit)]
        )

    @model_client.counting()
    def reply(
        self,
        session_id: int,
        message: str,
        *,
        idempotency_key: str | None = None,
        plan_id: int | None = None,
    ) -> AgentSessionResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        if plan_id is not None and agent_session.plan_id != plan_id:
            agent_session = self._take_plan(agent_session, plan_id)
        snapshot = self._to_response(agent_session)
        started = self._start_run(
            agent_session_id=session_id,
            intent="replan_meal" if snapshot.plan_id is not None else "create_plan",
            input_payload={"message": message},
            context_version=snapshot.context_version,
            plan_revision=(snapshot.pending_replan.base_revision if snapshot.pending_replan is not None else None),
            idempotency_key=idempotency_key,
        )
        if started.replayed:
            self.repository.end_read_transaction()
            return self.get(session_id) or snapshot
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        if snapshot.plan_id is not None:
            self.repository.end_read_transaction()
            try:
                response = (
                    self._plan_again(session_id, snapshot, message, run)
                    if VARIED_WEEK.search(message.lower())
                    else self._reply_to_planned(session_id, snapshot, message)
                )
            except Exception as error:
                self._fail_run(run, error)
                raise
            # A turn that leaves a question open waits for its answer; any other is done (an answer, a new week).
            asks = bool(response.clarification_questions) or response.pending_interaction is not None
            self._finish_turn_run(
                run,
                result_status="collecting" if asks and response.plan_id == snapshot.plan_id else "planned",
                scope_decision=response.last_scope_decision,
                has_preview=response.pending_replan is not None,
            )
            return self.get(session_id) or response
        acknowledged = list(agent_session.acknowledged_unknown_quantities)
        self.repository.end_read_transaction()

        turn = {
            "current": snapshot.constraints,
            "acknowledged_unknowns": acknowledged,
            "history": snapshot.messages[-self.max_history_messages :],
            "current_status": snapshot.status,
            "current_missing_fields": snapshot.missing_fields,
            "current_questions": snapshot.clarification_questions,
            "context_version": snapshot.context_version,
            "pending_interaction": snapshot.pending_interaction,
        }
        turn_input = _replay_input(message, **turn)
        try:
            result = self.orchestrator.process(message, **turn)
        except Exception as error:
            self._fail_run(run, error, replay=_replay_record(turn_input, None))
            raise
        if not result.state_mutated:
            updated = self.repository.append_bounded_exchange(
                session_id,
                user_message=message,
                assistant_message=result.assistant_message,
                scope_decision=result.scope_decision,
                pending_interaction=result.pending_interaction,
            )
            if updated is None:
                raise AgentSessionNotFoundError
            self._finish_turn_run(
                run,
                result_status=result.status,
                scope_decision=result.scope_decision,
                replay=_replay_record(turn_input, result),
            )
            return self._to_response(updated)
        updated = self.repository.append_exchange(
            session_id,
            user_message=message,
            assistant_message=result.assistant_message,
            constraints=result.constraints,
            status=result.status,
            missing_fields=result.missing_fields,
            clarification_questions=result.clarification_questions,
            acknowledged_unknowns=result.acknowledged_unknowns,
            context_version=result.context_version,
            scope_decision=result.scope_decision,
            pending_interaction=result.pending_interaction,
        )
        if updated is None:
            raise AgentSessionNotFoundError
        self._finish_turn_run(
            run,
            result_status=result.status,
            scope_decision=result.scope_decision,
            replay=_replay_record(turn_input, result),
        )
        return self._to_response(updated)

    def _require_plan(self, plan_id: int) -> None:
        if self.meal_plan_service.get(plan_id) is None:
            raise AgentPlanNotFoundError

    def _take_plan(self, agent_session: AgentSession, plan_id: int) -> AgentSession:
        """A conversation that planned no week (an unrelated question, or one still collecting) asked to
        change the household's week beside it: it becomes that week's conversation. One that already
        has a week keeps it: a conversation changes one week."""
        if agent_session.plan_id is not None:
            raise AgentSessionNotReadyError("This conversation changes another week. Open that week's conversation.")
        self._require_plan(plan_id)
        attached = self.repository.attach_plan(agent_session.id, plan_id=plan_id)
        if attached is None:
            raise AgentSessionNotFoundError
        return attached

    def answer_interaction(
        self,
        session_id: int,
        answer: InteractionAnswer,
        *,
        idempotency_key: str | None = None,
    ) -> AgentSessionResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        self.repository.end_read_transaction()
        if snapshot.pending_interaction is None:
            raise AgentSessionNotReadyError("There is no pending structured interaction.")
        try:
            values = validate_interaction_answer(
                snapshot.pending_interaction,
                answer,
                current_context_version=snapshot.context_version,
                current_plan_revision=(
                    snapshot.pending_replan.base_revision if snapshot.pending_replan is not None else None
                ),
            )
        except InteractionAnswerError as error:
            raise AgentSessionNotReadyError(str(error)) from error
        if len(values) != 1:
            raise AgentSessionNotReadyError("This interaction requires exactly one answer.")
        message = self._interaction_value_as_message(
            snapshot.pending_interaction, values[0], lang=language("", snapshot.messages)
        )
        return self.reply(session_id, message, idempotency_key=idempotency_key)

    @staticmethod
    def _grocery_evidence(estimate) -> dict:
        """What the saved plan's prices rest on: the packet's digest, how each was obtained, and whether
        every shown line cost and the total recompute from the observations alone."""
        packet = grocery_packet(estimate)
        report = verify_grocery_totals(estimate, packet)
        return {
            "kind": "retrieval_packet",
            "purpose": packet.purpose,
            "digest": packet_digest(packet),
            "items": len(packet.items),
            "modes": sorted({str(item.facts["mode"]) for item in packet.items}),
            "unsupported_claims": report.unsupported_claim_ids,
            "warnings": packet.warnings,
        }

    @staticmethod
    def _interaction_value_as_message(request: InteractionRequest, value: object, *, lang: str = "en") -> str:
        """What the household's choice says, in the conversation's language, so the reply stays in it."""
        if request.field_path == SAY_FIELD:
            return str(value).strip()
        if request.field_path == KEEP_SHAPE_FIELD:
            return say("keep_usual_say" if value == "keep" else "just_this_week", lang)
        if request.field_path == "household_size":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise AgentSessionNotReadyError("Household size must be a number.")
            if isinstance(value, str) and not value.strip().isdigit():
                return value.strip()
            return say("people_say", lang, count=int(value))
        if request.field_path and request.field_path.endswith(".quantity"):
            return str(value)
        if request.field_path and request.field_path.startswith("unmatched."):
            meant_for, _, term = request.field_path.removeprefix("unmatched.").partition(".")
            if meant_for == "excluded_ingredients":
                return say("exclude_say", lang, value=value, term=term)
            if meant_for == "available_ingredients":
                return say("have_say", lang, value=value, term=term)
        raise AgentSessionNotReadyError("This interaction field is not supported by the current runtime.")

    def _plan_request(self, constraints: AgentConstraintState) -> WeeklyMealPlanRequest:
        return WeeklyMealPlanRequest(
            start_date=date.today(),
            day_count=7,
            household_size=constraints.household_size,
            max_cooking_time_minutes=constraints.max_cooking_time_minutes,
            budget_per_meal_sgd=constraints.budget_per_meal_sgd,
            weekly_budget_sgd=constraints.weekly_budget_sgd,
            allergens=constraints.allergens,
            excluded_ingredients=constraints.excluded_ingredients,
            dietary_preferences=constraints.dietary_preferences,
            health_preferences=constraints.health_preferences,
            nutrition_targets=constraints.nutrition_targets,
            max_sodium_mg_per_meal=constraints.max_sodium_mg_per_meal,
            available_ingredients=constraints.available_ingredients,
            pricing_mode=constraints.pricing_mode,
            plan_shape=constraints.plan_shape or default_plan_shape(),
            max_uses_per_recipe=constraints.max_uses_per_recipe,
            avoid_recipe_ids=constraints.avoid_recipe_ids,
        )

    def _refusal(self, constraints: AgentConstraintState, lang: str) -> limits.Refusal | None:
        """A limit no week the planner could build meets: the floor's proofs, and near it the planner's own answer."""
        try:
            request = self._plan_request(constraints)
        except ValueError:
            return None  # the request itself is refused when the week is planned, with its own reason
        try:
            return limits.refusal(
                constraints,
                lambda **changes: self.meal_plan_service.week_floor(request.model_copy(update=changes)),
                lang,
                check=lambda **changes: self.meal_plan_service.check(request.model_copy(update=changes)),
                cheapest=self._cheapest(request),
            )
        except (ProductProviderError, WeeklyPlanSelectionError):
            # Prices or recipes could not be read now: nothing is refused, and Plan answers for itself.
            return None

    def _cheapest(self, request: WeeklyMealPlanRequest) -> Callable[..., float | None]:
        """What the cheapest week the planner's search finds for `request` with changes costs; None for none."""

        def cheapest(**changes) -> float | None:
            try:
                return self.meal_plan_service.cheapest_week(request.model_copy(update=changes))
            except (ProductProviderError, WeeklyPlanSelectionError):
                return None

        return cheapest

    def _reply_to_planned(
        self,
        session_id: int,
        snapshot: AgentSessionResponse,
        message: str,
    ) -> AgentSessionResponse:
        if snapshot.plan_id is None:
            raise AgentSessionNotReadyError("Generate a plan before requesting a replanning event.")
        lang = language(message, snapshot.messages)
        interaction = snapshot.pending_interaction
        if interaction is not None and interaction.field_path == KEEP_SHAPE_FIELD:
            keep = keep_shape_answer(message)
            if keep is not None:
                return self._answer_keep_shape(session_id, snapshot, message, keep=keep, lang=lang)
            # Not an answer but a new instruction ("no lunch on weekdays, keep the weekend"): the question lapses,
            # so the change stays this week's only, and the message is read as any other.
            snapshot = snapshot.model_copy(update={"pending_interaction": None})
        elif interaction is not None and interaction.field_path == SAY_FIELD:
            # Typed instead of tapped ("swap it", "add another", 再加一道): what the option it names would send.
            chosen = typed_choice(interaction, message)
            message = chosen if isinstance(chosen, str) else message
        if wants_variety(message):
            return self._offer_variety(session_id, snapshot, message, lang)
        # An open question ("which dish?") is answered by what answers it; a request that stands on its own
        # ("also plan lunch") is handled instead, and the question goes.
        changed = self._change_shape(
            session_id, snapshot, message, lang, pending=bool(snapshot.clarification_questions)
        )
        if changed is not None:
            return changed
        plan = self.meal_plan_service.get(snapshot.plan_id)
        if plan is None:
            raise AgentSessionNotFoundError
        scope_decision = self.scope_policy.classify(message)
        if scope_decision.scope_class is ScopeClass.AMBIGUOUS and snapshot.clarification_questions:
            scope_decision = ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["replan_clarification_answer"],
                supported_segments=[message],
                should_mutate_state=True,
                reason_code="PENDING_REPLAN_CLARIFICATION_RESPONSE",
            )
        elif (
            scope_decision.scope_class is ScopeClass.AMBIGUOUS
            and self.replan_interpreter._event_type(message.lower(), self.replan_interpreter.titles(plan)) is not None
        ):
            # "别动周一的晚饭", "keep Friday's soup": keeping, skipping or swapping a dish of the week, in words the
            # scope gate does not list.
            scope_decision = ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["replan_meal"],
                supported_segments=[message],
                should_mutate_state=True,
                reason_code="REPLAN_REQUEST",
            )
        if not scope_decision.should_mutate_state:
            reply, choices = self.orchestrator.boundary_message(scope_decision, lang), None
            if scope_decision.scope_class is ScopeClass.AMBIGUOUS:
                # Not a dead end: what can change in the week, as choices.
                wish = FOOD_WISH.search(message.lower()) is not None
                reply = say("wish_planned", lang) if wish else reply
                options = (
                    wish_options(lang, planned=True)
                    if wish
                    else self.replan_interpreter.choices(AgentReplanDraft(), None, lang)
                )
                choices = self._choices(snapshot, options, lang)
            updated = self.repository.append_bounded_exchange(
                session_id,
                user_message=message,
                assistant_message=reply,
                scope_decision=scope_decision,
                pending_interaction=choices if choices is not None else snapshot.pending_interaction,
            )
            if updated is None:
                raise AgentSessionNotFoundError
            return self._to_response(updated)

        draft, questions = self.replan_interpreter.parse(
            message,
            plan=plan,
            current=snapshot.replan_draft,
            lang=lang,
        )
        if questions:
            updated = self.repository.append_replan_exchange(
                session_id,
                user_message=message,
                assistant_message=questions[0],
                draft=draft,
                clarification_questions=questions,
                pending_event_id=None,
                scope_decision=scope_decision,
                pending_interaction=self._choices(snapshot, self.replan_interpreter.choices(draft, plan, lang), lang),
            )
        elif draft.event_type == "LOCK_MEAL" and (kept := self._already_kept(plan, draft, lang)) is not None:
            updated = self.repository.append_replan_exchange(
                session_id,
                user_message=message,
                assistant_message=kept,
                draft=AgentReplanDraft(),
                clarification_questions=[],
                pending_event_id=None,
                scope_decision=scope_decision,
            )
        else:
            try:
                preview = self.replanning_service.preview(
                    plan_id=plan.id,
                    request=MealPlanReplanPreviewRequest(
                        event_type=draft.event_type,
                        entry_id=draft.entry_id,
                        reason=draft.reason,
                        unavailable_ingredient=(
                            draft.unavailable_ingredient if draft.event_type == "ITEM_UNAVAILABLE" else None
                        ),
                        whole_meal=draft.whole_meal and draft.event_type == "LOCK_MEAL",
                    ),
                )
            except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
                updated = self.repository.append_replan_exchange(
                    session_id,
                    user_message=message,
                    assistant_message=say("prepare_failed", lang, error=planner_message(str(error), lang)),
                    draft=AgentReplanDraft(),
                    clarification_questions=[],
                    pending_event_id=None,
                    scope_decision=scope_decision,
                )
            else:
                updated = self.repository.append_replan_exchange(
                    session_id,
                    user_message=message,
                    assistant_message=self._describe_dish_preview(preview, plan, lang),
                    draft=draft,
                    clarification_questions=[],
                    pending_event_id=preview.id,
                    scope_decision=scope_decision,
                )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    def _offer_variety(
        self, session_id: int, snapshot: AgentSessionResponse, message: str, lang: str
    ) -> AgentSessionResponse:
        """A wish for variety ("the dishes are boring", 菜很单调): a new week of different dishes, or a swap."""
        plan = self.meal_plan_service.get(snapshot.plan_id)
        if plan is None:
            raise AgentSessionNotFoundError
        options = [(say("replan_varied", lang), say("replan_varied_say", lang)), self._swap_option(plan, lang)]
        reply = say("variety_planned", lang)
        updated = self.repository.append_bounded_exchange(
            session_id,
            user_message=message,
            assistant_message=reply,
            scope_decision=_variety_decision(message),
            pending_interaction=self._choices(snapshot, options, lang),
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    @staticmethod
    def _swap_option(plan: WeeklyMealPlanResponse, lang: str) -> tuple[str, str]:
        """A dish to swap for more variety: the first that repeats, else any dish."""
        seen: set[int] = set()
        for dish in sorted(plan.days, key=lambda item: (item.day_index, item.entry_id)):
            if dish.recipe.id in seen:
                values = {"title": dish.recipe.title, "day": weekday(dish.planned_date, lang), "index": dish.day_index}
                return say("swap_repeat", lang, **values), say("swap_repeat_say", lang, **values)
            seen.add(dish.recipe.id)
        return say("swap_other", lang), say("swap_say", lang)

    def _plan_again(
        self, session_id: int, snapshot: AgentSessionResponse, message: str, run: AgentRun
    ) -> AgentSessionResponse:
        """The week's repeated dishes swapped for different ones within its budget, previewed, for a household that
        found it monotonous; when no different dish fits, the week stays and the reply says what it would take.

        "The dishes are boring" (菜很单调) asks for this, not a new week (owner, 2026-10-04): a new week under the
        same budget, avoiding every dish of this one, had only dearer dishes left and came out less varied.
        """
        plan = self.meal_plan_service.get(snapshot.plan_id)
        if plan is None:
            raise AgentSessionNotFoundError
        lang = language(message, snapshot.messages)
        try:
            preview, repeats, short = self.replanning_service.preview_variety(plan_id=plan.id, reason=message.strip())
        except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
            reply = say("change_failed", lang, error=planner_message(str(error), lang))
            return self._keep_week(session_id, snapshot, plan, message, reply, lang)
        # What the week can spend: its budget, or what it costs now when a change took it over (ADR-0046 section 2).
        budget = plan.grocery_estimate.weekly_budget_sgd
        limit = max(budget, plan.grocery_estimate.purchase_total_sgd) if budget is not None else None
        if preview is None:
            if not repeats:
                reply = say("varied_none", lang)
            elif short is not None and limit is not None:
                reply = say("varied_short", lang, limit=limit, extra=short)
            else:
                reply = say("varied_nothing", lang)
            return self._keep_week(session_id, snapshot, plan, message, reply, lang)
        change = preview.shape_change
        before = {(dish.day_index, dish.meal_type, dish.role_id): dish.recipe_title for dish in change.removed}
        swaps = [
            say(
                "varied_swap",
                lang,
                day=weekday(plan.start_date + timedelta(days=dish.day_index - 1), lang),
                before=before[(dish.day_index, dish.meal_type, dish.role_id)],
                after=dish.recipe_title,
            )
            for dish in change.added
        ]
        left = repeats - len(swaps)
        reply = (
            say("varied_swaps", lang, swaps=("；" if lang == "zh" else "; ").join(swaps))
            + (say("varied_left", lang, count=left, extra=short, limit=limit) if left and short is not None else "")
            + self._over_budget(preview, plan, lang)
            + say("until_confirm", lang)
        )
        updated = self.repository.append_replan_exchange(
            session_id,
            user_message=message,
            assistant_message=reply,
            draft=AgentReplanDraft(event_type="CHANGE_SHAPE", reason=message.strip()),
            clarification_questions=[],
            pending_event_id=preview.id,
            scope_decision=_variety_decision(message),
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    def _keep_week(
        self,
        session_id: int,
        snapshot: AgentSessionResponse,
        plan: WeeklyMealPlanResponse,
        message: str,
        reply: str,
        lang: str,
    ) -> AgentSessionResponse:
        """No new week replaced this one: say why, and offer a swap instead."""
        updated = self.repository.append_bounded_exchange(
            session_id,
            user_message=message,
            assistant_message=reply,
            scope_decision=_variety_decision(message),
            pending_interaction=self._choices(snapshot, [self._swap_option(plan, lang)], lang),
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    def _choices(self, snapshot: AgentSessionResponse, options: list[tuple[str, str]], lang: str):
        """Choices for the question just asked of a planned week; None when there is nothing to choose."""
        if not options:
            return None
        return say_interaction(
            options=options,
            question_id=f"replan-{snapshot.id}-{len(snapshot.messages)}",
            context_version=max(snapshot.context_version, 1),
            lang=lang,
        )

    def _change_shape(
        self, session_id: int, snapshot: AgentSessionResponse, message: str, lang: str = "en", *, pending=False
    ) -> AgentSessionResponse | None:
        """A request to add, drop or recompose a meal, previewed; None when the message asks for something else.

        While a question is `pending`, only a request that stands on its own is one: "no, the soup" answers
        "which dish?" rather than taking the soup off.
        """
        plan = self.meal_plan_service.get(snapshot.plan_id)
        if plan is None:
            raise AgentSessionNotFoundError
        if self.replan_interpreter._event_type(message.lower(), self.replan_interpreter.titles(plan)) is not None:
            return None  # swap, skip, lock or can't buy: one dish, not the meal's shape
        days = self.replan_interpreter.day_indexes(message.lower(), plan)
        intent = read_shape_change(message, plan=plan, day_indexes=days, lang=lang)
        if intent is None or (pending and not intent.stands_alone):
            return None
        decision = ScopeDecision(
            scope_class=ScopeClass.DOMAIN_ACTION,
            detected_intents=["change_plan_shape"],
            supported_segments=[message],
            should_mutate_state=True,
            reason_code="PLAN_SHAPE_CHANGE",
        )
        if intent.ask is not None:
            # "Add a soup to Friday dinner" when it has one: a second soup, or that one swapped?
            updated = self.repository.append_replan_exchange(
                session_id,
                user_message=message,
                assistant_message=intent.ask,
                draft=AgentReplanDraft(),
                clarification_questions=[],
                pending_event_id=None,
                scope_decision=decision,
                pending_interaction=self._choices(snapshot, list(intent.ask_options), lang),
            )
            if updated is None:
                raise AgentSessionNotFoundError
            return self._to_response(updated)
        try:
            preview = self.replanning_service.preview_shape(plan_id=plan.id, request=intent.request)
        except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
            reply, pending, draft = (
                say("change_failed", lang, error=planner_message(str(error), lang)),
                None,
                AgentReplanDraft(),
            )
        else:
            reply, pending = self._describe_shape_preview(intent.summary, preview, plan, lang), preview.id
            draft = AgentReplanDraft(event_type="CHANGE_SHAPE", reason=message.strip())
        updated = self.repository.append_replan_exchange(
            session_id,
            user_message=message,
            assistant_message=reply,
            draft=draft,
            clarification_questions=[],
            pending_event_id=pending,
            scope_decision=decision,
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    @staticmethod
    def _over_budget(preview: MealPlanReplanEventResponse, plan: WeeklyMealPlanResponse, lang: str = "en") -> str:
        """How far a change takes the week over its budget, as the preview card says it; empty within it."""
        over, budget = preview.over_budget_sgd, plan.grocery_estimate.weekly_budget_sgd
        return say("shape_over", lang, total=budget + over, over=over, budget=budget) if over and budget else ""

    @staticmethod
    def _describe_shape_preview(
        summary: str, preview: MealPlanReplanEventResponse, plan: WeeklyMealPlanResponse, lang: str = "en"
    ) -> str:
        """The change, its dishes and its groceries, and what it puts the week over its budget."""
        change = preview.shape_change
        parts = [say("shape_summary", lang, summary=summary)]
        if change and change.added:
            titles = list(dict.fromkeys(dish.recipe_title for dish in change.added))
            more = say("shape_more", lang, count=len(titles) - 4) if len(titles) > 4 else ""
            parts.append(say("shape_new", lang, titles=("、" if lang == "zh" else ", ").join(titles[:4]), more=more))
        if change and change.removed:
            count = len(change.removed)
            parts.append(say("shape_removed_one" if count == 1 else "shape_removed", lang, count=count))
        delta = preview.purchase_total_delta_sgd
        budget = plan.grocery_estimate.weekly_budget_sgd
        total = round(plan.grocery_estimate.purchase_total_sgd + delta, 2)
        over = (
            say("shape_over", lang, total=total, over=total - budget, budget=budget)
            if preview.over_budget_sgd is not None and budget is not None
            else ""
        )
        if delta == 0:
            parts.append(say("shape_groceries_same", lang))  # the packages it needs are bought already
        else:
            parts.append(say("shape_groceries", lang, sign="+" if delta > 0 else "−", amount=abs(delta), over=over))
        return ("" if lang == "zh" else " ").join(parts)

    def _describe_dish_preview(
        self, preview: MealPlanReplanEventResponse, plan: WeeklyMealPlanResponse, lang: str
    ) -> str:
        """A keep, skip or swap of one dish (or a keep of a whole meal), what it does to the groceries and the
        budget, before anything changes."""
        before = preview.before_entry
        if preview.event_type == "LOCK_MEAL" and len(preview.meal_entries) > 1:
            day = next(dish.planned_date for dish in plan.days if dish.day_index == before.day_index)
            titles = listed([dish.recipe_title for dish in preview.meal_entries], lang)
            text = say(
                "preview_lock_meal", lang, meal=word(before.meal_type, lang), day=weekday(day, lang), titles=titles
            )
        elif preview.event_type == "LOCK_MEAL":
            text = say("preview_lock", lang, title=before.recipe_title)
        elif preview.event_type == "CANCEL_MEAL":
            text = say("preview_skip", lang, title=before.recipe_title) + self._skip_groceries(preview, plan.id, lang)
        else:
            after = preview.after_entry.recipe_title if preview.after_entry else ""
            text = say("preview_swap", lang, before=before.recipe_title, after=after)
        return text + self._over_budget(preview, plan, lang) + say("until_confirm", lang)

    @staticmethod
    def _already_kept(plan: WeeklyMealPlanResponse, draft: AgentReplanDraft, lang: str) -> str | None:
        """A keep said again after it was confirmed: that the dish, or the whole meal, is kept already; None while
        there is something left to keep."""
        target = next((dish for dish in plan.days if dish.entry_id == draft.entry_id), None)
        if target is None or not target.is_locked:
            return None
        if draft.whole_meal:
            meal, day = word(target.meal_type, lang), weekday(target.planned_date, lang)
            return say("already_kept_meal", lang, meal=meal, day=day)
        return say("already_kept", lang, title=target.recipe.title)

    def _skip_groceries(self, preview: MealPlanReplanEventResponse, plan_id: int, lang: str) -> str:
        """What skipping a dish takes off the groceries; or, when other dishes still need its whole packages,
        that the groceries stay the same and what still uses them (never a bare +S$0.00)."""
        delta = preview.purchase_total_delta_sgd
        if delta <= -0.005:
            return say("skip_saves", lang, amount=-delta)
        if delta >= 0.005:  # a cheaper mix of packages for what is left can cost more; said as it is
            return say("skip_costs", lang, amount=delta)
        # The skipped dish's own ingredients whose whole packages are still bought: less is needed, as many
        # packages are.
        kept = [
            line
            for line in preview.grocery_delta
            if line.after_packages_required
            and line.after_packages_required == line.before_packages_required
            and (line.after_required_quantity or 0) < (line.before_required_quantity or 0)
        ]
        users = self.replanning_service.dishes_using(
            plan_id=plan_id,
            entry_id=preview.before_entry.entry_id,
            ingredients=[line.ingredient_name for line in kept],
        )
        skipped = preview.before_entry.recipe_title
        uses: dict[str, str] = {}
        for line in kept:
            item = word(line.ingredient_name, lang) if lang == "zh" else line.ingredient_display_name.lower()
            # Another dish first; the same dish on another day of the week only when nothing else uses it.
            titles = sorted(users.get(line.ingredient_name, []), key=lambda title: title == skipped)
            if titles and item not in uses:
                again = titles[0] == skipped
                uses[item] = say("skip_used_again" if again else "skip_used_by", lang, item=item, title=titles[0])
        if not uses:
            return say("skip_same", lang)
        return say("skip_still_used", lang, uses=listed(list(uses.values())[:3], lang))

    def _answer_keep_shape(
        self, session_id: int, snapshot: AgentSessionResponse, message: str, *, keep: bool, lang: str = "en"
    ) -> AgentSessionResponse:
        """After a week's shape changed: keep it as the household's usual one only on a yes (`keep_shape_answer`)."""
        plan = self.meal_plan_service.get(snapshot.plan_id) if keep else None
        if keep and plan is not None and plan.plan_shape is not None and self.keep_plan_shape is not None:
            self.keep_plan_shape(plan.plan_shape)
            reply = say("kept", lang)
        elif keep:
            reply = say("keep_failed", lang)
        else:
            reply = say("week_only", lang)
        updated = self.repository.append_replan_exchange(
            session_id,
            user_message=message,
            assistant_message=reply,
            draft=AgentReplanDraft(),
            clarification_questions=[],
            pending_event_id=None,
            scope_decision=ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["keep_plan_shape"],
                supported_segments=[message],
                should_mutate_state=True,
                reason_code="KEEP_SHAPE_ANSWER",
            ),
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    def confirm(
        self,
        session_id: int,
        *,
        idempotency_key: str | None = None,
    ) -> AgentConfirmationResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        self.repository.end_read_transaction()
        started = self._start_run(
            agent_session_id=session_id,
            intent="create_plan",
            input_payload={"operation": "confirm_plan", "context_version": snapshot.context_version},
            context_version=snapshot.context_version,
            idempotency_key=idempotency_key,
        )
        if started.replayed:
            restored = self.get(session_id)
            if restored is None or restored.plan_id is None:
                raise AgentSessionNotReadyError("The previous request with this idempotency key did not save a plan.")
            plan = self.meal_plan_service.get(restored.plan_id)
            if plan is None:
                raise AgentSessionNotFoundError
            return AgentConfirmationResponse(session=restored, plan=plan)
        if not snapshot.can_confirm:
            self.run_lifecycle.transition(
                started.run,
                AgentRunStatus.FAILED,
                termination_reason_code="SESSION_NOT_READY",
                error_code="SESSION_NOT_READY",
            )
            raise AgentSessionNotReadyError("Resolve the outstanding clarification before generating a plan.")

        constraints = snapshot.constraints
        lang = language("", snapshot.messages)
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        request = self._plan_request(constraints)
        try:
            plan = self.meal_plan_service.generate(request)
        except Exception as error:
            self.run_lifecycle.record_tool(
                run,
                tool_name="generate_plan_preview",
                effect=ToolEffect.PREVIEW,
                status=ToolRunStatus.FAILED,
                arguments=request.model_dump(mode="json"),
                provider_mode=constraints.pricing_mode,
                error_code=type(error).__name__,
            )
            self._fail_run(run, error)
            if isinstance(error, WeeklyPlanSelectionError):
                raise WeeklyPlanSelectionError(self._explain_unplanned(snapshot, error, lang)) from error
            raise
        run = self.run_lifecycle.record_tool(
            run,
            tool_name="generate_plan_preview",
            effect=ToolEffect.PREVIEW,
            status=ToolRunStatus.SUCCEEDED,
            arguments=request.model_dump(mode="json"),
            result_reference=f"meal-plan:{plan.id}:revision:{plan.revision}",
            provider_mode=constraints.pricing_mode,
        )
        updated = self.repository.mark_planned(session_id, plan_id=plan.id, assistant_message=say("planned", lang))
        if updated is None:
            self._fail_run(run, AgentSessionNotFoundError())
            raise AgentSessionNotFoundError
        run = self.run_lifecycle.record_tool(
            run,
            tool_name="save_plan_revision",
            effect=ToolEffect.COMMIT,
            status=ToolRunStatus.SUCCEEDED,
            arguments={"plan_id": plan.id, "revision": plan.revision},
            result_reference=f"meal-plan:{plan.id}:revision:{plan.revision}",
            provider_mode=constraints.pricing_mode,
        )
        run = self.run_lifecycle.checkpoint(
            run,
            stage="plan_committed",
            status="succeeded",
            state_payload={"plan_id": plan.id, "plan_revision": plan.revision},
            evidence_references=[
                {"kind": "meal_plan", "reference": f"meal-plan:{plan.id}:revision:{plan.revision}"},
                self._grocery_evidence(plan.grocery_estimate),
            ],
        )
        self.run_lifecycle.transition(run, AgentRunStatus.COMMITTED, termination_reason_code="PLAN_SAVED")
        return AgentConfirmationResponse(session=self.get(session_id) or self._to_response(updated), plan=plan)

    def confirm_replan(
        self,
        session_id: int,
        *,
        idempotency_key: str | None = None,
    ) -> AgentReplanConfirmationResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        if snapshot.plan_id is None or snapshot.pending_replan is None:
            self.repository.end_read_transaction()
            raise AgentSessionNotReadyError("There is no replanning preview to confirm.")
        plan_id = snapshot.plan_id
        event_id = snapshot.pending_replan.id
        base_revision = snapshot.pending_replan.base_revision
        self.repository.end_read_transaction()
        started = self._start_run(
            agent_session_id=session_id,
            intent="replan_meal",
            input_payload={"operation": "confirm_replan", "plan_id": plan_id, "event_id": event_id},
            context_version=snapshot.context_version,
            plan_revision=base_revision,
            idempotency_key=idempotency_key,
        )
        if started.replayed:
            restored = self.get(session_id)
            plan = self.meal_plan_service.get(plan_id)
            if restored is None or plan is None:
                raise AgentSessionNotFoundError
            event = self.replanning_service.get_event(plan_id=plan_id, event_id=event_id)
            if event is None:
                raise AgentSessionNotFoundError
            return AgentReplanConfirmationResponse(session=restored, event=event, plan=plan)
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        try:
            result = self.replanning_service.confirm(plan_id=plan_id, event_id=event_id)
        except Exception as error:
            self.run_lifecycle.record_tool(
                run,
                tool_name="confirm_replan",
                effect=ToolEffect.COMMIT,
                status=ToolRunStatus.FAILED,
                arguments={"plan_id": plan_id, "event_id": event_id, "base_revision": base_revision},
                error_code=type(error).__name__,
            )
            self._fail_run(run, error)
            raise
        run = self.run_lifecycle.record_tool(
            run,
            tool_name="confirm_replan",
            effect=ToolEffect.COMMIT,
            status=ToolRunStatus.SUCCEEDED,
            arguments={"plan_id": plan_id, "event_id": event_id, "base_revision": base_revision},
            result_reference=f"meal-plan:{plan_id}:revision:{result.plan.revision}",
        )
        ask_keep = (
            result.event.shape_change is not None
            and result.event.shape_change.scope == "week"
            and self.keep_plan_shape is not None
        )
        lang = language("", snapshot.messages)
        question = say("ask_keep", lang)
        done = say("replanned", lang)
        updated = self.repository.finish_replan(
            session_id,
            assistant_message=done + (("" if lang == "zh" else " ") + question if ask_keep else ""),
            pending_interaction=(
                InteractionRequest(
                    type=InteractionType.QUICK_REPLY,
                    prompt=short_prompt(True, lang),
                    field_path=KEEP_SHAPE_FIELD,
                    question_id=f"keep-shape-{event_id}",
                    options=[
                        InteractionOption(id="keep", label=say("keep_usual", lang), value="keep"),
                        InteractionOption(id="week", label=say("just_this_week", lang), value="week"),
                    ],
                    context_version=snapshot.context_version,
                ).model_dump(mode="json")
                if ask_keep
                else None
            ),
        )
        if updated is None:
            self._fail_run(run, AgentSessionNotFoundError())
            raise AgentSessionNotFoundError
        run = self.run_lifecycle.checkpoint(
            run,
            stage="replan_committed",
            status="succeeded",
            state_payload={
                "plan_id": plan_id,
                "event_id": event_id,
                "base_revision": base_revision,
                "applied_revision": result.plan.revision,
            },
            evidence_references=[
                {"kind": "meal_plan_event", "reference": f"meal-plan-event:{event_id}"},
                self._grocery_evidence(result.plan.grocery_estimate),
            ],
        )
        self.run_lifecycle.transition(run, AgentRunStatus.COMMITTED, termination_reason_code="REPLAN_APPLIED")
        return AgentReplanConfirmationResponse(
            session=self.get(session_id) or self._to_response(updated),
            event=result.event,
            plan=result.plan,
        )

    def discard_replan(
        self,
        session_id: int,
        *,
        idempotency_key: str | None = None,
    ) -> AgentSessionResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        if snapshot.pending_replan is None and not snapshot.replan_draft.model_dump(exclude_none=True):
            self.repository.end_read_transaction()
            raise AgentSessionNotReadyError("There is no replanning request to discard.")
        self.repository.end_read_transaction()
        started = self._start_run(
            agent_session_id=session_id,
            intent="replan_meal",
            input_payload={"operation": "discard_replan"},
            context_version=snapshot.context_version,
            idempotency_key=idempotency_key,
        )
        if started.replayed:
            return self.get(session_id) or snapshot
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        updated = self.repository.finish_replan(
            session_id, assistant_message=say("discarded", language("", snapshot.messages))
        )
        if updated is None:
            self._fail_run(run, AgentSessionNotFoundError())
            raise AgentSessionNotFoundError
        run = self.run_lifecycle.checkpoint(
            run,
            stage="replan_discarded",
            status="succeeded",
            state_payload={"plan_id": snapshot.plan_id, "mutated": False},
        )
        self.run_lifecycle.transition(run, AgentRunStatus.COMMITTED, termination_reason_code="REPLAN_DISCARDED")
        return self.get(session_id) or self._to_response(updated)

    def _explain_unplanned(self, snapshot: AgentSessionResponse, error: Exception, lang: str) -> str:
        """Say in the conversation why no week was planned, from the planner's trace, with what to change.

        The Plan card gives way to the explanation (the session collects again), unless the same request
        may simply plan next time (slow search, missing data).
        """
        explained = limits.planning_failure(
            error, snapshot.constraints, lang, cheapest=self._cheapest(self._plan_request(snapshot.constraints))
        )
        context_version = max(snapshot.context_version, 1)
        self.repository.explain_unplanned(
            snapshot.id,
            assistant_message=explained.text,
            status="ready" if explained.retry else "collecting",
            missing_fields=[] if explained.retry else [explained.field],
            clarification_questions=[] if explained.retry else [explained.text],
            pending_interaction=None
            if explained.retry
            else say_interaction(
                options=list(explained.options),
                question_id=f"context-{context_version}:unplanned",
                context_version=context_version,
                lang=lang,
            ),
        )
        return explained.text

    def list_runs(self, session_id: int, *, limit: int = 20) -> AgentRunCollectionResponse:
        if self.repository.get(session_id) is None:
            raise AgentSessionNotFoundError
        self.repository.end_read_transaction()
        return AgentRunCollectionResponse(
            items=[
                AgentRunResponse.model_validate(item)
                for item in self.run_lifecycle.repository.list_for_session(session_id, limit=limit)
            ]
        )

    def get_run(self, session_id: int, run_id: int) -> AgentRunResponse:
        run = self.run_lifecycle.repository.get_for_session(session_id, run_id)
        if run is None:
            raise AgentRunNotFoundError
        return AgentRunResponse.model_validate(run)

    def cancel_run(self, session_id: int, run_id: int) -> AgentRunResponse:
        run = self.run_lifecycle.repository.get_for_session(session_id, run_id)
        if run is None:
            raise AgentRunNotFoundError
        cancelled = self.run_lifecycle.cancel(run.id)
        self.run_lifecycle.checkpoint(
            cancelled,
            stage="cancelled",
            status="cancelled",
            state_payload={"reason_code": cancelled.termination_reason_code},
        )
        return AgentRunResponse.model_validate(self.run_lifecycle.repository.get(run.id) or cancelled)

    def _start_run(
        self,
        *,
        agent_session_id: int,
        intent: str,
        input_payload: dict,
        context_version: int,
        idempotency_key: str | None,
        plan_revision: int | None = None,
        scope_decision: ScopeDecision | None = None,
    ) -> StartedRun:
        normalized_key = (idempotency_key or f"generated:{uuid4().hex}").strip()
        if not normalized_key or len(normalized_key) > 120:
            raise AgentRunLifecycleError("Idempotency-Key must contain 1 to 120 characters.")
        return self.run_lifecycle.start(
            agent_session_id=agent_session_id,
            idempotency_key=normalized_key,
            intent=intent,
            input_payload=input_payload,
            context_version=max(context_version, 1),
            plan_revision=plan_revision,
            scope_decision=scope_decision.model_dump(mode="json") if scope_decision is not None else None,
            model_config=self.model_config(),
            actor_user_id=self.actor_user_id,
            household_id=self.household_id,
        )

    def model_config(self) -> dict:
        """The parser and models behind this service's runs; never a key or a prompt."""
        config = {"parser": self.parser.provider, "parser_model": getattr(self.parser, "model", None)}
        if self.parser.provider == "openai":
            vectors = {
                "ingredient_vectors": _vector_meta("data/ingredients/embeddings-v1.json"),
                "recipe_vectors": _vector_meta("data/recipes/embeddings-v1.json"),
            }
            config.update({key: value for key, value in vectors.items() if value})
        return config

    def _finish_turn_run(
        self,
        run: AgentRun,
        *,
        result_status: str,
        scope_decision: ScopeDecision | None,
        has_preview: bool = False,
        replay: dict | None = None,
    ) -> AgentRun:
        scope_payload = scope_decision.model_dump(mode="json") if scope_decision is not None else None
        run.scope_decision = scope_payload
        self._record_model_calls(run)
        fell_back = bool((run.model_config or {}).get("model_fell_back"))
        self.run_lifecycle.repository.session.commit()
        run = self.run_lifecycle.checkpoint(
            run,
            stage="turn_completed",
            status=result_status,
            state_payload={
                "agent_session_id": run.agent_session_id,
                "context_version": run.context_version,
                "result_status": result_status,
                "scope_reason_code": scope_decision.reason_code if scope_decision is not None else None,
                "has_preview": has_preview,
                # What the console needs to re-run this turn (ADR-0047); read only by /api/ops/replay.
                **({"replay": replay} if replay is not None else {}),
            },
        )
        # Degraded is what went wrong: the model did not answer and simple rules read the turn, or the turn was
        # turned away (out of scope, restricted, adversarial). A greeting, a question back with choices or an
        # answered question is a turn done as meant.
        if fell_back:
            return self.run_lifecycle.transition(run, AgentRunStatus.DEGRADED, termination_reason_code="MODEL_FALLBACK")
        if scope_decision is not None and not scope_decision.should_mutate_state:
            reason = f"SCOPE_{scope_decision.scope_class.value.upper()}"
            if scope_decision.scope_class in ANSWERED_SCOPES:
                return self.run_lifecycle.transition(run, AgentRunStatus.COMMITTED, termination_reason_code=reason)
            if scope_decision.scope_class is ScopeClass.AMBIGUOUS:
                return self.run_lifecycle.transition(
                    run, AgentRunStatus.NEEDS_CLARIFICATION, termination_reason_code=reason
                )
            return self.run_lifecycle.transition(run, AgentRunStatus.DEGRADED, termination_reason_code=reason)
        if has_preview:
            return self.run_lifecycle.transition(run, AgentRunStatus.PREVIEW_READY)
        if result_status == "ready":
            return self.run_lifecycle.transition(run, AgentRunStatus.READY_FOR_CONFIRMATION)
        if result_status == "collecting":
            return self.run_lifecycle.transition(
                run,
                AgentRunStatus.NEEDS_CLARIFICATION,
                termination_reason_code="CLARIFICATION_REQUIRED",
            )
        return self.run_lifecycle.transition(run, AgentRunStatus.COMMITTED, termination_reason_code="TURN_COMPLETED")

    @staticmethod
    def _record_model_calls(run: AgentRun) -> None:
        """Puts on the run, for the caller's next commit, every request this turn sent to the model API and
        whether the turn had to go on without the model (model_client counts both).

        A record of work already done, so neither the deadline nor the limit is checked here: the turn is over,
        and a budget stop now would fail a turn whose reply is already saved, or hide why it failed."""
        taken = model_client.take()
        # ponytail: the table holds used <= max, so a turn past its limit records the limit; a turn sends at most
        # 4 (one chat and one embedding request, each retried once), so check before each request if that grows.
        run.used_llm_calls = min(run.used_llm_calls + taken.requests, run.max_llm_calls)
        if taken.fell_back:
            # What the console counts as a fallback.
            run.model_config = {**(run.model_config or {}), "model_fell_back": True}

    def _fail_run(self, run: AgentRun, error: Exception, *, replay: dict | None = None) -> AgentRun:
        current = self.run_lifecycle.repository.get(run.id) or run
        if AgentRunStatus(current.status) in {
            AgentRunStatus.NEEDS_CLARIFICATION,
            AgentRunStatus.READY_FOR_CONFIRMATION,
            AgentRunStatus.PREVIEW_READY,
            AgentRunStatus.COMMITTED,
            AgentRunStatus.DEGRADED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            return current
        self._record_model_calls(current)
        if replay is not None:
            current = self.run_lifecycle.checkpoint(
                current, stage="turn_failed", status="failed", state_payload={"replay": replay}
            )
        return self.run_lifecycle.transition(
            current,
            AgentRunStatus.FAILED,
            termination_reason_code="UNHANDLED_ERROR",
            error_code=type(error).__name__,
        )

    def _to_response(self, agent_session: AgentSession) -> AgentSessionResponse:
        pending_replan = None
        if agent_session.plan_id is not None and agent_session.pending_event_id is not None:
            pending_replan = self.replanning_service.get_event(
                plan_id=agent_session.plan_id,
                event_id=agent_session.pending_event_id,
            )
        latest_run = (
            self.run_lifecycle.repository.get(agent_session.latest_run_id)
            if agent_session.latest_run_id is not None
            else None
        )
        return AgentSessionResponse(
            id=agent_session.id,
            status=agent_session.status,
            parser_provider=agent_session.parser_provider,
            constraints=AgentConstraintState.model_validate(agent_session.constraints),
            missing_fields=list(agent_session.missing_fields),
            clarification_questions=list(agent_session.clarification_questions),
            messages=[
                AgentMessageResponse(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at,
                )
                for message in agent_session.messages
            ],
            plan_id=agent_session.plan_id,
            replan_draft=AgentReplanDraft.model_validate(agent_session.replan_draft or {}),
            pending_replan=pending_replan,
            context_version=agent_session.context_version,
            last_scope_decision=(
                ScopeDecision.model_validate(agent_session.last_scope_decision)
                if agent_session.last_scope_decision
                else None
            ),
            pending_interaction=(
                InteractionRequest.model_validate(agent_session.pending_interaction)
                if agent_session.pending_interaction
                else None
            ),
            latest_run=AgentRunResponse.model_validate(latest_run) if latest_run is not None else None,
            can_confirm=agent_session.status == "ready" and agent_session.plan_id is None,
            created_at=agent_session.created_at,
            updated_at=agent_session.updated_at,
        )
