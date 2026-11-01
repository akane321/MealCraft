from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.agent import AgentMessage, AgentRun, AgentSession
from app.orchestration.contracts import InteractionRequest, ScopeDecision
from app.schemas.agent import AgentConstraintState, AgentReplanDraft
from app.services.cleanup import delete_sessions


class AgentSessionRepository:
    def __init__(self, session: Session, *, household_id: int) -> None:
        self.session = session
        self.household_id = household_id

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
        context_version: int,
        scope_decision: ScopeDecision,
        pending_interaction: InteractionRequest | None,
    ) -> AgentSession:
        agent_session = AgentSession(
            household_id=self.household_id,
            parser_provider=provider,
            constraints=constraints.model_dump(mode="json"),
            status=status,
            missing_fields=missing_fields,
            clarification_questions=clarification_questions,
            acknowledged_unknown_quantities=acknowledged_unknowns,
            context_version=context_version,
            last_scope_decision=scope_decision.model_dump(mode="json"),
            pending_interaction=(pending_interaction.model_dump(mode="json") if pending_interaction else None),
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
            select(AgentSession)
            .where(AgentSession.id == session_id, AgentSession.household_id == self.household_id)
            .options(selectinload(AgentSession.messages))
        )
        return self.session.scalars(statement).unique().one_or_none()

    def list_recent(self, *, limit: int) -> list[AgentSession]:
        statement = (
            select(AgentSession)
            .where(AgentSession.household_id == self.household_id)
            .options(selectinload(AgentSession.messages))
            # Pinned first, the latest pin on top; then the rest by when they last changed.
            .order_by(
                AgentSession.pinned_at.is_(None),
                AgentSession.pinned_at.desc(),
                AgentSession.updated_at.desc(),
                AgentSession.id.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).unique().all())

    def label(self, session_id: int, values: dict) -> AgentSession | None:
        """Rename or (un)pin; when it last changed stays as it was, so the list does not reorder by a rename."""
        statement = (
            update(AgentSession)
            .where(AgentSession.id == session_id, AgentSession.household_id == self.household_id)
            .values(**values, updated_at=AgentSession.updated_at)
        )
        if self.session.execute(statement).rowcount == 0:
            return None
        self.session.commit()
        self.session.expire_all()
        return self.get(session_id)

    def delete(self, session_id: int) -> bool:
        agent_session = self.get(session_id)
        if agent_session is None:
            return False
        delete_sessions(self.session, [agent_session])
        self.session.commit()
        return True

    def replace_preferences(self, session_id, *, expected_version, constraints, run_id) -> AgentSession | None:
        other_work = select(AgentRun.id).where(
            AgentRun.agent_session_id == session_id,
            AgentRun.household_id == self.household_id,
            AgentRun.id != run_id,
            AgentRun.status.in_(("created", "running")),
        )
        changed = self.session.execute(
            update(AgentSession)
            .where(
                AgentSession.id == session_id,
                AgentSession.household_id == self.household_id,
                AgentSession.context_version == expected_version,
                AgentSession.status == "ready",
                AgentSession.plan_id.is_(None),
                ~other_work.exists(),
            )
            .values(constraints=constraints.model_dump(mode="json"), context_version=expected_version + 1)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount == 0:
            self.session.rollback()
            return None
        self.session.expire_all()
        agent_session = self.get(session_id)
        agent_session.messages.extend(
            [
                AgentMessage(role="user", content="Updated meal preferences using the confirmation card."),
                AgentMessage(role="assistant", content="Preferences updated. Review the details before planning."),
            ]
        )
        self.session.commit()
        return self.get(session_id)

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
        context_version: int,
        scope_decision: ScopeDecision,
        pending_interaction: InteractionRequest | None,
    ) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.constraints = constraints.model_dump(mode="json")
        agent_session.status = status
        agent_session.missing_fields = missing_fields
        agent_session.clarification_questions = clarification_questions
        agent_session.acknowledged_unknown_quantities = acknowledged_unknowns
        agent_session.context_version = context_version
        agent_session.last_scope_decision = scope_decision.model_dump(mode="json")
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        agent_session.messages.extend(
            [
                AgentMessage(role="user", content=user_message),
                AgentMessage(role="assistant", content=assistant_message),
            ]
        )
        self.session.commit()
        return self.get(session_id)

    def append_bounded_exchange(
        self,
        session_id: int,
        *,
        user_message: str,
        assistant_message: str,
        scope_decision: ScopeDecision,
        pending_interaction: InteractionRequest | None,
    ) -> AgentSession | None:
        """Persist an out-of-scope exchange without changing planning state; only the choices on offer change."""

        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.last_scope_decision = scope_decision.model_dump(mode="json")
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        agent_session.messages.extend(
            [
                AgentMessage(role="user", content=user_message),
                AgentMessage(role="assistant", content=assistant_message),
            ]
        )
        self.session.commit()
        return self.get(session_id)

    def mark_planned(
        self,
        session_id: int,
        *,
        plan_id: int,
        assistant_message: str,
        user_message: str | None = None,
        scope_decision: ScopeDecision | None = None,
        pending_interaction: InteractionRequest | None = None,
    ) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.status = "planned"
        agent_session.plan_id = plan_id
        agent_session.clarification_questions = []
        agent_session.missing_fields = []
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        self._reply(agent_session, assistant_message, user_message, scope_decision)
        self.session.commit()
        return self.get(session_id)

    def explain_unplanned(
        self,
        session_id: int,
        *,
        assistant_message: str,
        status: str,
        missing_fields: list[str],
        clarification_questions: list[str],
        pending_interaction: InteractionRequest | None,
        user_message: str | None = None,
        scope_decision: ScopeDecision | None = None,
    ) -> AgentSession | None:
        """A week the planner could not plan: why, in the conversation, and the session collecting again."""
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.status = status
        agent_session.missing_fields = missing_fields
        agent_session.clarification_questions = clarification_questions
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        self._reply(agent_session, assistant_message, user_message, scope_decision)
        self.session.commit()
        return self.get(session_id)

    def create_for_plan(self, *, provider: str, constraints: AgentConstraintState, plan_id: int) -> AgentSession:
        """An empty conversation that changes the household's week `plan_id`."""
        agent_session = AgentSession(
            household_id=self.household_id, parser_provider=provider, constraints=constraints.model_dump(mode="json")
        )
        self.session.add(agent_session)
        self.session.flush()
        return self.attach_plan(agent_session.id, plan_id=plan_id) or agent_session

    def attach_plan(
        self,
        session_id: int,
        *,
        plan_id: int,
        constraints: AgentConstraintState | None = None,
        pending_interaction: InteractionRequest | None = None,
    ) -> AgentSession | None:
        """The conversation becomes the one that changes `plan_id`, as if it had planned it; whatever it
        was still asking to plan a week of its own is dropped. `constraints`: the conversation's own, when the
        week was planned under changed ones (a halal week asked for in the chat)."""
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.status = "planned"
        agent_session.plan_id = plan_id
        agent_session.missing_fields = []
        agent_session.clarification_questions = []
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        if constraints is not None:
            agent_session.constraints = constraints.model_dump(mode="json")
        agent_session.replan_draft = {}
        agent_session.pending_event_id = None
        self.session.commit()
        return self.get(session_id)

    def append_replan_exchange(
        self,
        session_id: int,
        *,
        user_message: str,
        assistant_message: str,
        draft: AgentReplanDraft,
        clarification_questions: list[str],
        pending_event_id: int | None,
        scope_decision: ScopeDecision | None = None,
        pending_interaction: InteractionRequest | None = None,
    ) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.replan_draft = draft.model_dump(mode="json")
        agent_session.missing_fields = ["replan"] if clarification_questions else []
        agent_session.clarification_questions = clarification_questions[:1]
        agent_session.pending_event_id = pending_event_id
        # A new request about the week answers, or moves past, any question still open; the new
        # question may come with its own choices.
        agent_session.pending_interaction = pending_interaction.model_dump(mode="json") if pending_interaction else None
        if scope_decision is not None:
            agent_session.last_scope_decision = scope_decision.model_dump(mode="json")
        agent_session.messages.extend(
            [
                AgentMessage(role="user", content=user_message),
                AgentMessage(role="assistant", content=assistant_message),
            ]
        )
        self.session.commit()
        return self.get(session_id)

    def finish_replan(
        self,
        session_id: int,
        *,
        assistant_message: str,
        pending_interaction: dict | None = None,
        user_message: str | None = None,
        scope_decision: ScopeDecision | None = None,
    ) -> AgentSession | None:
        agent_session = self.get(session_id)
        if agent_session is None:
            return None
        agent_session.replan_draft = {}
        agent_session.pending_event_id = None
        agent_session.missing_fields = []
        agent_session.clarification_questions = []
        agent_session.pending_interaction = pending_interaction
        self._reply(agent_session, assistant_message, user_message, scope_decision)
        self.session.commit()
        return self.get(session_id)

    @staticmethod
    def _reply(
        agent_session: AgentSession,
        assistant_message: str,
        user_message: str | None,
        scope_decision: ScopeDecision | None,
    ) -> None:
        """The reply to a button, or to the household's words when they were typed (a confirmation, ADR-0098)."""
        if user_message is not None:
            agent_session.messages.append(AgentMessage(role="user", content=user_message))
        if scope_decision is not None:
            agent_session.last_scope_decision = scope_decision.model_dump(mode="json")
        agent_session.messages.append(AgentMessage(role="assistant", content=assistant_message))

    def end_read_transaction(self) -> None:
        self.session.rollback()
