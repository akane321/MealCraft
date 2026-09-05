from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.platform import AuthSession, Household, HouseholdMembership, User, UserCredential


class PlatformRepository:
    """Low-level identity persistence; HTTP authentication remains teammate work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_account(
        self,
        *,
        normalized_email: str,
        display_name: str,
        password_hash: str,
        locale: str = "en-SG",
        timezone: str = "Asia/Singapore",
    ) -> User:
        user = User(
            normalized_email=normalized_email,
            display_name=display_name,
            locale=locale,
            timezone=timezone,
        )
        self.session.add(user)
        self.session.flush()
        self.session.add(UserCredential(user_id=user.id, password_hash=password_hash))
        self.session.commit()
        return self.get_user(user.id) or user

    def get_user(self, user_id: int) -> User | None:
        return self.session.scalars(
            select(User).where(User.id == user_id).options(selectinload(User.credential))
        ).one_or_none()

    def get_user_by_email(self, normalized_email: str) -> User | None:
        return self.session.scalars(
            select(User).where(User.normalized_email == normalized_email).options(selectinload(User.credential))
        ).one_or_none()

    def create_auth_session(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        self.session.add(auth_session)
        self.session.commit()
        self.session.refresh(auth_session)
        return auth_session

    def resolve_auth_session(self, token_hash: str, *, now: datetime | None = None) -> AuthSession | None:
        moment = now or datetime.now(UTC)
        statement = (
            select(AuthSession)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > moment,
            )
            .options(selectinload(AuthSession.user))
        )
        return self.session.scalars(statement).unique().one_or_none()

    def revoke_auth_session(self, session_id: int, *, revoked_at: datetime | None = None) -> bool:
        auth_session = self.session.get(AuthSession, session_id)
        if auth_session is None:
            return False
        auth_session.revoked_at = revoked_at or datetime.now(UTC)
        self.session.commit()
        return True

    def create_household_for_owner(self, *, name: str, owner_user_id: int) -> Household:
        household = Household(name=name, created_by_user_id=owner_user_id)
        self.session.add(household)
        self.session.flush()
        self.session.add(
            HouseholdMembership(
                household_id=household.id,
                user_id=owner_user_id,
                role="owner",
                status="active",
            )
        )
        self.session.commit()
        return household

    def get_active_membership(self, *, household_id: int, user_id: int) -> HouseholdMembership | None:
        statement = select(HouseholdMembership).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == user_id,
            HouseholdMembership.status == "active",
        )
        return self.session.scalars(statement).one_or_none()
