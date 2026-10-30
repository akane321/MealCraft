"""The FairPrice cart API (docs/design/fairprice-cart.md): prepare, report, ordered, and the plan's cart state."""

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.meal_plan import MealPlan, MealPlanGroceryItem
from app.products.provider import FairPriceProductProvider
from app.repositories.product import ProductSnapshotRepository
from app.schemas.product import ProductResponse
from tests.test_out_of_stock_swap import ONE_TOFU, mains, week
from tests.test_planning_capability import dish_client

NOW = datetime(2026, 10, 29, tzinfo=UTC)
PASSWORD = "correct horse battery staple"


def item(name, *, external_id=None, price=None, packages=1, source="fairprice", trip=None, unit="g"):
    """One saved grocery line; no external id is a line with no product."""
    priced = external_id is not None
    return MealPlanGroceryItem(
        ingredient_name=name,
        ingredient_display_name=name.replace("_", " "),
        required_quantity=Decimal(100),
        unit=unit,
        pantry_deduction=Decimal(0),
        remaining_quantity=Decimal(100),
        product_external_id=external_id,
        product_name=f"{name} pack" if priced else None,
        product_price_sgd=Decimal(str(price)) if priced else None,
        product_url=f"https://www.fairprice.com.sg/product/{name}" if priced else None,
        product_source=source if priced else None,
        product_fetched_at=NOW if priced else None,
        packages_required=packages,
        purchase_cost_sgd=Decimal(str(price)) * packages if priced else Decimal(0),
        shopping_trip=trip,
    )


@contextmanager
def database():
    generator = app.dependency_overrides[get_db_session]()
    session = next(generator)
    try:
        yield session
    finally:
        generator.close()


def put_lines(plan_id, items, *, pricing_mode="live", budget=None):
    with database() as session:
        plan = session.get(MealPlan, plan_id)
        plan.grocery_items.clear()
        session.flush()  # the old lines go first: one line per trip, ingredient and unit
        plan.grocery_items = items
        plan.pricing_mode = pricing_mode
        plan.weekly_budget_sgd = Decimal(str(budget)) if budget is not None else None
        session.commit()


def listing(external_id, cart_item_id, price, *, in_stock=True):
    return ProductResponse(
        external_id=external_id,
        name="live",
        brand=None,
        category=None,
        package_size=None,
        package_unit=None,
        price_sgd=price,
        product_url="https://www.fairprice.com.sg/product/live",
        image_url=None,
        in_stock=in_stock,
        source="fairprice",
        fetched_at=datetime.now(UTC),
        cart_item_id=cart_item_id,
    )


class FakeFairPrice:
    """Stands in for the FairPrice listing: what each search query returns, and the queries asked."""

    def __init__(self, monkeypatch, answers):
        self.queries = []

        def search(provider, query, *, limit, timeout_seconds=None):
            self.queries.append(query)
            return answers.get(query, [])

        monkeypatch.setattr(FairPriceProductProvider, "search", search)


LIVE = {
    "chicken breast": [listing("111", "9001", 7.45)],
    "salmon fillet": [listing("222", "9002", 5.50, in_stock=False)],
    "canned tuna": [listing("other", "9999", 3.00)],  # the chosen product 333 is no longer listed
    "chickpea": [listing("444", None, 2.00)],  # a listing without an id cannot go in a cart
}


def lines():
    return [
        item("chicken_breast", external_id="111", price=6.95, packages=2),
        item("salmon_fillet", external_id="222", price=5.00),
        item("canned_tuna", external_id="333", price=3.00),
        item("chickpea", external_id="444", price=2.00),
        item("rice"),
        item("black_bean", external_id="555", price=1.00, packages=0),
        item("mushroom", external_id="fixture-7", price=2.00, source="fixture"),
    ]


@pytest.fixture
def plan_client(monkeypatch):
    with dish_client(monkeypatch, mains(*ONE_TOFU)) as client:
        yield client, week(client)["id"]


def url(plan_id, route):
    return f"/api/plans/{plan_id}/fairprice-cart/{route}"


def prepare(client, plan_id, trip=None):
    response = client.post(url(plan_id, "prepare"), json={"shopping_trip": trip})
    assert response.status_code == 200, response.text
    return response.json()


def report_body(fingerprint, results=(), trip=None):
    return {"shopping_trip": trip, "fingerprint": fingerprint, "results": list(results)}


def result(status="added", quantity=2, key="1|chicken_breast|g"):
    return {"line_key": key, "cart_item_id": "9001", "status": status, "quantity": quantity, "cart_price_sgd": 7.45}


def test_prepare_gives_every_line_its_status_and_the_totals(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines(), budget=27)
    fairprice = FakeFairPrice(monkeypatch, LIVE)

    body = prepare(client, plan_id)

    by_name = {line["ingredient_name"]: line for line in body["lines"]}
    assert {name: line["status"] for name, line in by_name.items()} == {
        "chicken_breast": "ready",
        "salmon_fillet": "out_of_stock",
        "canned_tuna": "not_found",
        "chickpea": "not_found",
        "rice": "no_product",
        "black_bean": "not_bought",
        "mushroom": "no_product",
    }
    chicken = by_name["chicken_breast"]
    assert chicken["line_key"] == "1|chicken_breast|g"
    assert (chicken["client_item_id"], chicken["cart_item_id"], chicken["quantity"]) == ("111", "9001", 2)
    assert (chicken["planned_price_sgd"], chicken["live_price_sgd"]) == (6.95, 7.45)
    assert chicken["product_url"] == "https://www.fairprice.com.sg/product/chicken_breast"
    assert by_name["canned_tuna"]["live_price_sgd"] is None and by_name["canned_tuna"]["cart_item_id"] is None
    assert by_name["salmon_fillet"]["live_price_sgd"] == 5.50
    # Only the lines FairPrice can be asked about were asked.
    assert sorted(fairprice.queries) == ["canned tuna", "chicken breast", "chickpea", "salmon fillet"]

    assert body["ready_total_sgd"] == 14.90  # 2 x 7.45
    assert body["planned_total_sgd"] == 25.90  # 13.90 + 5.00 + 3.00 + 2.00 + 2.00 (the fixture line) + 0 + 0
    assert body["projected_total_sgd"] == 27.40  # chicken and salmon at their live prices
    assert body["budget_sgd"] == 27 and body["over_budget"] is True
    assert body["shopping_trip"] is None and body["plan_id"] == plan_id
    assert len(body["fingerprint"]) == 64


def test_prepare_is_within_budget_when_the_projected_total_fits(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines(), budget=30)
    FakeFairPrice(monkeypatch, LIVE)

    body = prepare(client, plan_id)

    assert body["projected_total_sgd"] == 27.40 and body["over_budget"] is False
    put_lines(plan_id, lines(), budget=None)
    assert prepare(client, plan_id)["budget_sgd"] is None


def test_a_fixture_plan_makes_no_live_calls_and_every_line_is_no_product(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines(), pricing_mode="fixture")
    fairprice = FakeFairPrice(monkeypatch, LIVE)

    body = prepare(client, plan_id)

    assert {line["status"] for line in body["lines"]} == {"no_product"}
    assert fairprice.queries == []
    assert body["ready_total_sgd"] == 0 and body["projected_total_sgd"] == body["planned_total_sgd"]


def test_a_second_prepare_inside_the_cache_time_keeps_the_cart_id(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    fairprice = FakeFairPrice(monkeypatch, LIVE)
    prepare(client, plan_id)
    fairprice.queries.clear()

    again = prepare(client, plan_id)

    chicken = next(line for line in again["lines"] if line["ingredient_name"] == "chicken_breast")
    assert (chicken["status"], chicken["cart_item_id"]) == ("ready", "9001")
    # the cache could not answer these: the product is gone, and a cached row without a cart id is a miss
    assert fairprice.queries == ["canned tuna", "chickpea"]


def test_a_cached_row_without_a_cart_id_is_refetched_and_gets_its_id(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, [item("chickpea", external_id="444", price=2.00)])
    answers = {"chickpea": [listing("444", None, 2.00)]}
    fairprice = FakeFairPrice(monkeypatch, answers)
    assert prepare(client, plan_id)["lines"][0]["status"] == "not_found"
    answers["chickpea"] = [listing("444", "9004", 2.00)]  # FairPrice now gives the listing an id
    fairprice.queries.clear()

    line = prepare(client, plan_id)["lines"][0]

    assert fairprice.queries == ["chickpea"]
    assert (line["status"], line["cart_item_id"]) == ("ready", "9004")


def test_the_snapshot_cache_keeps_the_cart_id():
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        repository = ProductSnapshotRepository(session)
        repository.replace_query_results(
            source="fairprice", search_query="chicken", products=[listing("1", "9001", 7.45), listing("2", None, 1.0)]
        )
        cached = repository.get_fresh(source="fairprice", search_query="chicken", fetched_after=NOW.min, limit=5)
    assert [product.cart_item_id for product in cached] == ["9001", None]


def test_the_parser_reads_the_cart_id_from_the_listing_id():
    provider = FairPriceProductProvider(base_url="https://www.fairprice.com.sg", timeout_seconds=1)
    record = {
        "id": 172993,
        "clientItemId": 13097675,
        "name": "Chicken",
        "slug": "chicken-13097675",
        "final_price": 6.95,
    }

    product = provider._parse_product(record, NOW)
    assert (product.external_id, product.cart_item_id) == ("13097675", "172993")
    without_id = provider._parse_product({k: v for k, v in record.items() if k != "id"}, NOW)
    assert without_id.cart_item_id is None


def test_a_second_trip_has_its_own_lines_key_and_record(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(
        plan_id,
        [
            item("chicken_breast", external_id="111", price=6.95, trip=1),
            item("chicken_breast", external_id="111", price=6.95, trip=2),
        ],
    )
    FakeFairPrice(monkeypatch, LIVE)

    body = prepare(client, plan_id, trip=2)
    assert [line["line_key"] for line in body["lines"]] == ["2|chicken_breast|g"]
    assert body["shopping_trip"] == 2 and body["planned_total_sgd"] == 6.95

    state = client.post(
        url(plan_id, "report"), json=report_body(body["fingerprint"], [result(key="2|chicken_breast|g")], trip=2)
    ).json()
    assert list(state) == ["2"]
    plan = client.get(f"/api/plans/{plan_id}").json()
    assert list(plan["fairprice_cart"]) == ["2"] and plan["fairprice_cart"]["2"]["stale"] is False


def sent(client, plan_id):
    body = prepare(client, plan_id)
    response = client.post(url(plan_id, "report"), json=report_body(body["fingerprint"], [result()]))
    assert response.status_code == 200, response.text
    return body, response.json()


def test_a_report_is_stored_and_the_plan_shows_it_until_the_lines_change(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"] is None

    body, state = sent(client, plan_id)

    trip = state["1"]
    assert trip["status"] == "in_cart" and trip["ordered_at"] is None and trip["stale"] is False
    assert trip["fingerprint"] == body["fingerprint"] and trip["results"] == [result()] and trip["sent_at"]
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"] == state

    put_lines(plan_id, [item("chicken_breast", external_id="111", price=6.95, packages=3), *lines()[1:]])
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"]["1"]["stale"] is True


@pytest.mark.parametrize(
    "results",
    [[], [result("failed", 0)], [result("out_of_stock", 0)], [result("added", 0)], [result("reduced", 0)]],
)
def test_a_report_with_nothing_added_is_not_stored(plan_client, monkeypatch, results):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)
    fingerprint = prepare(client, plan_id)["fingerprint"]

    response = client.post(url(plan_id, "report"), json=report_body(fingerprint, results))

    assert response.status_code == 200 and response.json() == {}
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"] is None


def test_a_report_with_nothing_added_keeps_the_stored_record(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)
    _, state = sent(client, plan_id)

    again = client.post(url(plan_id, "report"), json=report_body("a" * 64, [result("failed", 0)]))

    assert again.json() == state
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"] == state


def test_a_reduced_report_is_stored(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)
    fingerprint = prepare(client, plan_id)["fingerprint"]

    state = client.post(url(plan_id, "report"), json=report_body(fingerprint, [result("reduced", 1)])).json()

    assert state["1"]["results"] == [result("reduced", 1)]


def test_the_fingerprint_is_the_hash_of_the_bought_fairprice_lines(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)

    bought = ["1|canned_tuna|g|333|1", "1|chicken_breast|g|111|2", "1|chickpea|g|444|1", "1|salmon_fillet|g|222|1"]
    assert prepare(client, plan_id)["fingerprint"] == hashlib.sha256("\n".join(bought).encode()).hexdigest()


def test_ordered_is_a_conflict_until_the_trip_was_sent(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)

    assert client.post(url(plan_id, "ordered"), json={"shopping_trip": None}).status_code == 409
    sent(client, plan_id)
    assert client.post(url(plan_id, "ordered"), json={"shopping_trip": 2}).status_code == 409  # another trip

    ordered = client.post(url(plan_id, "ordered"), json={"shopping_trip": None})
    assert ordered.status_code == 200
    assert ordered.json()["1"]["status"] == "ordered" and ordered.json()["1"]["ordered_at"]
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"]["1"]["status"] == "ordered"


@pytest.mark.parametrize(
    "change",
    [
        {"fingerprint": "abc"},
        {"fingerprint": "G" * 64},
        {"results": [result("bought")]},
        {"results": [result(quantity=1000)]},
        {"results": [result(quantity=-1)]},
        {"results": [result(quantity=1.5)]},
        {"results": [result()] * 501},
    ],
)
def test_a_malformed_report_is_refused(plan_client, change):
    client, plan_id = plan_client

    assert client.post(url(plan_id, "report"), json={**report_body("a" * 64), **change}).status_code == 422
    largest = report_body("a" * 64, [result("failed", 999)] * 500)
    assert client.post(url(plan_id, "report"), json=largest).status_code == 200


def test_another_household_cannot_see_or_change_the_plan(plan_client, monkeypatch):
    client, plan_id = plan_client
    put_lines(plan_id, lines())
    FakeFairPrice(monkeypatch, LIVE)
    sent(client, plan_id)

    with TestClient(app) as other:
        registered = other.post(
            "/api/auth/register",
            json={"email": "other@example.test", "password": PASSWORD, "display_name": "Other"},
        )
        other.headers.update({"X-CSRF-Token": registered.json()["csrf_token"]})
        assert other.post(url(plan_id, "prepare"), json={"shopping_trip": None}).status_code == 404
        assert other.post(url(plan_id, "report"), json=report_body("a" * 64)).status_code == 404
        assert other.post(url(plan_id, "ordered"), json={"shopping_trip": None}).status_code == 404
    assert client.get(f"/api/plans/{plan_id}").json()["fairprice_cart"]["1"]["status"] == "in_cart"


@pytest.mark.parametrize(
    ("route", "body"),
    [
        ("prepare", {"shopping_trip": None}),
        ("report", report_body("a" * 64)),
        ("ordered", {"shopping_trip": None}),
    ],
)
def test_the_writes_need_the_csrf_token(plan_client, route, body):
    client, plan_id = plan_client
    put_lines(plan_id, lines())

    for headers in ({"X-CSRF-Token": ""}, {"X-CSRF-Token": "forged"}):
        assert client.post(url(plan_id, route), json=body, headers=headers).status_code == 403
    with database() as session:
        assert session.get(MealPlan, plan_id).fairprice_cart is None
