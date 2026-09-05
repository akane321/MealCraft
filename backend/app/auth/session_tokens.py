from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

SESSION_TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedSessionToken:
    """Return the raw token once and persist only its SHA-256 digest."""

    raw_token: str
    token_hash: str


def hash_session_token(raw_token: str) -> str:
    if not raw_token:
        raise ValueError("session token cannot be empty")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_session_token() -> IssuedSessionToken:
    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    return IssuedSessionToken(raw_token=raw_token, token_hash=hash_session_token(raw_token))


def session_token_matches(raw_token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_session_token(raw_token), expected_hash)
