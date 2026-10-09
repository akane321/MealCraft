"""Old weeks remain identifiable outside the recent-plan window."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.meal_plan import MealPlan
from app.repositories.meal_plan import MealPlanRepository
from app.services.agent import AgentSessionNotReadyError, AgentSessionService
from app.services.replanning import MealPlanReplanConflictError, MealPlanReplanningService
from tests.test_plan_list_and_dashboard import service


def test_current_checks_all_plans_and_uses_id_when_timestamps_tie():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        made = datetime(2026, 10, 1)
        start = made.date()
        for _index in range(22):
            session.add(
                MealPlan(
                    household_id=1,
                    start_date=start,
                    end_date=start + timedelta(days=6),
                    household_size=2,
                    pricing_mode="fixture",
                    purchase_total_sgd=50,
                    constraints={},
                    created_at=made,
                )
            )
        session.commit()
        repository = MealPlanRepository(session, household_id=1)
        recent = repository.list_recent(limit=20)
        assert len(recent) == 20
        oldest = repository.get(1)
        assert oldest.id not in {item.id for item in recent}
        assert not repository.is_current(oldest)
        assert repository.is_current(recent[0])
        assert service(repository).get(oldest.id).current is False
        assert service(repository).get(recent[0].id).current is True


def test_replaced_week_cannot_apply_an_otherwise_valid_preview():
    plan = SimpleNamespace(revision=1)
    event = SimpleNamespace(status="previewed", base_revision=1)
    repository = SimpleNamespace(
        get=lambda plan_id: plan,
        get_event=lambda **kwargs: event,
        is_current=lambda candidate: False,
    )
    service = MealPlanReplanningService(
        repository=repository,
        recipe_repository=None,
        recommendation_service=None,
        grocery_aggregator=None,
    )
    with pytest.raises(MealPlanReplanConflictError, match="replaced"):
        service.confirm(plan_id=1, event_id=1)


def test_replaced_week_rejects_pending_interaction_before_processing_answer():
    agent = AgentSessionService.__new__(AgentSessionService)
    snapshot = SimpleNamespace(plan_id=1, pending_interaction=object())
    agent.repository = SimpleNamespace(get=lambda session_id: snapshot, end_read_transaction=lambda: None)
    agent._to_response = lambda stored: stored
    agent.meal_plan_service = SimpleNamespace(get=lambda plan_id: SimpleNamespace(current=False))
    with pytest.raises(AgentSessionNotReadyError, match="replaced"):
        agent.answer_interaction(1, None)
