from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.auth.passwords import Argon2PasswordAdapter
from app.auth.session_tokens import hash_session_token, issue_csrf_token, issue_session_token, session_token_matches
from app.models.platform import AuthSession, HouseholdMembership, User
from app.repositories.platform import PlatformRepository
from app.schemas.platform import AccountLoginRequest, AccountRegistrationRequest


class AuthenticationError(RuntimeError):
    pass


class EmailAlreadyRegisteredError(AuthenticationError):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class AccountUnavailableError(AuthenticationError):
    pass


class AuthenticationRequiredError(AuthenticationError):
    pass


class CsrfValidationError(AuthenticationError):
    pass


class AuthSessionNotFoundError(AuthenticationError):
    pass


@dataclass(frozen=True)
class IssuedAuthentication:
    user: User
    auth_session: AuthSession
    raw_session_token: str
    raw_csrf_token: str
    active_membership: HouseholdMembership | None


@dataclass(frozen=True)
class CurrentAuthentication:
    user: User
    auth_session: AuthSession
    active_membership: HouseholdMembership | None


class AuthenticationService:
    """Account and opaque-session lifecycle without HTTP/cookie concerns."""

    def __init__(
        self,
        *,
        repository: PlatformRepository,
        password_adapter: Argon2PasswordAdapter,
        session_ttl: timedelta,
        last_seen_interval: timedelta,
        max_login_failures: int,
        login_lock_duration: timedelta,
    ) -> None:
        if session_ttl <= timedelta(0):
            raise ValueError("session_ttl must be positive")
        if last_seen_interval < timedelta(0):
            raise ValueError("last_seen_interval cannot be negative")
        if max_login_failures < 1:
            raise ValueError("max_login_failures must be positive")
        if login_lock_duration <= timedelta(0):
            raise ValueError("login_lock_duration must be positive")
        self.repository = repository
        self.password_adapter = password_adapter
        self.session_ttl = session_ttl
        self.last_seen_interval = last_seen_interval
        self.max_login_failures = max_login_failures
        self.login_lock_duration = login_lock_duration

    def register(
        self,
        payload: AccountRegistrationRequest,
        *,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> IssuedAuthentication:
        if self.repository.get_user_by_email(payload.email) is not None:
            raise EmailAlreadyRegisteredError("An account with this email already exists")

        password_hash = self.password_adapter.hash_password(payload.password.get_secret_value())
        household_name = f"{payload.display_name} Household"[:120]
        try:
            user, _ = self.repository.create_account_with_household(
                normalized_email=payload.email,
                display_name=payload.display_name,
                password_hash=password_hash,
                household_name=household_name,
                locale=payload.locale,
                timezone=payload.timezone,
            )
        except IntegrityError as error:
            self.repository.session.rollback()
            raise EmailAlreadyRegisteredError("An account with this email already exists") from error
        return self._issue_session(user=user, user_agent=user_agent, now=now)

    def login(
        self,
        payload: AccountLoginRequest,
        *,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> IssuedAuthentication:
        moment = now or datetime.now(UTC)
        user = self.repository.get_user_by_email(payload.email)
        credential = user.credential if user is not None else None
        encoded_hash = credential.password_hash if credential is not None else None
        verification = self.password_adapter.verify_password(encoded_hash, payload.password.get_secret_value())

        if credential is not None and self._is_locked(credential.locked_until, moment):
            raise InvalidCredentialsError("Invalid email or password")
        if not verification.valid or user is None or credential is None:
            if credential is not None:
                self.repository.record_failed_login(
                    credential,
                    now=moment,
                    max_failures=self.max_login_failures,
                    lock_duration=self.login_lock_duration,
                )
            raise InvalidCredentialsError("Invalid email or password")
        if user.status != "active":
            raise AccountUnavailableError("Account is not available")

        self.repository.record_successful_login(
            user,
            now=moment,
            upgraded_password_hash=verification.upgraded_hash,
        )
        return self._issue_session(user=user, user_agent=user_agent, now=moment)

    def authenticate(
        self,
        raw_session_token: str | None,
        *,
        now: datetime | None = None,
    ) -> CurrentAuthentication:
        if not raw_session_token:
            raise AuthenticationRequiredError("Authentication required")
        moment = now or datetime.now(UTC)
        auth_session = self.repository.resolve_auth_session(hash_session_token(raw_session_token), now=moment)
        if auth_session is None:
            raise AuthenticationRequiredError("Authentication required")
        if auth_session.user.status != "active":
            self.repository.revoke_auth_session(auth_session.id, revoked_at=moment)
            raise AuthenticationRequiredError("Authentication required")

        self.repository.touch_auth_session(
            auth_session,
            seen_at=moment,
            minimum_interval=self.last_seen_interval,
        )
        membership = self._active_membership(auth_session.user)
        return CurrentAuthentication(
            user=auth_session.user,
            auth_session=auth_session,
            active_membership=membership,
        )

    def require_csrf(self, current: CurrentAuthentication, raw_csrf_token: str | None) -> None:
        expected_hash = current.auth_session.csrf_token_hash
        if not raw_csrf_token or not expected_hash or not session_token_matches(raw_csrf_token, expected_hash):
            raise CsrfValidationError("CSRF validation failed")

    def logout(self, current: CurrentAuthentication, *, now: datetime | None = None) -> None:
        self.repository.revoke_auth_session(current.auth_session.id, revoked_at=now or datetime.now(UTC))

    def list_sessions(
        self,
        current: CurrentAuthentication,
        *,
        now: datetime | None = None,
    ) -> list[AuthSession]:
        return self.repository.list_active_auth_sessions(user_id=current.user.id, now=now)

    def revoke_session(
        self,
        current: CurrentAuthentication,
        *,
        session_id: int,
        now: datetime | None = None,
    ) -> bool:
        revoked = self.repository.revoke_auth_session_for_user(
            session_id=session_id,
            user_id=current.user.id,
            revoked_at=now or datetime.now(UTC),
        )
        if not revoked:
            raise AuthSessionNotFoundError("Session not found")
        return session_id == current.auth_session.id

    def _issue_session(
        self,
        *,
        user: User,
        user_agent: str | None,
        now: datetime | None,
    ) -> IssuedAuthentication:
        moment = now or datetime.now(UTC)
        session_token = issue_session_token()
        csrf_token = issue_csrf_token()
        auth_session = self.repository.create_auth_session(
            user_id=user.id,
            token_hash=session_token.token_hash,
            csrf_token_hash=csrf_token.token_hash,
            expires_at=moment + self.session_ttl,
            user_agent=self._normalize_user_agent(user_agent),
        )
        return IssuedAuthentication(
            user=user,
            auth_session=auth_session,
            raw_session_token=session_token.raw_token,
            raw_csrf_token=csrf_token.raw_token,
            active_membership=self.repository.get_first_active_membership(user_id=user.id),
        )

    @staticmethod
    def _normalize_user_agent(user_agent: str | None) -> str | None:
        if user_agent is None:
            return None
        normalized = user_agent.strip()
        return normalized[:512] or None

    @staticmethod
    def _is_locked(locked_until: datetime | None, now: datetime) -> bool:
        if locked_until is None:
            return False
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        return locked_until > now

    @staticmethod
    def _active_membership(user: User) -> HouseholdMembership | None:
        active = [membership for membership in user.household_memberships if membership.status == "active"]
        if not active:
            return None
        return min(active, key=lambda membership: (membership.joined_at, membership.household_id))
