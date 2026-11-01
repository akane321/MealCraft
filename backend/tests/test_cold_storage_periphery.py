"""Cold Storage beside FairPrice in what is saved, the cart, the console and the product search
(docs/design/cold-storage.md): a line keeps its store, the cart takes only FairPrice lines, and the console edits
Cold Storage mappings under their own kind."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes.products import get_product_search_service
from app.data.overrides import overrides
from app.main import app
from app.models.meal_plan import MealPlan
from app.models.platform import AuditEvent, CatalogOverride
from app.planning import retailers
from app.planning.grocery_estimator import release_products
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.product import GroceryLineEstimate, ProductResponse, ProductSearchResponse
from app.schemas.retrieval import RetrievalTrace
from tests.test_fairprice_cart import FakeFairPrice, database, item, prepare, put_lines
from tests.test_operations_data_api import PRODUCT  # noqa: F401
from tests.test_operations_data_api import console as console
from tests.test_out_of_stock_swap import ONE_TOFU, mains, week
from tests.test_planning_capability import dish_client

NOW = datetime(2026, 10, 31, tzinfo=UTC)
KIND = "product_mapping:cold_storage"
CS_PRODUCT = {
    **PRODUCT,
    "external_id": "cs-78715",
    "name": "Cold Storage Agar",
    "product_url": "https://coldstorage.com.sg/product/agar-78715",
}
CS_SNAPSHOT = {"agar": {"status": "mapped", "review_status": "proposed", "products": [CS_PRODUCT]}}


@pytest.fixture
def plan_client(monkeypatch):
    with dish_client(monkeypatch, mains(*ONE_TOFU)) as client:
        yield client, week(client)["id"]


def cold_storage_item(name, price, *, packages=1):
    line = item(name, external_id="cs-1", price=price, packages=packages, source="cold_storage")
    line.product_url = "https://coldstorage.com.sg/product/" + name
    line.retailer = "cold_storage"
    return line


def test_a_saved_plan_keeps_the_store_of_each_line(plan_client):
    client, plan_id = plan_client
    product = ProductResponse(
        external_id="cs-78715",
        name="Agar",
        brand=None,
        category=None,
        package_size=None,
        package_unit=None,
        price_sgd=4.0,
        product_url="https://coldstorage.com.sg/product/agar-78715",
        image_url=None,
        in_stock=True,
        source="cold_storage",
        fetched_at=NOW,
    )
    line = GroceryLineEstimate(
        ingredient_name="agar",
        ingredient_display_name="Agar",
        required_quantity=10,
        unit="g",
        pantry_deduction=0,
        remaining_quantity=10,
        product=product,
        match_score=None,
        packages_required=1,
        purchase_cost_sgd=4.0,
        consumed_cost_sgd=None,
        excess_quantity=None,
        note=None,
        retailer="cold_storage",
    )
    with database() as session:
        plan = session.get(MealPlan, plan_id)
        MealPlanRepository(session, household_id=plan.household_id)._replace_grocery_items(
            plan, SimpleNamespace(items=[line])
        )
        session.commit()
        assert [row.retailer for row in plan.grocery_items] == ["cold_storage"]

    saved = client.get(f"/api/plans/{plan_id}").json()["grocery_estimate"]["items"]
    assert [(row["retailer"], row["product"]["source"]) for row in saved] == [("cold_storage", "cold_storage")]


def test_a_row_saved_before_the_store_was_kept_reads_as_its_products_store(plan_client):
    client, plan_id = plan_client
    put_lines(plan_id, [item("rice", external_id="1", price=2.0), item("salt")])

    saved = client.get(f"/api/plans/{plan_id}").json()["grocery_estimate"]["items"]

    assert {row["ingredient_name"]: row["retailer"] for row in saved} == {"rice": "fairprice", "salt": None}


def test_prepare_leaves_a_cold_storage_line_out_and_reports_it_by_store(plan_client, monkeypatch):
    client, plan_id = plan_client
    fairprice_line = item("chicken_breast", external_id="111", price=6.95)
    put_lines(
        plan_id,
        [fairprice_line, cold_storage_item("agar", 4.0, packages=2), cold_storage_item("kombu", 3.5)],
        budget=15,
    )
    asked = FakeFairPrice(monkeypatch, {})

    body = prepare(client, plan_id)

    # Only the FairPrice line is a cart line; the Cold Storage ones are neither checked nor a cart problem.
    assert [line["ingredient_name"] for line in body["lines"]] == ["chicken_breast"]
    assert asked.queries == ["chicken breast"]
    assert body["other_stores"] == [{"retailer": "cold_storage", "lines": 2, "purchase_total_sgd": 11.5}]
    assert body["planned_total_sgd"] == 6.95
    # The budget counts both stores: 6.95 at FairPrice and 11.50 at Cold Storage against 15.
    assert body["over_budget"] is True


def test_a_plan_with_only_fairprice_lines_has_no_other_stores(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, [item("chicken_breast", external_id="111", price=6.95)])
    FakeFairPrice(monkeypatch, {})

    assert prepare(client, plan_id)["other_stores"] == []


def test_the_console_lists_and_edits_cold_storage_mappings_under_their_own_kind(console, monkeypatch):  # noqa: F811
    client, factory = console
    monkeypatch.setattr(retailers, "cold_storage_snapshot", lambda: CS_SNAPSHOT)
    fairprice_agar = release_products()["agar"]

    listed = client.get("/api/ops/data/mappings", params={"retailer": "cold_storage"}).json()
    assert listed["total"] == 1
    assert (listed["items"][0]["retailer"], listed["items"][0]["source"]) == ("cold_storage", "file")
    assert client.get("/api/ops/data/mappings").json()["items"][0]["retailer"] == "fairprice"

    edited = {**CS_PRODUCT, "external_id": "cs-99", "price_sgd": 3.2}
    response = client.put("/api/ops/data/mappings/agar", params={"retailer": "cold_storage"}, json={"product": edited})
    assert response.status_code == 200
    assert (response.json()["retailer"], response.json()["source"]) == ("cold_storage", "console")
    assert overrides(KIND)["agar"]["products"][0]["external_id"] == "cs-99"
    assert "agar" not in overrides("product_mapping")
    assert retailers.cold_storage_products()["agar"]["products"][0]["external_id"] == "cs-99"
    assert release_products()["agar"] == fairprice_agar  # FairPrice's mapping is untouched
    with factory() as session:
        assert session.scalars(select(CatalogOverride.kind)).all() == [KIND]
        assert session.scalars(select(AuditEvent.target_type).where(AuditEvent.action == "mapping.changed")).all() == [
            KIND
        ]

    removed = client.delete("/api/ops/data/mappings/agar", params={"retailer": "cold_storage"})
    assert removed.status_code == 200 and removed.json()["status"] == "removed"
    assert "agar" not in retailers.cold_storage_products() and "agar" in release_products()
    assert client.delete("/api/ops/data/mappings/agar", params={"retailer": "cold_storage"}).status_code == 404
    assert client.get("/api/ops/data/mappings", params={"retailer": "giant"}).status_code == 422


def test_the_product_search_route_passes_the_retailer(monkeypatch):
    asked = []

    class Service:
        def search(self, query, **options):
            asked.append(options)
            trace = RetrievalTrace(
                requested_source="cold_storage",
                provider_used="cold_storage",
                mode="live",
                status="no_match",
                query=query,
                fetched_at=NOW,
                parser_version="cold-storage-flight-v1",
                candidate_count=0,
            )
            return ProductSearchResponse(
                query=query,
                provider_used="cold_storage",
                fallback_used=False,
                cached=False,
                warning=None,
                items=[],
                retrieval=trace,
            )

    app.dependency_overrides[get_product_search_service] = Service
    try:
        client = TestClient(app)
        assert client.get("/api/products/search", params={"q": "agar", "retailer": "cold_storage"}).status_code == 200
        assert client.get("/api/products/search", params={"q": "agar"}).status_code == 200
        assert client.get("/api/products/search", params={"q": "agar", "retailer": "giant"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_product_search_service)
    assert [options["retailer"] for options in asked] == ["cold_storage", "fairprice"]
