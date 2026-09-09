from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

    def create_account_with_household(
        self,
        *,
        normalized_email: str,
        display_name: str,
        password_hash: str,
        household_name: str,
        locale: str = "en-SG",
        timezone: str = "Asia/Singapore",
    ) -> tuple[User, Household]:
        """Create the first account, household and owner membership atomically."""

        user = User(
            normalized_email=normalized_email,
            display_name=display_name,
            locale=locale,
            timezone=timezone,
        )
        self.session.add(user)
        self.session.flush()
        self.session.add(UserCredential(user_id=user.id, password_hash=password_hash))

        household = Household(name=household_name, created_by_user_id=user.id)
        self.session.add(household)
        self.session.flush()
        self.session.add(
            HouseholdMembership(
                household_id=household.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        self.session.commit()
        return self.get_user(user.id) or user, household

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
        csrf_token_hash: str | None = None,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            csrf_token_hash=csrf_token_hash,
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
            .options(
                selectinload(AuthSession.user).selectinload(User.household_memberships),
                selectinload(AuthSession.user).selectinload(User.credential),
            )
        )
        return self.session.scalars(statement).unique().one_or_none()

    def touch_auth_session(
        self,
        auth_session: AuthSession,
        *,
        seen_at: datetime,
        minimum_interval: timedelta,
    ) -> None:
        last_seen_at = auth_session.last_seen_at
        if last_seen_at is not None and last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        if last_seen_at is not None and seen_at - last_seen_at < minimum_interval:
            return
        auth_session.last_seen_at = seen_at
        self.session.commit()

    def revoke_auth_session(self, session_id: int, *, revoked_at: datetime | None = None) -> bool:
        auth_session = self.session.get(AuthSession, session_id)
        if auth_session is None:
            return False
        auth_session.revoked_at = revoked_at or datetime.now(UTC)
        self.session.commit()
        return True

    def revoke_auth_session_for_user(
        self,
        *,
        session_id: int,
        user_id: int,
        revoked_at: datetime | None = None,
    ) -> bool:
        auth_session = self.session.scalars(
            select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user_id)
        ).one_or_none()
        if auth_session is None:
            return False
        if auth_session.revoked_at is None:
            auth_session.revoked_at = revoked_at or datetime.now(UTC)
            self.session.commit()
        return True

    def list_active_auth_sessions(self, *, user_id: int, now: datetime | None = None) -> list[AuthSession]:
        moment = now or datetime.now(UTC)
        statement = (
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > moment,
            )
            .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        )
        return list(self.session.scalars(statement))

    def record_failed_login(
        self,
        credential: UserCredential,
        *,
        now: datetime,
        max_failures: int,
        lock_duration: timedelta,
    ) -> None:
        locked_until = credential.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until is not None and locked_until <= now:
            credential.failed_login_count = 0
            credential.locked_until = None

        credential.failed_login_count += 1
        if credential.failed_login_count >= max_failures:
            credential.locked_until = now + lock_duration
        self.session.commit()

    def record_successful_login(
        self,
        user: User,
        *,
        now: datetime,
        upgraded_password_hash: str | None = None,
    ) -> None:
        if user.credential is None:
            raise LookupError("User credential is missing")
        user.credential.failed_login_count = 0
        user.credential.locked_until = None
        if upgraded_password_hash is not None:
            user.credential.password_hash = upgraded_password_hash
            user.credential.password_changed_at = now
        user.last_login_at = now
        self.session.commit()

    def get_first_active_membership(self, *, user_id: int) -> HouseholdMembership | None:
        statement = (
            select(HouseholdMembership)
            .where(
                HouseholdMembership.user_id == user_id,
                HouseholdMembership.status == "active",
            )
            .order_by(HouseholdMembership.joined_at, HouseholdMembership.household_id)
            .limit(1)
        )
        return self.session.scalars(statement).one_or_none()

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
