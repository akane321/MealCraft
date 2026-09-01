from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.agent import AgentMessage, AgentSession
from app.schemas.agent import AgentConstraintState


class AgentSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        provider: str,
        user_message: str,
        assistant_message: str,
        constraints: AgentConstraintState,
        status: str,
        missing_fields: list[str],
        clarification_questions: list[str],
        acknowledged_unknowns: list[str],
    ) -> AgentSession:
        agent_session = AgentSession(
            parser_provider=provider,
            constraints=constraints.model_dump(mode="json"),
            status=status,
            missing_fields=missing_fields,
            clarification_questions=clarification_questions,
            acknowledged_unknown_quantities=acknowledged_unknowns,
            messages=[
                AgentMessage(role="user", content=user_message),
                AgentMessage(role="assistant", content=assistant_message),
            ],
        )
        self.session.add(agent_session)
        self.session.commit()
        return self.get(agent_session.id) or agent_session

    def get(self, session_id: int) -> AgentSession | None:
        statement = (
            select(AgentSession).where(AgentSession.id == session_id).options(selectinload(AgentSession.messages))
        )
        return self.session.scalars(statement).unique().one_or_none()

    def list_recent(self, *, limit: int) -> list[AgentSession]:
        statement = (
            select(AgentSession)
            .options(selectinload(AgentSession.messages))
            .order_by(AgentSession.updated_at.desc(), AgentSession.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement).unique().all())

    def append_exchange(
        self,
        session_id: int,
        *,
        user_message: str,
        assistant_message: str,
        constraints: AgentConstraintState,
        status: str,
        missing_fields: list[str],
        clarification_questions: list[str],
        acknowledged_unknowns: list[str],
    ) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.constraints = constraints.model_dump(mode="json")
        agent_session.status = status
        agent_session.missing_fields = missing_fields
        agent_session.clarification_questions = clarification_questions
        agent_session.acknowledged_unknown_quantities = acknowledged_unknowns
        agent_session.messages.extend(
            [
                AgentMessage(role="user", content=user_message),
                AgentMessage(role="assistant", content=assistant_message),
            ]
        )
        self.session.commit()
        return self.get(session_id)

    def mark_planned(self, session_id: int, *, plan_id: int) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.status = "planned"
        agent_session.plan_id = plan_id
        agent_session.clarification_questions = []
        agent_session.missing_fields = []
        agent_session.messages.append(
            AgentMessage(
                role="assistant",
                content=f"The seven-day plan is ready and saved as plan #{plan_id}.",
            )
        )
        self.session.commit()
        return self.get(session_id)

    def end_read_transaction(self) -> None:
        self.session.rollback()
