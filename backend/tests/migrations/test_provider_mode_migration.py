import sqlalchemy as sa

from tests.migrations.support import MigrationDatabase

HALAL = "20261031_0033"
WIDER = "20261102_0034"
TABLES = ("operation_runs", "agent_tool_executions")
LONGEST = "cold_storage,fairprice,fixture,manual,redmart"


def _lengths(database: MigrationDatabase) -> dict:
    inspector = sa.inspect(database.engine)
    return {
        table: next(c for c in inspector.get_columns(table) if c["name"] == "provider_mode")["type"].length
        for table in TABLES
    }


def test_provider_mode_takes_every_product_source_joined_and_the_downgrade_narrows_it(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(HALAL)
    assert _lengths(migration_database) == {table: 30 for table in TABLES}

    migration_database.upgrade(WIDER)
    assert migration_database.current_revision() == WIDER
    assert _lengths(migration_database) == {table: 64 for table in TABLES}
    with migration_database.engine.begin() as connection:
        connection.execute(sa.text("UPDATE operation_runs SET provider_mode = :mode"), {"mode": LONGEST})

    migration_database.downgrade(HALAL)
    assert _lengths(migration_database) == {table: 30 for table in TABLES}
    with migration_database.engine.connect() as connection:
        modes = connection.execute(sa.text("SELECT DISTINCT provider_mode FROM operation_runs")).scalars().all()
    assert set(modes) <= {None, LONGEST[:30]}
    migration_database.upgrade(WIDER)
    assert migration_database.current_revision() == WIDER
