from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.passwords import Argon2PasswordAdapter
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.platform import PlatformRepository
from app.schemas.platform import (
    AccountLoginRequest,
    AccountPublic,
    AccountRegistrationRequest,
    AuthenticationResponse,
    AuthSessionCollectionResponse,
    AuthSessionPublic,
    CurrentActor,
)
from app.services.authentication import (
    AccountUnavailableError,
    AuthenticationRequiredError,
    AuthenticationService,
    AuthSessionNotFoundError,
    CsrfValidationError,
    CurrentAuthentication,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    IssuedAuthentication,
)

router = APIRouter(prefix="/auth", tags=["authentication"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_password_adapter() -> Argon2PasswordAdapter:
    return Argon2PasswordAdapter()


PasswordAdapterDependency = Annotated[Argon2PasswordAdapter, Depends(get_password_adapter)]


def get_authentication_service(
    database: DatabaseDependency,
    settings: SettingsDependency,
    password_adapter: PasswordAdapterDependency,
) -> AuthenticationService:
    return AuthenticationService(
        repository=PlatformRepository(database),
        password_adapter=password_adapter,
        session_ttl=timedelta(hours=settings.auth_session_ttl_hours),
        last_seen_interval=timedelta(seconds=settings.auth_last_seen_interval_seconds),
        max_login_failures=settings.auth_login_max_failures,
        login_lock_duration=timedelta(minutes=settings.auth_login_lock_minutes),
    )


AuthenticationServiceDependency = Annotated[AuthenticationService, Depends(get_authentication_service)]


def require_current_authentication(
    request: Request,
    service: AuthenticationServiceDependency,
    settings: SettingsDependency,
) -> CurrentAuthentication:
    try:
        return service.authenticate(request.cookies.get(settings.auth_cookie_name))
    except AuthenticationRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Session"},
        ) from error


CurrentAuthenticationDependency = Annotated[CurrentAuthentication, Depends(require_current_authentication)]


@router.post("/register", response_model=AuthenticationResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: AccountRegistrationRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
    settings: SettingsDependency,
) -> AuthenticationResponse:
    try:
        issued = service.register(payload, user_agent=request.headers.get("user-agent"))
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    _set_authentication_cookies(response, issued=issued, settings=settings)
    return _authentication_response(issued)


@router.post("/login", response_model=AuthenticationResponse)
def login(
    payload: AccountLoginRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
    settings: SettingsDependency,
) -> AuthenticationResponse:
    try:
        issued = service.login(payload, user_agent=request.headers.get("user-agent"))
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password") from error
    except AccountUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    _set_authentication_cookies(response, issued=issued, settings=settings)
    return _authentication_response(issued)


@router.get("/me", response_model=CurrentActor)
def me(current: CurrentAuthenticationDependency) -> CurrentActor:
    return _current_actor(current)


@router.get("/sessions", response_model=AuthSessionCollectionResponse)
def list_sessions(
    current: CurrentAuthenticationDependency,
    service: AuthenticationServiceDependency,
) -> AuthSessionCollectionResponse:
    return AuthSessionCollectionResponse(
        items=[AuthSessionPublic.model_validate(item) for item in service.list_sessions(current)]
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current: CurrentAuthenticationDependency,
    service: AuthenticationServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    _require_csrf(service, current, csrf_token)
    service.logout(current)
    _clear_authentication_cookies(response, settings=settings)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: int,
    response: Response,
    current: CurrentAuthenticationDependency,
    service: AuthenticationServiceDependency,
    settings: SettingsDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    _require_csrf(service, current, csrf_token)
    try:
        revoked_current = service.revoke_session(current, session_id=session_id)
    except AuthSessionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found") from error
    if revoked_current:
        _clear_authentication_cookies(response, settings=settings)


def _require_csrf(
    service: AuthenticationService,
    current: CurrentAuthentication,
    csrf_token: str | None,
) -> None:
    try:
        service.require_csrf(current, csrf_token)
    except CsrfValidationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed") from error


def _authentication_response(issued: IssuedAuthentication) -> AuthenticationResponse:
    current = CurrentAuthentication(
        user=issued.user,
        auth_session=issued.auth_session,
        active_membership=issued.active_membership,
    )
    return AuthenticationResponse(
        actor=_current_actor(current),
        session=AuthSessionPublic.model_validate(issued.auth_session),
        csrf_token=issued.raw_csrf_token,
    )


def _current_actor(current: CurrentAuthentication) -> CurrentActor:
    membership = current.active_membership
    return CurrentActor(
        user=AccountPublic.model_validate(current.user),
        active_household_id=membership.household_id if membership is not None else None,
        household_role=membership.role if membership is not None else None,
    )


def _set_authentication_cookies(
    response: Response,
    *,
    issued: IssuedAuthentication,
    settings: Settings,
) -> None:
    max_age = settings.auth_session_ttl_hours * 60 * 60
    cookie_options = {
        "max_age": max_age,
        "path": "/",
        "secure": settings.effective_auth_cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(
        settings.auth_cookie_name,
        issued.raw_session_token,
        httponly=True,
        **cookie_options,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        issued.raw_csrf_token,
        httponly=False,
        **cookie_options,
    )


def _clear_authentication_cookies(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.auth_csrf_cookie_name, path="/")
