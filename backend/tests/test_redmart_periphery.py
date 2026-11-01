"""RedMart beside FairPrice and Cold Storage in what is saved, the cart, the console and the product search
(docs/design/redmart.md): a line keeps its store, the cart takes only FairPrice lines and reports each other store
apart in fill order, and the console edits RedMart mappings under their own kind."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes.products import get_product_search_service
from app.data.overrides import overrides
from app.main import app
from app.models.platform import AuditEvent, CatalogOverride
from app.planning import retailers
from app.planning.grocery_estimator import release_products
from app.schemas.product import ProductSearchResponse
from app.schemas.retrieval import RetrievalTrace
from tests.test_cold_storage_periphery import cold_storage_item
from tests.test_fairprice_cart import FakeFairPrice, item, prepare, put_lines
from tests.test_operations_data_api import PRODUCT  # noqa: F401
from tests.test_operations_data_api import console as console
from tests.test_out_of_stock_swap import ONE_TOFU, mains, week
from tests.test_planning_capability import dish_client

NOW = datetime(2026, 11, 1, tzinfo=UTC)
KIND = "product_mapping:redmart"
RM_PRODUCT = {
    **PRODUCT,
    "external_id": "rm-3124212075",
    "name": "RedMart Agar Powder",
    "product_url": "https://www.lazada.sg/products/pdp-i3124212075.html",
}
RM_SNAPSHOT = {"agar": {"status": "mapped", "review_status": "proposed", "products": [RM_PRODUCT]}}


@pytest.fixture
def plan_client(monkeypatch):
    with dish_client(monkeypatch, mains(*ONE_TOFU)) as client:
        yield client, week(client)["id"]


def redmart_item(name, price, *, packages=1):
    line = item(name, external_id="rm-1", price=price, packages=packages, source="redmart")
    line.product_url = "https://www.lazada.sg/products/" + name
    line.retailer = "redmart"
    return line


def test_a_row_saved_with_a_redmart_product_reads_as_redmart(plan_client):
    client, plan_id = plan_client
    put_lines(plan_id, [item("agar", external_id="rm-1", price=4.0, source="redmart")])

    saved = client.get(f"/api/plans/{plan_id}").json()["grocery_estimate"]["items"]

    assert [(row["retailer"], row["product"]["source"]) for row in saved] == [("redmart", "redmart")]


def test_prepare_totals_each_other_store_apart_in_fill_order(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(
        plan_id,
        [
            redmart_item("kombu", 3.5),
            item("chicken_breast", external_id="111", price=6.95),
            cold_storage_item("agar", 4.0, packages=2),
            redmart_item("yuzu", 2.0, packages=0),  # not bought: no line
            redmart_item("miso", 1.25),
        ],
        budget=20,
    )
    asked = FakeFairPrice(monkeypatch, {})

    body = prepare(client, plan_id)

    # Only the FairPrice line is a cart line; Cold Storage comes before RedMart whatever the order of the lines.
    assert [line["ingredient_name"] for line in body["lines"]] == ["chicken_breast"]
    assert asked.queries == ["chicken breast"]
    assert body["other_stores"] == [
        {"retailer": "cold_storage", "lines": 1, "purchase_total_sgd": 8.0},
        {"retailer": "redmart", "lines": 2, "purchase_total_sgd": 4.75},
    ]
    # The budget counts all three stores: 6.95 + 8.00 + 4.75 = 19.70 against 20, then against 19.
    assert body["over_budget"] is False
    put_lines(plan_id, [redmart_item("kombu", 13.5), item("chicken_breast", external_id="111", price=6.95)], budget=20)
    FakeFairPrice(monkeypatch, {})
    assert prepare(client, plan_id)["over_budget"] is True


def test_a_plan_with_only_redmart_lines_has_one_other_store_and_no_cart_lines(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, [redmart_item("kombu", 3.5)])
    asked = FakeFairPrice(monkeypatch, {})

    body = prepare(client, plan_id)

    assert (body["lines"], asked.queries) == ([], [])
    assert body["other_stores"] == [{"retailer": "redmart", "lines": 1, "purchase_total_sgd": 3.5}]


def test_the_console_lists_and_edits_redmart_mappings_under_their_own_kind(console, monkeypatch):  # noqa: F811
    client, factory = console
    monkeypatch.setattr(retailers, "redmart_snapshot", lambda: RM_SNAPSHOT)
    fairprice_agar = release_products()["agar"]

    listed = client.get("/api/ops/data/mappings", params={"retailer": "redmart"}).json()
    assert listed["total"] == 1
    assert (listed["items"][0]["retailer"], listed["items"][0]["source"]) == ("redmart", "file")
    assert client.get("/api/ops/data/mappings").json()["items"][0]["retailer"] == "fairprice"

    edited = {**RM_PRODUCT, "external_id": "rm-99", "price_sgd": 3.2}
    response = client.put("/api/ops/data/mappings/agar", params={"retailer": "redmart"}, json={"product": edited})
    assert response.status_code == 200
    assert (response.json()["retailer"], response.json()["source"]) == ("redmart", "console")
    assert overrides(KIND)["agar"]["products"][0]["external_id"] == "rm-99"
    assert "agar" not in overrides("product_mapping") and "agar" not in overrides("product_mapping:cold_storage")
    assert retailers.store_products("redmart")["agar"]["products"][0]["external_id"] == "rm-99"
    assert release_products()["agar"] == fairprice_agar  # FairPrice's mapping is untouched
    with factory() as session:
        assert session.scalars(select(CatalogOverride.kind)).all() == [KIND]
        assert session.scalars(select(AuditEvent.target_type).where(AuditEvent.action == "mapping.changed")).all() == [
            KIND
        ]

    removed = client.delete("/api/ops/data/mappings/agar", params={"retailer": "redmart"})
    assert removed.status_code == 200 and removed.json()["status"] == "removed"
    assert "agar" not in retailers.store_products("redmart") and "agar" in release_products()
    assert client.delete("/api/ops/data/mappings/agar", params={"retailer": "redmart"}).status_code == 404
    assert client.get("/api/ops/data/mappings", params={"retailer": "giant"}).status_code == 422


def test_the_product_search_route_passes_redmart(monkeypatch):
    asked = []

    class Service:
        def search(self, query, **options):
            asked.append(options)
            trace = RetrievalTrace(
                requested_source="redmart",
                provider_used="redmart",
                mode="live",
                status="no_match",
                query=query,
                fetched_at=NOW,
                parser_version="redmart-ajax-v1",
                candidate_count=0,
            )
            return ProductSearchResponse(
                query=query,
                provider_used="redmart",
                fallback_used=False,
                cached=False,
                warning=None,
                items=[],
                retrieval=trace,
            )

    app.dependency_overrides[get_product_search_service] = Service
    try:
        client = TestClient(app)
        assert client.get("/api/products/search", params={"q": "agar", "retailer": "redmart"}).status_code == 200
        assert client.get("/api/products/search", params={"q": "agar", "retailer": "giant"}).status_code == 422
        # A platform priced only by hand has no search to call (docs/design/manual-prices.md): refused, not a 500.
        assert client.get("/api/products/search", params={"q": "agar", "retailer": "shopee"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_product_search_service)
    assert [options["retailer"] for options in asked] == ["redmart"]


def test_every_product_source_joined_fits_the_saved_provider_mode() -> None:
    """A planning run saves the sources it priced with, joined (`WeeklyMealPlanService._operation_run`); with RedMart
    and the hand-recorded prices the longest is 45 characters, past the String(30) PostgreSQL enforced."""
    from typing import get_args

    from app.models.agent import AgentToolExecution
    from app.models.platform import OperationRun
    from app.schemas.product import ProductSource

    longest = ",".join(sorted(get_args(ProductSource)))

    assert longest == "cold_storage,fairprice,fixture,manual,redmart"
    for model in (OperationRun, AgentToolExecution):
        assert len(longest) <= model.__table__.c.provider_mode.type.length
