"""Accounts for the operations console (ADR-0047 Users): view, edit and delete.

Conversations and plans belong to households; "an account's" conversations or plans are those of the
households it belongs to. Every change writes an audit row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.agent import AgentRun, AgentSession
from app.models.household import HouseholdProfile, HouseholdProfileVersion
from app.models.meal_plan import MealPlan
from app.models.platform import (
    AuditEvent,
    AuthSession,
    OperationRun,
    RuntimeSetting,
    User,
)
from app.schemas.operations import (
    OpsUserCollection,
    OpsUserDetail,
    OpsUserHousehold,
    OpsUserSummary,
    OpsUserUpdate,
)


class OpsUserNotFoundError(LookupError):
    pass


class OpsUserConflictError(ValueError):
    pass


class UsersService:
    def __init__(self, database: Session, *, actor_user_id: int) -> None:
        self.database = database
        self.actor_user_id = actor_user_id

    def list(self, *, query: str | None, offset: int, limit: int) -> OpsUserCollection:
        filters = []
        if query:
            pattern = f"%{query.strip().casefold()}%"
            filters.append(or_(User.normalized_email.like(pattern), func.lower(User.display_name).like(pattern)))
        total = self.database.scalar(select(func.count()).select_from(User).where(*filters)) or 0
        users = self.database.scalars(
            select(User).where(*filters).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
        )
        # ponytail: a few small queries per account on the page; one grouped query each if pages grow large.
        return OpsUserCollection(items=[self._summary(user) for user in users], total=total)

    def get(self, user_id: int) -> OpsUserDetail:
        user = self._user(user_id)
        summary = self._summary(user)
        households = [item.id for item in summary.households]
        sessions = self.database.scalars(
            select(AgentSession)
            .where(AgentSession.household_id.in_(households))
            .order_by(AgentSession.created_at.desc())
            .limit(10)
        )
        plans = self.database.scalars(
            select(MealPlan).where(MealPlan.household_id.in_(households)).order_by(MealPlan.created_at.desc()).limit(10)
        )
        return OpsUserDetail(
            **summary.model_dump(),
            recent_conversations=[
                {
                    "id": item.id,
                    "status": item.status,
                    "messages": len(item.messages),
                    "first_message": next((m.content for m in item.messages if m.role == "user"), None),
                    "created_at": item.created_at,
                }
                for item in sessions
            ],
            recent_plans=[
                {
                    "id": plan.id,
                    "start_date": plan.start_date,
                    "total_sgd": float(plan.purchase_total_sgd),
                    "household_size": plan.household_size,
                    "created_at": plan.created_at,
                }
                for plan in plans
            ],
        )

    def update(self, user_id: int, change: OpsUserUpdate) -> OpsUserDetail:
        user = self._user(user_id)
        before = {"display_name": user.display_name, "system_role": user.system_role}
        if change.system_role is not None and user.id == self.actor_user_id and change.system_role != "admin":
            raise OpsUserConflictError("You cannot remove your own console access.")
        if change.display_name is not None:
            user.display_name = change.display_name.strip()
        if change.system_role is not None:
            user.system_role = change.system_role
        after = {"display_name": user.display_name, "system_role": user.system_role}
        self._audit("user.updated", user.id, {"before": before, "after": after})
        self.database.commit()
        return self.get(user_id)

    def delete_conversations(self, user_id: int) -> int:
        households = self._household_ids(self._user(user_id))
        count = self._delete_sessions(households)
        self._audit("user.conversations_deleted", user_id, {"households": households, "deleted": count})
        self.database.commit()
        return count

    def delete_plans(self, user_id: int) -> int:
        households = self._household_ids(self._user(user_id))
        count = self._delete_plans(households)
        self._audit("user.plans_deleted", user_id, {"households": households, "deleted": count})
        self.database.commit()
        return count

    def delete(self, user_id: int) -> None:
        user = self._user(user_id)
        if user.id == self.actor_user_id:
            raise OpsUserConflictError("You cannot delete the account you are signed in with.")
        removed_households = []
        for membership in list(user.household_memberships):
            household = membership.household
            others = [item for item in household.memberships if item.user_id != user.id]
            if not others:
                # Nobody else uses this household, so it goes with the account.
                self._delete_sessions([household.id])
                self._delete_plans([household.id])
                for profile in self.database.scalars(
                    select(HouseholdProfile).where(HouseholdProfile.household_id == household.id)
                ):
                    self.database.delete(profile)
                removed_households.append(household.id)
                self.database.delete(household)
            elif household.created_by_user_id == user.id:
                household.created_by_user_id = others[0].user_id
        # Households reference their creator without an ORM relationship, so they must go first.
        self.database.flush()
        self.database.expire(user, ["household_memberships"])
        # SQLite does not enforce ON DELETE SET NULL here; clear the references the same way Postgres would.
        for model, column in (
            (AgentRun, AgentRun.actor_user_id),
            (OperationRun, OperationRun.triggered_by_user_id),
            (AuditEvent, AuditEvent.actor_user_id),
            (RuntimeSetting, RuntimeSetting.updated_by_user_id),
        ):
            self.database.execute(update(model).where(column == user.id).values({column.key: None}))
        self._audit(
            "user.deleted",
            user.id,
            {"email": user.normalized_email, "households_removed": removed_households},
        )
        self.database.delete(user)
        self.database.commit()

    # --- helpers ---

    def _user(self, user_id: int) -> User:
        user = self.database.get(User, user_id)
        if user is None:
            raise OpsUserNotFoundError
        return user

    @staticmethod
    def _household_ids(user: User) -> list[int]:
        return [item.household_id for item in user.household_memberships]

    def _summary(self, user: User) -> OpsUserSummary:
        households = []
        for membership in user.household_memberships:
            households.append(
                OpsUserHousehold(
                    id=membership.household_id,
                    name=membership.household.name,
                    role=membership.role,
                    members=len(membership.household.memberships),
                    profile=self._profile(membership.household_id),
                )
            )
        ids = [item.id for item in households]
        last_seen = self.database.scalar(
            select(func.max(AuthSession.last_seen_at)).where(AuthSession.user_id == user.id)
        )
        seen = [moment for moment in (last_seen, user.last_login_at) if moment is not None]
        return OpsUserSummary(
            id=user.id,
            email=user.normalized_email,
            display_name=user.display_name,
            system_role=user.system_role,
            status=user.status,
            households=households,
            conversations=self._count(AgentSession, ids),
            plans=self._count(MealPlan, ids),
            last_seen_at=max(seen, key=lambda moment: moment.replace(tzinfo=None)) if seen else None,
            created_at=user.created_at,
        )

    def _count(self, model, household_ids: list[int]) -> int:
        if not household_ids:
            return 0
        return (
            self.database.scalar(select(func.count()).select_from(model).where(model.household_id.in_(household_ids)))
            or 0
        )

    def _profile(self, household_id: int) -> dict[str, Any] | None:
        version = self.database.scalar(
            select(HouseholdProfileVersion)
            .join(HouseholdProfile, HouseholdProfile.id == HouseholdProfileVersion.profile_id)
            .where(
                HouseholdProfile.household_id == household_id,
                HouseholdProfileVersion.version == HouseholdProfile.current_version,
            )
        )
        if version is None:
            return None
        return {
            "people": version.planning_household_size,
            "weekly_budget_sgd": float(version.weekly_budget_sgd) if version.weekly_budget_sgd is not None else None,
            "max_cooking_minutes": version.max_cooking_time_minutes,
            "allergens": version.allergens,
            "diet": version.dietary_preferences,
            "pricing": version.pricing_mode,
        }

    def _delete_sessions(self, household_ids: list[int]) -> int:
        sessions = list(self.database.scalars(select(AgentSession).where(AgentSession.household_id.in_(household_ids))))
        for item in sessions:
            item.latest_run_id = None
        self.database.flush()
        for item in sessions:
            self.database.delete(item)
        self.database.flush()
        return len(sessions)

    def _delete_plans(self, household_ids: list[int]) -> int:
        plans = list(self.database.scalars(select(MealPlan).where(MealPlan.household_id.in_(household_ids))))
        if not plans:
            return 0
        ids = [plan.id for plan in plans]
        self.database.execute(
            update(AgentSession).where(AgentSession.plan_id.in_(ids)).values(plan_id=None, pending_event_id=None)
        )
        self.database.execute(update(MealPlan).where(MealPlan.id.in_(ids)).values(replaces_plan_id=None))
        for plan in plans:
            self.database.delete(plan)
        self.database.flush()
        return len(plans)

    def _audit(self, action: str, user_id: int, details: dict) -> None:
        self.database.add(
            AuditEvent(
                actor_user_id=self.actor_user_id,
                action=action,
                target_type="user",
                target_id=str(user_id),
                details=details,
            )
        )
