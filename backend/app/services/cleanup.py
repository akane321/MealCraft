"""Deleting conversations and planned weeks, for a household (its own list) and for the console (any account).

A conversation goes with its messages and runs. A week goes with its days, events and groceries; a
conversation that planned it stays, without a week, and a week planned to replace it no longer points at it.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.agent import AgentSession
from app.models.meal_plan import MealPlan


def delete_sessions(database: Session, sessions: list[AgentSession]) -> int:
    for item in sessions:
        item.latest_run_id = None  # a session and its latest run point at each other
    database.flush()
    for item in sessions:
        database.delete(item)
    database.flush()
    return len(sessions)


def delete_plans(database: Session, plans: list[MealPlan]) -> int:
    if not plans:
        return 0
    ids = [plan.id for plan in plans]
    database.execute(
        update(AgentSession).where(AgentSession.plan_id.in_(ids)).values(plan_id=None, pending_event_id=None)
    )
    database.execute(update(MealPlan).where(MealPlan.replaces_plan_id.in_(ids)).values(replaces_plan_id=None))
    database.execute(update(MealPlan).where(MealPlan.id.in_(ids)).values(replaces_plan_id=None))
    for plan in plans:
        database.delete(plan)
    database.flush()
    return len(plans)
