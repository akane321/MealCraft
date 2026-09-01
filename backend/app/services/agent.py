from datetime import date

from app.agent.parser import ConstraintParser
from app.agent.workflow import AgentConstraintWorkflow
from app.models.agent import AgentSession
from app.repositories.agent import AgentSessionRepository
from app.schemas.agent import (
    AgentConfirmationResponse,
    AgentConstraintState,
    AgentMessageResponse,
    AgentSessionCollectionResponse,
    AgentSessionResponse,
)
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.services.meal_plan import WeeklyMealPlanService


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
        max_history_messages: int = 20,
    ) -> None:
        self.repository = repository
        self.parser = parser
        self.workflow = AgentConstraintWorkflow(parser)
        self.meal_plan_service = meal_plan_service
        self.max_history_messages = max_history_messages

    def create(self, message: str) -> AgentSessionResponse:
        current = AgentConstraintState()
        result = self.workflow.run(
            message,
            current=current,
            acknowledged_unknowns=[],
            history=[],
        )
        agent_session = self.repository.create(
            provider=self.parser.provider,
            user_message=message,
            assistant_message=result["assistant_message"],
            constraints=AgentConstraintState.model_validate(result["merged_constraints"]),
            status=result["status"],
            missing_fields=result["missing_fields"],
            clarification_questions=result["clarification_questions"],
            acknowledged_unknowns=result["merged_acknowledged_unknowns"],
        )
        return self._to_response(agent_session)

    def get(self, session_id: int) -> AgentSessionResponse | None:
        agent_session = self.repository.get(session_id)
        return self._to_response(agent_session) if agent_session is not None else None

    def list_recent(self, *, limit: int) -> AgentSessionCollectionResponse:
        return AgentSessionCollectionResponse(
            items=[self._to_response(item) for item in self.repository.list_recent(limit=limit)]
        )

    def reply(self, session_id: int, message: str) -> AgentSessionResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        if snapshot.plan_id is not None:
            self.repository.end_read_transaction()
            raise AgentSessionNotReadyError("This session already produced a plan. Start a new session to revise it.")
        acknowledged = list(agent_session.acknowledged_unknown_quantities)
        self.repository.end_read_transaction()

        result = self.workflow.run(
            message,
            current=snapshot.constraints,
            acknowledged_unknowns=acknowledged,
            history=snapshot.messages[-self.max_history_messages :],
        )
        updated = self.repository.append_exchange(
            session_id,
            user_message=message,
            assistant_message=result["assistant_message"],
            constraints=AgentConstraintState.model_validate(result["merged_constraints"]),
            status=result["status"],
            missing_fields=result["missing_fields"],
            clarification_questions=result["clarification_questions"],
            acknowledged_unknowns=result["merged_acknowledged_unknowns"],
        )
        if updated is None:
            raise AgentSessionNotFoundError
        return self._to_response(updated)

    def confirm(self, session_id: int) -> AgentConfirmationResponse:
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise AgentSessionNotFoundError
        snapshot = self._to_response(agent_session)
        self.repository.end_read_transaction()
        if not snapshot.can_confirm:
            raise AgentSessionNotReadyError("Resolve the outstanding clarification before generating a plan.")

        constraints = snapshot.constraints
        plan = self.meal_plan_service.generate(
            WeeklyMealPlanRequest(
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
        )
        updated = self.repository.mark_planned(session_id, plan_id=plan.id)
        if updated is None:
            raise AgentSessionNotFoundError
        return AgentConfirmationResponse(session=self._to_response(updated), plan=plan)

    @staticmethod
    def _to_response(agent_session: AgentSession) -> AgentSessionResponse:
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
            can_confirm=agent_session.status == "ready" and agent_session.plan_id is None,
            created_at=agent_session.created_at,
            updated_at=agent_session.updated_at,
        )
