import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db_session
from app.main import app


@pytest.fixture
def system_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_database() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_health_endpoint_returns_ok(system_client: TestClient) -> None:
    response = system_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MealCraft",
        "database": "connected",
    }


def test_info_endpoint_returns_application_metadata(system_client: TestClient) -> None:
    response = system_client.get("/api/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "MealCraft",
        "version": "0.1.0",
        "environment": "development",
    }


BACKEND = Path(__file__).resolve().parents[1]


def _python(script: str, **env: str) -> str:
    """Runs a script in a fresh interpreter from the backend directory, as the container does."""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_tests_do_not_inherit_the_containers_parser_model_or_keys() -> None:
    """`docker compose exec backend ... pytest` runs with the container's environment, which selects the
    OpenAI parser and holds the key. The test configuration drops those before any setting is read, and a
    test can still set one on purpose."""
    script = """
import os
import tests.conftest
from app.core.config import Settings
settings = Settings()
os.environ["OPENAI_MODEL"] = "set-by-a-test"
print(settings.agent_parser_provider, settings.openai_api_key, settings.admin_accounts or "-", Settings().openai_model)
"""
    container = {
        "AGENT_PARSER_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-from-the-container",
        "openai_model": "gpt-from-the-container",
        "ADMIN_ACCOUNTS": "a@example.test:secret:A",
    }
    assert _python(script, **container).split() == ["fixture", "None", "-", "set-by-a-test"]


def test_start_up_loads_the_openai_library_before_the_first_request() -> None:
    """The first swap after a start took over ten seconds: the OpenAI library loads its API modules on first
    use. With a key configured, start-up now loads them in the background, without sending a request."""
    script = """
import sys, threading
from fastapi.testclient import TestClient
from app.main import app
before = "openai.resources.embeddings" in sys.modules
with TestClient(app):
    for thread in threading.enumerate():
        if thread.name == "warm-openai":
            thread.join(120)
print(before, "openai.resources.embeddings" in sys.modules)
"""
    unroutable = {"OPENAI_API_KEY": "sk-test-not-used", "OPENAI_BASE_URL": "http://openai.invalid/v1"}
    assert _python(script, **unroutable).split() == ["False", "True"]
