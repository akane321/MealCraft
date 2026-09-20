import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import Engine

from alembic import command
from app.core.config import get_settings
from tests.migrations.support import DATABASE_URL_ENV, PRE_TENANCY_REVISION, MigrationDatabase

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pre_tenancy.sql"


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")


def _load_fixture(engine: Engine) -> None:
    statements = [statement.strip() for statement in FIXTURE_PATH.read_text(encoding="utf-8").split(";")]
    with engine.begin() as connection:
        for statement in statements:
            if statement:
                connection.exec_driver_sql(statement)


def _database_name(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(sa.text("SELECT current_database()")).scalar_one()


@pytest.fixture
def migration_database() -> Iterator[MigrationDatabase]:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_URL_ENV} is required for PostgreSQL migration tests")

    engine = sa.create_engine(database_url, poolclass=sa.pool.NullPool)
    database_name = _database_name(engine)
    if not database_name.endswith("_migration_test"):
        engine.dispose()
        pytest.fail(
            f"Refusing to reset database {database_name!r}; migration test databases must end with '_migration_test'"
        )

    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    _reset_public_schema(engine)
    command.upgrade(alembic_config, PRE_TENANCY_REVISION)
    _load_fixture(engine)
    counts_before_upgrade = MigrationDatabase(engine, alembic_config, {}).counts()
    database = MigrationDatabase(
        engine=engine,
        alembic_config=alembic_config,
        counts_before_upgrade=counts_before_upgrade,
    )

    try:
        yield database
    finally:
        _reset_public_schema(engine)
        engine.dispose()
        get_settings.cache_clear()
