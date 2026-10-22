from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

UserStatus = Literal["pending_verification", "active", "suspended", "deleted"]
SystemRoleValue = Literal["ordinary_user", "data_reviewer", "operator", "admin"]
HouseholdRoleValue = Literal["owner", "editor", "member", "viewer"]
MembershipStatus = Literal["invited", "active", "removed"]
OperationStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "degraded"]


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if " " in normalized or normalized.count("@") != 1:
        raise ValueError("email must contain one @ and no spaces")
    local, domain = normalized.split("@", maxsplit=1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("email format is incomplete")
    return normalized


# A username is what people type to sign in (2026-10-12, owner): letters (any script), digits, ".", "-", "_".
USERNAME = re.compile(r"[^\W][\w.-]{1,31}")


def normalize_username(value: str) -> str:
    normalized = value.strip().casefold()
    if not USERNAME.fullmatch(normalized):
        raise ValueError("username must be 2-32 letters, digits, '.', '-' or '_', starting with a letter or digit")
    return normalized


def username_from_email(email: str) -> str:
    """A username for an account that did not choose one: its email's local part, made valid."""
    local = re.sub(r"[^\w.-]", "-", email.split("@", 1)[0].casefold()).strip(".-_")[:28]
    return local if len(local) >= 2 else f"user-{local}".rstrip("-")


class AccountRegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    # Optional for the API (scripts and tests register by email alone): left out, it comes from the email.
    username: str | None = Field(default=None, max_length=32)
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr
    locale: str = Field(default="en-SG", min_length=2, max_length=20)
    timezone: str = Field(default="Asia/Singapore", min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_account_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("username")
    @classmethod
    def normalize_account_username(cls, value: str | None) -> str | None:
        return normalize_username(value) if value is not None else None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display_name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def require_reasonable_password_length(self) -> AccountRegistrationRequest:
        # Course project, never deployed: no strength rules, only a non-empty value of sane size.
        length = len(self.password.get_secret_value())
        if length < 1 or length > 128:
            raise ValueError("password must contain between 1 and 128 characters")
        return self


class AccountLoginRequest(BaseModel):
    """Sign in with a username (the default) or an email, and the password."""

    username: str | None = Field(default=None, min_length=1, max_length=32)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    password: SecretStr

    @field_validator("username")
    @classmethod
    def normalize_account_username(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_account_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value is not None else None

    @model_validator(mode="after")
    def require_one_identifier(self) -> AccountLoginRequest:
        if (self.username is None) == (self.email is None):
            raise ValueError("sign in with either a username or an email")
        return self


class AccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_email: str
    username: str | None = None
    display_name: str
    locale: str
    timezone: str
    status: UserStatus
    system_role: SystemRoleValue
    email_verified_at: datetime | None
    created_at: datetime


class AuthSessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    user_agent: str | None


class CurrentActor(BaseModel):
    user: AccountPublic
    active_household_id: int | None
    household_role: HouseholdRoleValue | None


class AuthenticationResponse(BaseModel):
    actor: CurrentActor
    session: AuthSessionPublic
    csrf_token: str


class AuthSessionCollectionResponse(BaseModel):
    items: list[AuthSessionPublic]
