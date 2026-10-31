import sqlalchemy as sa

from tests.migrations.support import MigrationDatabase

CART = "20261029_0032"
HALAL = "20261031_0033"


def _column(database: MigrationDatabase) -> dict:
    return {c["name"]: c for c in sa.inspect(database.engine).get_columns("household_profile_versions")}.get(
        "requires_halal", {}
    )


def _line_column(database: MigrationDatabase) -> dict:
    return {c["name"]: c for c in sa.inspect(database.engine).get_columns("meal_plan_grocery_items")}.get(
        "product_halal_certified", {}
    )


def test_the_halal_switch_is_off_for_every_saved_version_and_the_downgrade_drops_it(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(CART)
    assert not _column(migration_database)
    assert not _line_column(migration_database)
    with migration_database.engine.connect() as connection:
        versions = connection.execute(sa.text("SELECT count(*) FROM household_profile_versions")).scalar_one()
    migration_database.upgrade(HALAL)
    assert migration_database.current_revision() == HALAL
    assert _column(migration_database)["nullable"] is False
    # A saved grocery line's Halal mark is unknown (NULL) until a plan is saved with one; never halal by default.
    assert _line_column(migration_database)["nullable"] is True
    with migration_database.engine.begin() as connection:
        # Every version saved before the switch planned ordinary meals, and still does.
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM household_profile_versions WHERE requires_halal = false")
            ).scalar_one()
            == versions
        )
        connection.execute(sa.text("UPDATE household_profile_versions SET requires_halal = true"))

    migration_database.downgrade(CART)
    assert migration_database.current_revision() == CART
    assert not _column(migration_database)
    assert not _line_column(migration_database)
    with migration_database.engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM household_profile_versions")).scalar_one() == versions
    migration_database.upgrade(HALAL)
    assert migration_database.current_revision() == HALAL
