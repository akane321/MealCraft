from __future__ import annotations

import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import get_password_adapter
from app.api.routes.operations_data_quality import get_data_quality_service
from app.auth.authorization import SystemRole
from app.auth.passwords import Argon2PasswordAdapter, Argon2PasswordPolicy
from app.core.config import Settings, get_settings
from app.core.paths import repository_root
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.platform import User
from app.services.ops_data_quality import DataQualityService

FIXTURE_DIRECTORY = repository_root() / "data-engineering" / "data" / "fixtures" / "ops"


def _release_directory(target: Path) -> Path:
    target.mkdir()
    shutil.copyfile(FIXTURE_DIRECTORY / "quality_summary.sample.json", target / "quality_summary.json")
    shutil.copyfile(FIXTURE_DIRECTORY / "dropped.sample.jsonl", target / "dropped.jsonl")
    summary = json.loads((target / "quality_summary.json").read_text(encoding="utf-8"))
    (target / "release_manifest.json").write_text(
        json.dumps(
            {
                "release_version": summary["release_version"],
                "schema_version": "mealcraft.recipe.v2",
                "created_at": summary["created_at"],
            }
        ),
        encoding="utf-8",
    )
    return target


@pytest.fixture
def data_quality_client(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker, Path], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    database_factory = sessionmaker(bind=engine, expire_on_commit=False)
    release_directory = _release_directory(tmp_path / "release")
    test_settings = Settings(
        app_name="MealCraft Test",
        app_version="9.9.9",
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
    app.dependency_overrides[get_data_quality_service] = lambda: DataQualityService(release_directory, "v2")
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "email": "quality@example.test",
                "display_name": "Quality Tester",
                "password": "correct-horse-battery-staple",
            },
        )
        assert response.status_code == 201
        yield client, database_factory, release_directory
    app.dependency_overrides.clear()
    engine.dispose()


def _set_system_role(database_factory: sessionmaker, role: SystemRole) -> None:
    with database_factory() as database:
        user = database.scalars(select(User)).one()
        user.system_role = role.value
        database.commit()


def test_summary_reads_the_real_pipeline_fixture(tmp_path: Path) -> None:
    release_directory = _release_directory(tmp_path / "release")

    result = DataQualityService(release_directory, "v2").summary()

    assert result.status == "available"
    assert result.release_version == "v2"
    assert result.schema_version == "mealcraft.recipe.v2"
    assert result.coverage is not None
    assert result.coverage.released_recipes == 12
    assert result.coverage.released_ingredients == 29
    assert result.by_cuisine == {
        "middle_eastern": 3,
        "american": 3,
        "greek": 2,
        "japanese": 1,
        "indian": 1,
        "french": 1,
        "latin_american": 1,
    }
    assert result.estimated_share is not None
    assert result.estimated_share.model_dump() == {
        "servings": 0.75,
        "times": 0.5,
        "ingredient_amounts": 0.0227,
    }
    assert result.nutrition is not None
    assert result.nutrition.model_dump() == {
        "complete_recipes": 12,
        "total_recipes": 12,
        "median_energy_kcal": 167.9,
    }
    assert {artifact.name for artifact in result.artifacts} == {"quality_summary.json", "release_manifest.json"}
    assert all(len(artifact.sha256) == 64 for artifact in result.artifacts)
    assert str(tmp_path) not in result.model_dump_json()


def test_registered_current_release_is_readable() -> None:
    service = DataQualityService.current()

    summary = service.summary()
    dropped = service.dropped(offset=0, limit=1, reason=None)

    assert summary.status == "available"
    assert summary.release_version == "v2.1"
    assert summary.coverage is not None
    assert summary.coverage.released_recipes == 8968
    assert summary.coverage.released_ingredients == 701
    assert dropped.status == "available"
    assert dropped.total == 292
    assert len(dropped.items) == 1


@pytest.mark.parametrize("failure", ["missing", "invalid_json", "invalid_contract"])
def test_summary_reports_degraded_without_inventing_zeroes(tmp_path: Path, failure: str) -> None:
    release_directory = _release_directory(tmp_path / "release")
    summary_path = release_directory / "quality_summary.json"
    if failure == "missing":
        summary_path.unlink()
    elif failure == "invalid_json":
        summary_path.write_text("{", encoding="utf-8")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        del summary["coverage"]
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = DataQualityService(release_directory, "v2").summary()

    assert result.status == "degraded"
    assert result.coverage is None
    assert result.estimated_share is None
    assert result.nutrition is None
    assert result.dropped_by_reason is None
    assert {issue.code for issue in result.issues} >= {failure}
    assert str(tmp_path) not in result.model_dump_json()


def test_summary_marks_a_release_mismatch_but_keeps_valid_metrics(tmp_path: Path) -> None:
    release_directory = _release_directory(tmp_path / "release")
    summary_path = release_directory / "quality_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["release_version"] = "unexpected"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = DataQualityService(release_directory, "v2").summary()

    assert result.status == "degraded"
    assert result.coverage is not None
    assert result.coverage.released_recipes == 12
    assert {issue.code for issue in result.issues} == {"release_mismatch"}


def test_dropped_records_are_paged_and_unknown_reasons_are_data(tmp_path: Path) -> None:
    release_directory = _release_directory(tmp_path / "release")
    (release_directory / "dropped.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"candidate_id": "one", "title": "One", "reason": "future reason"}),
                json.dumps({"candidate_id": "two", "title": "Two", "reason": "known reason"}),
                "{",
                json.dumps({"candidate_id": "missing-title", "reason": "known reason"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    service = DataQualityService(release_directory, "v2")

    first = service.dropped(offset=0, limit=1, reason=None)
    unknown = service.dropped(offset=0, limit=20, reason="future reason")

    assert first.status == "degraded"
    assert first.total == 2
    assert [item.candidate_id for item in first.items] == ["one"]
    assert first.next_offset == 1
    assert first.skipped_records == 2
    assert {issue.code for issue in first.issues} == {"invalid_json", "invalid_record"}
    assert unknown.total == 1
    assert [item.reason for item in unknown.items] == ["future reason"]
    assert str(tmp_path) not in first.model_dump_json()


def test_empty_and_missing_dropped_artifacts_are_distinct(tmp_path: Path) -> None:
    release_directory = _release_directory(tmp_path / "release")
    dropped_path = release_directory / "dropped.jsonl"
    dropped_path.write_text("", encoding="utf-8")

    empty = DataQualityService(release_directory, "v2").dropped(offset=0, limit=50, reason=None)
    dropped_path.unlink()
    missing = DataQualityService(release_directory, "v2").dropped(offset=0, limit=50, reason=None)

    assert (empty.status, empty.total, empty.items) == ("available", 0, [])
    assert empty.artifact is not None
    assert (missing.status, missing.total, missing.items) == ("degraded", None, [])
    assert missing.artifact is None
    assert {issue.code for issue in missing.issues} == {"missing"}


@pytest.mark.parametrize("role", list(SystemRole))
@pytest.mark.parametrize("endpoint", ["/api/ops/data-quality", "/api/ops/data-quality/dropped?limit=1"])
def test_data_quality_endpoints_follow_the_central_operations_role_gate(
    data_quality_client,
    role: SystemRole,
    endpoint: str,
) -> None:
    client, database_factory, _release_directory = data_quality_client
    _set_system_role(database_factory, role)

    baseline = client.get("/api/ops/overview")
    response = client.get(endpoint)

    assert response.status_code == baseline.status_code
    if baseline.status_code == 404:
        assert response.json() == {"detail": "Not Found"}
    else:
        assert response.status_code == 200


@pytest.mark.parametrize("endpoint", ["/api/ops/data-quality", "/api/ops/data-quality/dropped"])
def test_data_quality_endpoints_require_authentication(data_quality_client, endpoint: str) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.get(endpoint)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_data_quality_api_exposes_no_path_parameter(data_quality_client) -> None:
    client, database_factory, release_directory = data_quality_client
    _set_system_role(database_factory, SystemRole.ADMIN)

    response = client.get("/api/ops/data-quality", params={"path": "C:/secrets"})
    operation = app.openapi()["paths"]["/api/ops/data-quality"]["get"]

    assert response.status_code == 200
    assert str(release_directory) not in response.text
    assert operation.get("parameters", []) == []


def test_data_quality_api_returns_summary_and_paged_dropped_records(data_quality_client) -> None:
    client, database_factory, release_directory = data_quality_client
    _set_system_role(database_factory, SystemRole.ADMIN)

    summary = client.get("/api/ops/data-quality")
    dropped = client.get("/api/ops/data-quality/dropped", params={"offset": 1, "limit": 2})

    assert summary.status_code == 200
    assert summary.json()["coverage"]["released_recipes"] == 12
    assert summary.json()["estimated_share"] == {
        "servings": 0.75,
        "times": 0.5,
        "ingredient_amounts": 0.0227,
    }
    assert dropped.status_code == 200
    assert dropped.json()["total"] == 50
    assert len(dropped.json()["items"]) == 2
    assert dropped.json()["next_offset"] == 3
    assert str(release_directory) not in summary.text + dropped.text


@pytest.mark.parametrize("params", [{"offset": -1}, {"limit": 0}, {"limit": 201}, {"reason": ""}])
def test_dropped_api_rejects_unbounded_or_empty_query_values(data_quality_client, params: dict) -> None:
    client, database_factory, _release_directory = data_quality_client
    _set_system_role(database_factory, SystemRole.ADMIN)

    response = client.get("/api/ops/data-quality/dropped", params=params)

    assert response.status_code == 422
