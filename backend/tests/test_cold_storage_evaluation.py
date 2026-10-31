"""The frozen evaluation catalog is FairPrice's: no Cold Storage snapshot reaches it (docs/design/cold-storage.md)."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from app.evaluation import meal_day_week_runner, multidish_labels, runner, workbench
from app.planning import grocery_estimator, retailers
from app.planning.retailers import cold_storage_products

CS_ENTRY = {
    "status": "mapped",
    "review_status": "proposed",
    "products": [
        {
            "external_id": "cs-1",
            "name": "Cold Storage Spice",
            "brand": None,
            "category": None,
            "package_grams": 100,
            "package_grams_basis": "name",
            "price_sgd": 2.0,
            "product_url": "https://example.test/cs-1",
            "in_stock": True,
            "query": "spice",
            "fetched_at": "2026-10-31T00:00:00+00:00",
        }
    ],
}


class Reached(Exception):
    """Raised by a stand-in for the first call that plans or prices, carrying what Cold Storage looked like there."""

    def __init__(self, seen: dict) -> None:
        self.seen = seen


@pytest.fixture(autouse=True)
def cold_storage_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Cold Storage snapshot is present (fake loader), and FairPrice has nothing for `spice`."""
    monkeypatch.setattr(retailers, "cold_storage_snapshot", lambda: {"spice": CS_ENTRY})
    monkeypatch.setattr(retailers, "overrides", lambda kind: {})
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset())
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: {})


def stand_in(*_args, **_kwargs):
    raise Reached(cold_storage_products())


@contextmanager
def stand_in_database(*_args, **_kwargs):
    raise Reached(cold_storage_products())
    yield  # pragma: no cover


def test_the_fake_snapshot_is_visible_outside_the_frozen_entry_points() -> None:
    assert "spice" in cold_storage_products()


def test_the_v1_gate_sees_no_cold_storage_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_catalog", stand_in)
    with pytest.raises(Reached) as reached:
        runner.evaluate(
            ingredient_path=Path("x"), recipe_path=Path("x"), scenario_path=Path("x"), fixture_path=Path("x")
        )
    assert reached.value.seen == {}


def test_a_meal_day_week_episode_sees_no_cold_storage_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meal_day_week_runner, "product_database", stand_in_database)
    with pytest.raises(Reached) as reached:
        meal_day_week_runner.run_episode({"episode_id": "e"})
    assert reached.value.seen == {}


def test_the_label_pool_sees_no_cold_storage_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meal_day_week_runner, "product_database", stand_in_database)
    with pytest.raises(Reached) as reached:
        multidish_labels.product_candidates(())
    assert reached.value.seen == {}


def test_the_label_price_of_a_line_ignores_cold_storage() -> None:
    """`bought` prices a week's grams at the frozen catalog: a Cold Storage-only ingredient is unpriceable."""
    assert multidish_labels.bought("spice", 50) == float("inf")
    # The same line is priced once the store is allowed (the control).
    choice = grocery_estimator.choose_product(
        multidish_labels._pricing()[0],
        grocery_estimator.ProductMatcher(),
        "spice",
        "Spice",
        "g",
        live=False,
        quantity=50,
    )
    assert choice.product is not None
    assert choice.product.external_id == "cs-1"


def test_the_workbench_evaluations_see_no_cold_storage_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workbench, "evaluate", stand_in)
    path = Path("x")
    with pytest.raises(Reached) as reached:
        workbench.build_workbench(
            ingredient_path=path,
            recipe_path=path,
            developer_path=path,
            heldout_path=path,
            agent_path=path,
            scope_path=path,
            grounding_path=path,
            fixture_path=path,
        )
    assert reached.value.seen == {}
