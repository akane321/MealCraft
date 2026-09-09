from datetime import date
from uuid import uuid4

from app.agent.parser import ConstraintParser
from app.agent.replanning import AgentReplanInterpreter
from app.models.agent import AgentRun, AgentSession
from app.orchestration.contracts import (
    AgentRunStatus,
    InteractionAnswer,
    InteractionRequest,
    ScopeClass,
    ScopeDecision,
    ToolEffect,
    ToolRunStatus,
)
from app.orchestration.interactions import InteractionAnswerError, validate_interaction_answer
from app.orchestration.run_lifecycle import (
    AgentRunLifecycle,
    AgentRunLifecycleError,
    AgentRunNotFoundError,
    StartedRun,
)
from app.orchestration.runtime import BoundedAgentOrchestrator
from app.orchestration.scope_policy import ReferenceScopePolicy
from app.planning.weekly_planner import WeeklyPlanSelectionError
from app.repositories.agent import AgentSessionRepository
from app.repositories.agent_runs import AgentRunRepository
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
from app.schemas.meal_plan import MealPlanReplanPreviewRequest, WeeklyMealPlanRequest
from app.services.meal_plan import WeeklyMealPlanService
from app.services.replanning import (
    MealPlanReplanningService,
    MealPlanReplanValidationError,
)


class AgentSessionNotFoundError(LookupError):
    pass


class AgentSessionNotReadyError(ValueError):
    pass


class AgentSessionService:
    def __init__(
        self,
        *,
        repository: AgentSessionRepository,
        parser: ConstraintParser,
        meal_plan_service: WeeklyMealPlanService,
        replanning_service: MealPlanReplanningService,
        run_repository: AgentRunRepository,
        max_history_messages: int = 20,
    ) -> None:
        self.repository = repository
        self.parser = parser
        self.orchestrator = BoundedAgentOrchestrator(parser)
        self.scope_policy = ReferenceScopePolicy()
        self.meal_plan_service = meal_plan_service
        self.replanning_service = replanning_service
        self.replan_interpreter = AgentReplanInterpreter()
        self.run_lifecycle = AgentRunLifecycle(run_repository)
        self.max_history_messages = max_history_messages

    def create(self, message: str, *, idempotency_key: str | None = None) -> AgentSessionResponse:
        current = AgentConstraintState()
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
        self._finish_turn_run(run, result_status=result.status, scope_decision=result.scope_decision)
        return self._to_response(self.repository.get(agent_session.id) or agent_session)

    def get(self, session_id: int) -> AgentSessionResponse | None:
        agent_session = self.repository.get(session_id)
        return self._to_response(agent_session) if agent_session is not None else None

    def list_recent(self, *, limit: int) -> AgentSessionCollectionResponse:
        return AgentSessionCollectionResponse(
            items=[self._to_response(item) for item in self.repository.list_recent(limit=limit)]
        )

    def reply(
        self,
        session_id: int,
        message: str,
        *,
        idempotency_key: str | None = None,
    ) -> AgentSessionResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
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
                response = self._reply_to_planned(session_id, snapshot, message)
            except Exception as error:
                self._fail_run(run, error)
                raise
            self._finish_turn_run(
                run,
                result_status=("planned" if response.pending_replan is not None else "collecting"),
                scope_decision=response.last_scope_decision,
                has_preview=response.pending_replan is not None,
            )
            return self.get(session_id) or response
        acknowledged = list(agent_session.acknowledged_unknown_quantities)
        self.repository.end_read_transaction()

        try:
            result = self.orchestrator.process(
                message,
                current=snapshot.constraints,
                acknowledged_unknowns=acknowledged,
                history=snapshot.messages[-self.max_history_messages :],
                current_status=snapshot.status,
                current_missing_fields=snapshot.missing_fields,
                current_questions=snapshot.clarification_questions,
                context_version=snapshot.context_version,
                pending_interaction=snapshot.pending_interaction,
            )
        except Exception as error:
            self._fail_run(run, error)
            raise
        if not result.state_mutated:
            updated = self.repository.append_bounded_exchange(
                session_id,
                user_message=message,
                assistant_message=result.assistant_message,
                scope_decision=result.scope_decision,
            )
            if updated is None:
                raise AgentSessionNotFoundError
            self._finish_turn_run(run, result_status=result.status, scope_decision=result.scope_decision)
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
        self._finish_turn_run(run, result_status=result.status, scope_decision=result.scope_decision)
        return self._to_response(updated)

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
        message = self._interaction_value_as_message(snapshot.pending_interaction, values[0])
        return self.reply(session_id, message, idempotency_key=idempotency_key)

    @staticmethod
    def _interaction_value_as_message(request: InteractionRequest, value: object) -> str:
        if request.field_path == "household_size":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise AgentSessionNotReadyError("Household size must be a number.")
            if isinstance(value, str) and not value.strip().isdigit():
                return value.strip()
            return f"{int(value)} people"
        if request.field_path and request.field_path.endswith(".quantity"):
            return str(value)
        raise AgentSessionNotReadyError("This interaction field is not supported by the current runtime.")

    def _reply_to_planned(
        self,
        session_id: int,
        snapshot: AgentSessionResponse,
        message: str,
    ) -> AgentSessionResponse:
        if snapshot.plan_id is None:
            raise AgentSessionNotReadyError("Generate a plan before requesting a replanning event.")
        scope_decision = self.scope_policy.classify(message)
        if scope_decision.scope_class is ScopeClass.AMBIGUOUS and snapshot.clarification_questions:
            scope_decision = ScopeDecision(
                scope_class=ScopeClass.DOMAIN_ACTION,
                detected_intents=["replan_clarification_answer"],
                supported_segments=[message],
                should_mutate_state=True,
                reason_code="PENDING_REPLAN_CLARIFICATION_RESPONSE",
            )
        if not scope_decision.should_mutate_state:
            updated = self.repository.append_bounded_exchange(
                session_id,
                user_message=message,
                assistant_message=self.orchestrator.boundary_message(scope_decision),
                scope_decision=scope_decision,
            )
            if updated is None:
                raise AgentSessionNotFoundError
            return self._to_response(updated)

        plan = self.meal_plan_service.get(snapshot.plan_id)
        if plan is None:
            raise AgentSessionNotFoundError
        draft, questions = self.replan_interpreter.parse(
            message,
            plan=plan,
            current=snapshot.replan_draft,
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
                    ),
                )
            except (MealPlanReplanValidationError, WeeklyPlanSelectionError) as error:
                updated = self.repository.append_replan_exchange(
                    session_id,
                    user_message=message,
                    assistant_message=f"I could not prepare that change: {error}",
                    draft=AgentReplanDraft(),
                    clarification_questions=[],
                    pending_event_id=None,
                    scope_decision=scope_decision,
                )
            else:
                updated = self.repository.append_replan_exchange(
                    session_id,
                    user_message=message,
                    assistant_message=(
                        f"I prepared a preview: {preview.before_entry.recipe_title} → "
                        f"{preview.after_entry.recipe_title}. Review the nutrition and Shopping List deltas "
                        "before confirming."
                    ),
                    draft=draft,
                    clarification_questions=[],
                    pending_event_id=preview.id,
                    scope_decision=scope_decision,
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
        run = self.run_lifecycle.transition(started.run, AgentRunStatus.RUNNING)
        request = WeeklyMealPlanRequest(
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
        )
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
        updated = self.repository.mark_planned(session_id, plan_id=plan.id)
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
            evidence_references=[{"kind": "meal_plan", "reference": f"meal-plan:{plan.id}:revision:{plan.revision}"}],
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
        updated = self.repository.finish_replan(
            session_id,
            assistant_message=(
                f"I applied the change to plan #{plan_id}. The plan is now revision "
                f"{result.plan.revision}, and the Dashboard and Shopping List are updated."
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
            evidence_references=[{"kind": "meal_plan_event", "reference": f"meal-plan-event:{event_id}"}],
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
            session_id,
            assistant_message="I discarded that replanning request. The saved meal plan was not changed.",
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
        )

    def _finish_turn_run(
        self,
        run: AgentRun,
        *,
        result_status: str,
        scope_decision: ScopeDecision | None,
        has_preview: bool = False,
    ) -> AgentRun:
        scope_payload = scope_decision.model_dump(mode="json") if scope_decision is not None else None
        run.scope_decision = scope_payload
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
            },
        )
        if scope_decision is not None and not scope_decision.should_mutate_state:
            return self.run_lifecycle.transition(
                run,
                AgentRunStatus.DEGRADED,
                termination_reason_code=f"SCOPE_{scope_decision.scope_class.value.upper()}",
            )
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

    def _fail_run(self, run: AgentRun, error: Exception) -> AgentRun:
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
