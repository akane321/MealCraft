from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Dietary Planner MVP",
        "database": "connected",
    }


def test_info_endpoint_returns_application_metadata() -> None:
    response = client.get("/api/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Dietary Planner MVP",
        "version": "0.1.0",
        "environment": "development",
    }
