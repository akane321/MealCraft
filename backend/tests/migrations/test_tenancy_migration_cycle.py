import sqlalchemy as sa

from tests.migrations.support import PRE_TENANCY_REVISION, MigrationDatabase

LEGACY_EMAIL = "legacy-import@mealcraft.invalid"
TENANT_ROOTS = ("household_profiles", "meal_plans", "agent_sessions")


def _legacy_identity(database: MigrationDatabase) -> tuple[int, int]:
    with database.engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT users.id AS user_id, memberships.household_id "
                "FROM users JOIN household_memberships AS memberships ON memberships.user_id = users.id "
                "WHERE users.normalized_email = :email"
            ),
            {"email": LEGACY_EMAIL},
        ).one()
    return row.user_id, row.household_id


def test_tenancy_upgrade_downgrade_upgrade_is_repeatable(migration_database: MigrationDatabase) -> None:
    migration_database.upgrade()
    first_legacy_identity = _legacy_identity(migration_database)
    counts_after_first_upgrade = migration_database.counts()

    migration_database.downgrade(PRE_TENANCY_REVISION)
    inspector = sa.inspect(migration_database.engine)
    for table in TENANT_ROOTS:
        assert "household_id" not in {column["name"] for column in inspector.get_columns(table)}

    assert migration_database.counts() == counts_after_first_upgrade
    with migration_database.engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == PRE_TENANCY_REVISION
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM users LEFT JOIN user_credentials ON user_credentials.user_id = users.id "
                    "WHERE users.normalized_email = :email AND users.status = 'suspended' "
                    "AND user_credentials.user_id IS NULL"
                ),
                {"email": LEGACY_EMAIL},
            ).scalar_one()
            == 1
        )

    migration_database.upgrade()
    migration_database.upgrade()

    assert _legacy_identity(migration_database) == first_legacy_identity
    assert migration_database.counts() == counts_after_first_upgrade
    assert migration_database.current_revision() == migration_database.head_revision()
    with migration_database.engine.connect() as connection:
        for table in TENANT_ROOTS:
            assert (
                connection.execute(sa.text(f'SELECT count(*) FROM "{table}" WHERE household_id IS NULL')).scalar_one()
                == 0
            )
        assert (
            connection.execute(sa.text("SELECT count(*) FROM agent_runs WHERE household_id IS NULL")).scalar_one() == 0
        )
