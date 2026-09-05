from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.authorization import (
    HouseholdAction,
    HouseholdRole,
    OperationsAction,
    SystemRole,
    may_access_household,
    may_access_operations,
)
from app.auth.session_tokens import hash_session_token, issue_session_token, session_token_matches
from app.db.base import Base
from app.repositories.platform import PlatformRepository
from app.schemas.platform import AccountRegistrationRequest


def test_registration_contract_normalizes_email_and_hides_password() -> None:
    payload = AccountRegistrationRequest(
        email="  Alice@Example.Test ",
        display_name="Alice",
        password="correct-horse-battery-staple",
    )

    assert payload.email == "alice@example.test"
    assert "correct-horse" not in repr(payload)
    with pytest.raises(ValidationError, match="between 12 and 128"):
        AccountRegistrationRequest(email="short@example.test", display_name="Short", password="short")


def test_session_token_is_random_and_only_digest_is_persistable() -> None:
    first = issue_session_token()
    second = issue_session_token()

    assert first.raw_token != second.raw_token
    assert first.raw_token != first.token_hash
    assert len(first.token_hash) == 64
    assert hash_session_token(first.raw_token) == first.token_hash
    assert session_token_matches(first.raw_token, first.token_hash)
    assert not session_token_matches(second.raw_token, first.token_hash)


def test_household_and_operations_roles_are_independent() -> None:
    assert may_access_household(HouseholdRole.OWNER, HouseholdAction.MANAGE_MEMBERS)
    assert not may_access_household(HouseholdRole.VIEWER, HouseholdAction.CREATE_PLAN)
    assert may_access_operations(SystemRole.DATA_REVIEWER, OperationsAction.REVIEW_DATA)
    assert not may_access_operations(SystemRole.ORDINARY_USER, OperationsAction.REVIEW_DATA)


def test_repository_persists_revocable_session_and_household_membership() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        repository = PlatformRepository(database)
        user = repository.create_account(
            normalized_email="alice@example.test",
            display_name="Alice",
            password_hash="$argon2id$fixture-not-a-real-password-hash",
        )
        household = repository.create_household_for_owner(name="Alice Home", owner_user_id=user.id)
        token = issue_session_token()
        auth_session = repository.create_auth_session(
            user_id=user.id,
            token_hash=token.token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            user_agent="pytest",
        )

        assert repository.get_active_membership(household_id=household.id, user_id=user.id).role == "owner"
        assert repository.resolve_auth_session(token.token_hash) is not None
        assert repository.revoke_auth_session(auth_session.id)
        assert repository.resolve_auth_session(token.token_hash) is None

    engine.dispose()


def test_cross_household_lookup_requires_an_explicit_membership() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        repository = PlatformRepository(database)
        alice = repository.create_account(
            normalized_email="alice@example.test",
            display_name="Alice",
            password_hash="$argon2id$alice-fixture",
        )
        bob = repository.create_account(
            normalized_email="bob@example.test",
            display_name="Bob",
            password_hash="$argon2id$bob-fixture",
        )
        alice_home = repository.create_household_for_owner(name="Alice Home", owner_user_id=alice.id)

        assert repository.get_active_membership(household_id=alice_home.id, user_id=alice.id) is not None
        assert repository.get_active_membership(household_id=alice_home.id, user_id=bob.id) is None

    engine.dispose()
