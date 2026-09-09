from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import get_password_adapter
from app.auth.passwords import Argon2PasswordAdapter, Argon2PasswordPolicy
from app.auth.session_tokens import hash_session_token, issue_csrf_token, issue_session_token
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.platform import AuthSession, HouseholdMembership, User
from app.repositories.platform import PlatformRepository


@pytest.fixture
def auth_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    database_factory = sessionmaker(bind=engine, expire_on_commit=False)
    test_settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite://",
        auth_cookie_secure=False,
        auth_session_ttl_hours=24,
        auth_last_seen_interval_seconds=0,
        auth_login_max_failures=2,
        auth_login_lock_minutes=15,
    )
    fast_password_adapter = Argon2PasswordAdapter(
        Argon2PasswordPolicy(
            version="argon2id-test-v1",
            time_cost=1,
            memory_cost_kib=8_192,
            parallelism=1,
            hash_length=16,
            salt_length=16,
        )
    )

    def override_database() -> Generator[Session, None, None]:
        with database_factory() as database:
            yield database

    app.dependency_overrides[get_db_session] = override_database
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_password_adapter] = lambda: fast_password_adapter
    with TestClient(app) as client:
        yield client, database_factory
    app.dependency_overrides.clear()
    engine.dispose()


def _register(client: TestClient, *, email: str = "alice@example.test", name: str = "Alice"):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": name,
            "password": "correct-horse-battery-staple",
        },
        headers={"User-Agent": "MealCraft auth test"},
    )


def test_register_creates_account_household_and_digest_only_session(auth_client) -> None:
    client, database_factory = auth_client
    response = _register(client)

    assert response.status_code == 201
    payload = response.json()
    assert payload["actor"]["user"]["normalized_email"] == "alice@example.test"
    assert payload["actor"]["active_household_id"] is not None
    assert payload["actor"]["household_role"] == "owner"
    assert payload["session"]["user_agent"] == "MealCraft auth test"
    assert payload["csrf_token"] == client.cookies.get("mealcraft_csrf")

    raw_session_token = client.cookies.get("mealcraft_session")
    assert raw_session_token
    assert raw_session_token not in response.text
    assert "correct-horse" not in response.text

    with database_factory() as database:
        user = database.scalars(select(User)).one()
        auth_session = database.scalars(select(AuthSession)).one()
        membership = database.scalars(select(HouseholdMembership)).one()
        assert user.credential is not None
        assert user.credential.password_hash.startswith("$argon2id$")
        assert auth_session.token_hash == hash_session_token(raw_session_token)
        assert auth_session.token_hash != raw_session_token
        assert auth_session.csrf_token_hash == hash_session_token(payload["csrf_token"])
        assert membership.user_id == user.id
        assert membership.role == "owner"

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["display_name"] == "Alice"


def test_duplicate_registration_and_login_errors_are_bounded(auth_client) -> None:
    client, database_factory = auth_client
    assert _register(client).status_code == 201
    assert _register(client, name="Alice Duplicate").status_code == 409
    client.cookies.clear()

    unknown = client.post(
        "/api/auth/login",
        json={"email": "missing@example.test", "password": "incorrect-password"},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"email": "alice@example.test", "password": "incorrect-password"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Invalid email or password"}

    second_wrong = client.post(
        "/api/auth/login",
        json={"email": "alice@example.test", "password": "incorrect-password"},
    )
    locked_correct = client.post(
        "/api/auth/login",
        json={"email": "alice@example.test", "password": "correct-horse-battery-staple"},
    )
    assert second_wrong.status_code == 401
    assert locked_correct.status_code == 401
    with database_factory() as database:
        user = database.scalars(select(User)).one()
        assert user.credential is not None
        assert user.credential.locked_until is not None


def test_login_lists_devices_and_rejects_suspended_account(auth_client) -> None:
    client, database_factory = auth_client
    assert _register(client).status_code == 201
    first_session_id = client.get("/api/auth/sessions").json()["items"][0]["id"]
    client.cookies.clear()

    login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.test", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    sessions = client.get("/api/auth/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()["items"]) == 2
    assert first_session_id in {item["id"] for item in sessions.json()["items"]}

    client.cookies.clear()
    with database_factory() as database:
        user = database.scalars(select(User)).one()
        user.status = "suspended"
        database.commit()
    suspended = client.post(
        "/api/auth/login",
        json={"email": "alice@example.test", "password": "correct-horse-battery-staple"},
    )
    assert suspended.status_code == 403
    assert suspended.json() == {"detail": "Account is not available"}


def test_logout_requires_matching_csrf_and_revokes_session(auth_client) -> None:
    client, database_factory = auth_client
    registration = _register(client)
    csrf_token = registration.json()["csrf_token"]

    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    with database_factory() as database:
        auth_session = database.scalars(select(AuthSession)).one()
        assert auth_session.revoked_at is not None


def test_device_revoke_is_user_scoped_and_current_revoke_clears_cookie(auth_client) -> None:
    client, database_factory = auth_client
    registration = _register(client)
    alice_session_id = registration.json()["session"]["id"]
    alice_csrf = registration.json()["csrf_token"]

    with database_factory() as database:
        repository = PlatformRepository(database)
        bob = repository.create_account(
            normalized_email="bob@example.test",
            display_name="Bob",
            password_hash="$argon2id$fixture",
        )
        bob_session = issue_session_token()
        bob_csrf = issue_csrf_token()
        persisted_bob_session = repository.create_auth_session(
            user_id=bob.id,
            token_hash=bob_session.token_hash,
            csrf_token_hash=bob_csrf.token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        bob_session_id = persisted_bob_session.id

    foreign_revoke = client.delete(
        f"/api/auth/sessions/{bob_session_id}",
        headers={"X-CSRF-Token": alice_csrf},
    )
    assert foreign_revoke.status_code == 404
    assert client.get("/api/auth/me").status_code == 200

    current_revoke = client.delete(
        f"/api/auth/sessions/{alice_session_id}",
        headers={"X-CSRF-Token": alice_csrf},
    )
    assert current_revoke.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_password_adapter_upgrades_a_valid_older_policy_hash() -> None:
    old_adapter = Argon2PasswordAdapter(
        Argon2PasswordPolicy(
            version="old",
            time_cost=1,
            memory_cost_kib=8_192,
            parallelism=1,
            hash_length=16,
            salt_length=16,
        )
    )
    current_adapter = Argon2PasswordAdapter(
        Argon2PasswordPolicy(
            version="current",
            time_cost=2,
            memory_cost_kib=8_192,
            parallelism=1,
            hash_length=16,
            salt_length=16,
        )
    )
    encoded_hash = old_adapter.hash_password("correct-horse-battery-staple")

    result = current_adapter.verify_password(encoded_hash, "correct-horse-battery-staple")

    assert result.valid
    assert result.upgraded_hash is not None
    assert current_adapter.verify_password(result.upgraded_hash, "correct-horse-battery-staple").valid
