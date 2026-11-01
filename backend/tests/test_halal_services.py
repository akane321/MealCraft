"""Halal in the recommendation service and the private-recipe intake (docs/design/halal.md, ADR-0104).

The labels and the certified-product facts are built here, so no data file of the halal feature is read.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.paths import repository_root
from app.data import halal as halal_data
from app.data.catalog import import_catalog, load_catalog
from app.db.base import Base
from app.services.external_recipe_intake import persist_admitted_recipe, review_external_recipe
from tests.test_external_recipe_intake import draft
from tests.test_halal_household import HALAL_DISHES, halal_mains, halal_week
from tests.test_out_of_stock_swap import mains
from tests.test_planning_capability import dish_client


def label(certify=False):
    return {"status": "halal", "needs_certification": certify, "source": "test", "reason": "test"}


@pytest.fixture(autouse=True)
def labels(monkeypatch):
    built = {
        "chicken_breast": {"normalized_name": "chicken_breast", **label(certify=True)},
        "brown_rice": {"normalized_name": "brown_rice", **label()},
    }
    monkeypatch.setattr(halal_data, "halal_labels", lambda: built)
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})


def test_a_swap_on_a_halal_week_never_offers_meat_without_a_certified_product(monkeypatch):
    # A curated dish whose meat has no certified product: it passes the status screen, not the purchase.
    (roast,) = mains(("chicken-roast", "chicken_breast"))
    roast.halal_status = "needs_certification"
    with dish_client(monkeypatch, [*halal_mains(*HALAL_DISHES), roast]) as client:
        plan = halal_week(client)
        assert "chicken-roast" not in {day["recipe"]["slug"] for day in plan["days"]}
        offered = []
        for day in plan["days"]:
            preview = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={"event_type": "REPLACE_MEAL", "entry_id": day["entry_id"]},
            )
            assert preview.status_code in {201, 422}, preview.text
            if preview.status_code == 201:
                offered.append(preview.json()["after_entry"]["recipe_slug"])
        assert offered and "chicken-roast" not in offered


def test_a_private_chicken_recipe_is_stored_as_needing_certification():
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    root = repository_root()
    lines = [
        {
            "source_name": name.replace("_", " "),
            "grams": 200,
            "canonical_id": name,
            "match_confidence": 0.98,
            "allergens": [],
            "halal_status": "halal",  # what ingredients.halal_status holds: never needs_certification
        }
        for name in ("chicken_breast", "brown_rice")
    ]
    candidate = draft(title="Chicken and Rice Bowl", ingredients=lines)
    with Session(engine) as session:
        import_catalog(
            session,
            load_catalog(root / "data/ingredients/ingredients.json", root / "data/recipes/recipes.json"),
        )
        recipe, _ = persist_admitted_recipe(session, candidate, review_external_recipe(candidate), household_id=12)
        assert recipe.halal_status == "needs_certification"
