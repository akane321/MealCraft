import sqlalchemy as sa

from tests.migrations.support import MigrationDatabase
from tests.migrations.test_sprint2_foundation_migration import _add_plan, _add_recipe

TRIPS = "20261019_0031"
CART = "20261029_0032"


def _columns(database: MigrationDatabase, table: str) -> dict:
    return {c["name"]: c for c in sa.inspect(database.engine).get_columns(table)}


def test_the_cart_columns_are_nullable_and_the_downgrade_drops_only_them(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(TRIPS)
    with migration_database.engine.begin() as connection:
        recipe_id = _add_recipe(connection, "migration-test-cart")
        plan_id = _add_plan(connection, recipe_id, 7)
    migration_database.upgrade(CART)
    assert migration_database.current_revision() == CART
    assert _columns(migration_database, "product_snapshots")["cart_item_id"]["nullable"]
    assert _columns(migration_database, "meal_plans")["fairprice_cart"]["nullable"]
    with migration_database.engine.begin() as connection:
        # No backfill: the existing plan has sent nothing.
        assert connection.execute(
            sa.text("SELECT fairprice_cart IS NULL FROM meal_plans WHERE id = :id"), {"id": plan_id}
        ).scalar_one()
        connection.execute(
            sa.text("UPDATE meal_plans SET fairprice_cart = CAST(:cart AS json) WHERE id = :id"),
            {"cart": '{"1": {"status": "in_cart"}}', "id": plan_id},
        )

    migration_database.downgrade(TRIPS)
    assert migration_database.current_revision() == TRIPS
    assert "cart_item_id" not in _columns(migration_database, "product_snapshots")
    assert "fairprice_cart" not in _columns(migration_database, "meal_plans")
    with migration_database.engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM meal_plans WHERE id = :id"), {"id": plan_id}).scalar_one()
            == 1
        )
    migration_database.upgrade(CART)
    assert migration_database.current_revision() == CART
