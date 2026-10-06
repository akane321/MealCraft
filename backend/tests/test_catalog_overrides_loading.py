import logging
from contextlib import nullcontext

import pytest
from sqlalchemy.exc import OperationalError

import app.data.overrides as catalog_overrides
import app.main as main


class DatabaseStub:
    def __init__(self, bind: object | None = None):
        self.bind = bind or object()
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1

    def get_bind(self) -> object:
        return self.bind


@pytest.fixture(autouse=True)
def unloaded(monkeypatch):
    monkeypatch.setattr(catalog_overrides, "_loaded", False)
    monkeypatch.setattr(catalog_overrides, "_load_failed", False)


def test_transient_database_failure_is_retried_on_the_next_access(monkeypatch, caplog):
    database = DatabaseStub()
    attempts = 0

    def fail_then_load(_database):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("SELECT catalog_overrides", {}, ConnectionError("database unavailable"))
        catalog_overrides._loaded = True
        catalog_overrides._load_failed = False

    monkeypatch.setattr(catalog_overrides, "reload", fail_then_load)

    with caplog.at_level(logging.WARNING, logger="app.data.overrides"):
        assert catalog_overrides.ensure_loaded(database) is False
        assert catalog_overrides.ensure_loaded(database) is True

    assert attempts == 2
    assert database.rollbacks == 1
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None


def test_missing_pre_migration_table_uses_files_without_retrying_each_request(monkeypatch, caplog):
    database = DatabaseStub()
    attempts = 0

    def missing_table(_database):
        nonlocal attempts
        attempts += 1
        raise OperationalError(
            "SELECT catalog_overrides",
            {},
            RuntimeError("no such table: catalog_overrides"),
        )

    monkeypatch.setattr(catalog_overrides, "reload", missing_table)

    with caplog.at_level(logging.WARNING, logger="app.data.overrides"):
        assert catalog_overrides.ensure_loaded(database) is True
        assert catalog_overrides.ensure_loaded(database) is True

    assert attempts == 1
    assert database.rollbacks == 1
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is None


def test_startup_warmer_retries_overrides_before_loading_the_planning_pool(monkeypatch):
    database = DatabaseStub()
    attempts = iter((False, True))
    waits: list[float] = []
    warmed: list[object] = []

    class StopStub:
        def wait(self, seconds):
            waits.append(seconds)
            return False

    monkeypatch.setattr(main, "SessionLocal", lambda: nullcontext(database))
    monkeypatch.setattr(main, "ensure_loaded", lambda _database: next(attempts))
    monkeypatch.setattr(main, "keep_planning_pool_warm", lambda bind, _stop: warmed.append(bind))

    main.warm_planning_pool(StopStub())

    assert waits == [main.POOL_CHECK_SECONDS]
    assert warmed == [database.bind]
