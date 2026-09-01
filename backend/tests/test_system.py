from collections.abc import Generator

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
