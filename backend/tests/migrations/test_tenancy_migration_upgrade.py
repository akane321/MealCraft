import pytest
import sqlalchemy as sa

from tests.migrations.support import TENANCY_REVISION, MigrationDatabase

LEGACY_EMAIL = "legacy-import@mealcraft.invalid"
TENANT_ROOTS = ("household_profiles", "meal_plans", "agent_sessions")


def _constraint_by_name(items: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(item for item in items if item["name"] == name)


def test_tenancy_upgrade_backfills_and_constrains_private_roots(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade()

    inspector = sa.inspect(migration_database.engine)
    with migration_database.engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == TENANCY_REVISION

        legacy_user = connection.execute(
            sa.text("SELECT id, status FROM users WHERE normalized_email = :email"),
            {"email": LEGACY_EMAIL},
        ).mappings().one()
        assert legacy_user["status"] == "suspended"
        assert connection.execute(
            sa.text("SELECT count(*) FROM user_credentials WHERE user_id = :user_id"),
            {"user_id": legacy_user["id"]},
        ).scalar_one() == 0

        legacy_membership = connection.execute(
            sa.text(
                "SELECT household_id, role, status FROM household_memberships "
                "WHERE user_id = :user_id"
            ),
            {"user_id": legacy_user["id"]},
        ).mappings().one()
        assert legacy_membership["role"] == "owner"
        assert legacy_membership["status"] == "active"

        legacy_household_id = legacy_membership["household_id"]
        for table in TENANT_ROOTS:
            assert connection.execute(
                sa.text(f'SELECT count(*) FROM "{table}" WHERE household_id IS NULL')
            ).scalar_one() == 0
            assert connection.execute(
                sa.text(f'SELECT count(*) FROM "{table}" WHERE household_id != :household_id'),
                {"household_id": legacy_household_id},
            ).scalar_one() == 0

        assert connection.execute(
            sa.text("SELECT count(*) FROM agent_runs WHERE household_id IS NULL")
        ).scalar_one() == 0
        assert connection.execute(
            sa.text("SELECT count(*) FROM agent_runs WHERE household_id != :household_id"),
            {"household_id": legacy_household_id},
        ).scalar_one() == 0

        assert connection.execute(
            sa.text("SELECT count(*) FROM operation_runs WHERE household_id IN (2001, 2002)")
        ).scalar_one() == 2
        assert connection.execute(
            sa.text("SELECT count(*) FROM audit_events WHERE household_id IN (2001, 2002)")
        ).scalar_one() == 2

    assert migration_database.counts() == {
        **migration_database.counts_before_upgrade,
        "users": migration_database.counts_before_upgrade["users"] + 1,
        "households": migration_database.counts_before_upgrade["households"] + 1,
        "household_memberships": migration_database.counts_before_upgrade["household_memberships"] + 1,
    }

    for table in TENANT_ROOTS:
        household_column = next(column for column in inspector.get_columns(table) if column["name"] == "household_id")
        assert household_column["nullable"] is False

    profile_foreign_key = _constraint_by_name(
        inspector.get_foreign_keys("household_profiles"),
        "household_profiles_household_id_fkey",
    )
    assert profile_foreign_key["referred_table"] == "households"
    assert profile_foreign_key["options"] == {"ondelete": "CASCADE"}
    assert _constraint_by_name(
        inspector.get_unique_constraints("household_profiles"),
        "household_profiles_household_key",
    )["column_names"] == ["household_id"]

    assert _constraint_by_name(
        inspector.get_indexes("meal_plans"),
        "meal_plans_household_created_idx",
    )["column_names"] == ["household_id", "created_at", "id"]
    assert _constraint_by_name(
        inspector.get_indexes("agent_sessions"),
        "agent_sessions_household_updated_idx",
    )["column_names"] == ["household_id", "updated_at", "id"]


def test_tenancy_upgrade_rejects_orphan_household_ids(migration_database: MigrationDatabase) -> None:
    migration_database.upgrade()

    with migration_database.engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("UPDATE meal_plans SET household_id = -1 WHERE id = 5001"))
        transaction.rollback()
