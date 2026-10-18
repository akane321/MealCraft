import pytest
import sqlalchemy as sa

from tests.migrations.support import MigrationDatabase
from tests.migrations.test_sprint2_foundation_migration import _add_plan, _add_recipe

FOUNDATION = "20261018_0030"
TRIPS = "20261019_0031"


def _line(connection, plan_id: int, trip: int | None, name: str = "rice") -> None:
    connection.execute(
        sa.text(
            "INSERT INTO meal_plan_grocery_items (plan_id, ingredient_name, ingredient_display_name, unit, "
            "pantry_deduction, packages_required, purchase_cost_sgd, shopping_trip) "
            "VALUES (:plan_id, :name, 'Rice', 'g', 0, 1, 2.5, :trip)"
        ),
        {"plan_id": plan_id, "name": name, "trip": trip},
    )


def _rejected(database: MigrationDatabase, plan_id: int, trip: int | None, name: str = "rice") -> None:
    with pytest.raises(sa.exc.IntegrityError), database.engine.begin() as connection:
        _line(connection, plan_id, trip, name)


def test_a_second_trip_may_buy_what_the_first_buys_and_downgrade_keeps_lists(
    migration_database: MigrationDatabase,
) -> None:
    migration_database.upgrade(FOUNDATION)
    with migration_database.engine.begin() as connection:
        recipe_id = _add_recipe(connection, "migration-test-trips")
        plan_id = _add_plan(connection, recipe_id, 10)
        connection.execute(
            sa.text(
                "INSERT INTO meal_plan_grocery_items (plan_id, ingredient_name, ingredient_display_name, unit, "
                "pantry_deduction, packages_required, purchase_cost_sgd) "
                "VALUES (:plan_id, 'salt', 'Salt', 'g', 0, 1, 1)"
            ),
            {"plan_id": plan_id},
        )
    migration_database.upgrade(TRIPS)
    assert migration_database.current_revision() == TRIPS
    columns = {c["name"]: c for c in sa.inspect(migration_database.engine).get_columns("meal_plan_grocery_items")}
    assert columns["shopping_trip"]["nullable"] and columns["perishable"]["nullable"]
    with migration_database.engine.connect() as connection:
        # No backfill: the existing line is the plan's only trip.
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM meal_plan_grocery_items WHERE shopping_trip IS NULL")
            ).scalar_one()
            == 1
        )

    with migration_database.engine.begin() as connection:
        _line(connection, plan_id, 1)
        _line(connection, plan_id, 2)
    _rejected(migration_database, plan_id, 2)  # one line per trip, ingredient and unit
    _rejected(migration_database, plan_id, None)  # NULL is the first trip
    _rejected(migration_database, plan_id, 3, name="noodles")

    # The rollback never deletes a list: two trips' lines for one ingredient block it.
    with pytest.raises(sa.exc.IntegrityError):
        migration_database.downgrade(FOUNDATION)
    with migration_database.engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM meal_plan_grocery_items WHERE shopping_trip = 2"))
    migration_database.downgrade(FOUNDATION)
    assert "shopping_trip" not in {
        c["name"] for c in sa.inspect(migration_database.engine).get_columns("meal_plan_grocery_items")
    }
    with migration_database.engine.begin() as connection:
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                sa.text(
                    "INSERT INTO meal_plan_grocery_items (plan_id, ingredient_name, ingredient_display_name, unit, "
                    "pantry_deduction, packages_required, purchase_cost_sgd) "
                    "VALUES (:plan_id, 'rice', 'Rice', 'g', 0, 1, 1)"
                ),
                {"plan_id": plan_id},
            )
    migration_database.upgrade(TRIPS)
    assert migration_database.current_revision() == TRIPS
