"""Prices recorded by hand, the last fill layer (docs/design/manual-prices.md): used only where FairPrice, Cold Storage
and RedMart have no product in stock, a line keeps the platform it was recorded from, and none is ever read live."""

import json

import pytest

from app.data.price_coverage import report
from app.planning import retailers
from app.planning.grocery_estimator import GroceryEstimator, ProductMatcher, choose_product, priceable_ingredients
from app.planning.retailers import SECOND_STORES, fairprice_only, retailer_of, store_products
from app.schemas.product import GroceryLineEstimate
from tests.test_fairprice_cart import item, prepare, put_lines
from tests.test_out_of_stock_swap import ONE_TOFU, mains, week
from tests.test_planning_capability import dish_client
from tests.test_redmart_planning import entry
from tests.test_redmart_planning import stores as stores  # noqa: F401  (the fake FairPrice, Cold Storage, RedMart)

# Midnight Singapore time on 2026-11-02, as the export writes it.
OBSERVED = "2026-11-02T00:00:00+08:00"


def manual_entry(external_id: str, price: float, platform: str = "shopee", *, in_stock: bool = True) -> dict:
    """What `manual_prices.py export` writes for one ingredient: no brand, category or query."""
    product = entry(external_id, price, in_stock=in_stock)["products"][0]
    for key in ("brand", "category", "query"):
        del product[key]
    return {"status": "mapped", "products": [{**product, "retailer": platform, "fetched_at": OBSERVED}]}


@pytest.fixture
def manual(stores, monkeypatch):  # noqa: F811
    snapshot: dict[str, dict] = {}
    monkeypatch.setattr(retailers, "manual_snapshot", lambda: snapshot)
    return snapshot


class NoSearch:
    """A product service that fails the test if anything is searched live."""

    def search(self, *args, **kwargs):
        raise AssertionError("a hand-recorded price is never searched live")


def choose(name: str = "flour", *, halal: bool = False, live: bool = False):
    return choose_product(NoSearch(), ProductMatcher(), name, name, "g", live=live, quantity=300, requires_halal=halal)


def line(name: str, product) -> GroceryLineEstimate:
    return GroceryEstimator.price_line(name, name, 300, "g", 0.0, 300, product, None)


def test_manual_is_the_last_layer_and_an_absent_snapshot_is_empty() -> None:
    assert SECOND_STORES[-1] == "manual"
    retailers.manual_snapshot.cache_clear()
    assert retailers.manual_snapshot() == {}


def test_the_snapshot_file_is_read_with_whole_cent_prices_and_a_default_status(tmp_path, monkeypatch) -> None:
    product = {**manual_entry("mn-1-1", 4.0)["products"][0], "price_sgd": 4.000000001}
    (tmp_path / "products").mkdir()
    (tmp_path / retailers.MANUAL_SNAPSHOT_FILE).write_text(
        json.dumps({"snapshot_version": "manual-v1", "ingredients": {"flour": {"products": [product]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(retailers, "data_root", lambda: tmp_path)
    retailers.manual_snapshot.cache_clear()
    try:
        entry_ = store_products("manual")["flour"]
    finally:
        retailers.manual_snapshot.cache_clear()

    assert (entry_["status"], entry_["products"][0]["price_sgd"]) == ("mapped", 4.0)


@pytest.mark.parametrize("earlier", ["fairprice", "cold_storage", "redmart"])
def test_manual_is_used_only_when_no_earlier_store_has_a_product_in_stock(stores, manual, earlier) -> None:  # noqa: F811
    fairprice, cold_storage, redmart = stores
    mapping = {"fairprice": fairprice, "cold_storage": cold_storage, "redmart": redmart}[earlier]
    manual["flour"] = manual_entry("mn-1-1", 0.5)

    mapping["flour"] = entry("x-1", 9.0)
    assert choose().product.external_id == "x-1"  # never because it is cheaper

    mapping["flour"] = entry("x-1", 9.0, in_stock=False)
    assert choose().product.external_id == "mn-1-1"


def test_a_line_is_bought_where_it_was_recorded_and_says_so(stores, manual) -> None:  # noqa: F811
    manual["flour"] = manual_entry("mn-1-1", 4.0, "shopee")
    manual["sugar"] = manual_entry("mn-2-1", 2.0, "redmart")
    manual["agar"] = manual_entry("mn-3-1", 3.0, "other")

    flour = choose("flour")
    assert (flour.product.source, flour.product.retailer, retailer_of(flour.product)) == ("manual", "shopee", "shopee")
    assert flour.product.halal_certified is None
    assert (flour.evidence.source, flour.evidence.mode) == ("manual", "snapshot")
    assert flour.evidence.fetched_at.isoformat() == OBSERVED

    flour_line = line("flour", flour.product)
    assert flour_line.retailer == "shopee"
    assert flour_line.note == "No store we read sells this; price recorded by hand on 2026-11-02."
    assert flour_line.packages_required == 1
    # A manual RedMart row groups with RedMart's own lines; an unnamed platform is "other".
    assert line("sugar", choose("sugar").product).retailer == "redmart"
    assert line("agar", choose("agar").product).retailer == "other"


def test_a_hand_recorded_line_goes_into_the_evidence_packet_the_agent_saves(stores, manual) -> None:  # noqa: F811
    """A line priced from Shopee, Lazada, Amazon or another site is evidence a person recorded: the packet that
    confirming a plan saves (`AgentSessionService._grocery_evidence`) refused every platform but RedMart."""
    from types import SimpleNamespace

    from app.retrieval.evidence import grocery_packet
    from app.services.agent import AgentSessionService

    lines = []
    for number, platform in enumerate(("shopee", "lazada", "amazon", "other", "redmart"), start=1):
        name = f"item{number}"
        manual[name] = manual_entry(f"mn-{number}-1", 2.0, platform)
        choice = choose(name)
        lines.append(line(name, choice.product).model_copy(update={"evidence": choice.evidence}))
    total = round(sum(line.purchase_cost_sgd for line in lines), 2)
    estimate = SimpleNamespace(items=lines, pricing_mode="snapshot", purchase_total_sgd=total)

    packet = grocery_packet(estimate)
    evidence = AgentSessionService._grocery_evidence(estimate)

    assert [line.retailer for line in lines] == ["shopee", "lazada", "amazon", "other", "redmart"]
    assert {item.source for item in packet.items} == {"manual"}
    assert (evidence["items"], evidence["modes"], evidence["unsupported_claims"]) == (5, ["snapshot"], [])


def test_a_hand_recorded_price_is_never_searched_live(stores, manual) -> None:  # noqa: F811
    manual["flour"] = manual_entry("mn-1-1", 4.0)

    choice = choose(live=True)

    assert (choice.product.external_id, choice.evidence.mode) == ("mn-1-1", "snapshot")
    assert choice.warnings == []


def test_halal_is_never_taken_from_the_hand_recorded_prices(stores, manual) -> None:  # noqa: F811
    manual["beef"] = manual_entry("mn-5-1", 12.0)
    manual["flour"] = manual_entry("mn-1-1", 4.0)

    assert choose("beef", halal=True).product is None
    assert choose("beef").product.external_id == "mn-5-1"
    assert choose("flour", halal=True).product.external_id == "mn-1-1"


def test_fairprice_only_hides_the_hand_recorded_prices(stores, manual) -> None:  # noqa: F811
    manual["flour"] = manual_entry("mn-1-1", 4.0)

    assert "flour" in priceable_ingredients()
    with fairprice_only():
        assert store_products("manual") == {}
        assert "flour" not in priceable_ingredients()
        assert choose().product is None
    assert choose().product is not None


@pytest.fixture
def plan_client(monkeypatch):
    with dish_client(monkeypatch, mains(*ONE_TOFU)) as client:
        yield client, week(client)["id"]


def manual_item(name, price, platform="shopee", *, packages=1):
    row = item(name, external_id="mn-1-1", price=price, packages=packages, source="manual")
    row.product_url = f"https://shopee.sg/{name}"
    row.retailer = platform
    return row


def test_a_saved_plan_keeps_the_platform_of_a_hand_recorded_line(plan_client) -> None:
    client, plan_id = plan_client
    unnamed = item("gum", external_id="mn-9-1", price=1.0, source="manual")
    put_lines(plan_id, [manual_item("agar", 4.0, "shopee"), unnamed])

    saved = client.get(f"/api/plans/{plan_id}").json()["grocery_estimate"]["items"]

    assert [(row["retailer"], row["product"]["source"]) for row in saved] == [("shopee", "manual"), ("other", "manual")]


def test_the_cart_reports_each_platform_apart_after_the_stores(plan_client) -> None:
    client, plan_id = plan_client
    put_lines(
        plan_id,
        [
            manual_item("amaranth", 2.0, "amazon"),
            manual_item("agar", 4.0, "shopee", packages=2),
            manual_item("kombu", 1.5, "redmart"),
            manual_item("miso", 3.0, "shopee"),
            manual_item("yuzu", 3.0, "lazada", packages=0),  # not bought: no entry
        ],
    )

    body = prepare(client, plan_id)

    assert body["lines"] == []
    assert body["other_stores"] == [
        {"retailer": "redmart", "lines": 1, "purchase_total_sgd": 1.5},
        {"retailer": "shopee", "lines": 2, "purchase_total_sgd": 11.0},
        {"retailer": "amazon", "lines": 1, "purchase_total_sgd": 2.0},
    ]


def test_the_coverage_counts_what_only_the_hand_recorded_prices_price() -> None:
    mapped = {"status": "mapped", "products": [{}]}
    names = {"a", "b", "c", "d"}

    result = report([], names, {"a": mapped}, {"b": mapped}, {"c": mapped}, {"a": mapped, "c": mapped, "d": mapped})

    ingredients = result["ingredients"]
    assert (ingredients["manual_only"], ingredients["redmart_only"], ingredients["combined"]) == (1, 1, 4)
    assert ingredients["manual_only_share"] == 0.25
    # A call without a manual mapping still works.
    assert report([], names, {"a": mapped}, {}, {})["ingredients"]["manual_only"] == 0


def test_the_final_price_check_leaves_a_hand_recorded_line_alone(stores, manual) -> None:  # noqa: F811
    """The check before the cart re-prices FairPrice lines only; a hand-recorded price keeps its date and evidence."""
    from tests.test_redmart_planning import live_service

    manual["flour"] = manual_entry("mn-1-1", 4.0)
    service, providers, _ = live_service()
    product = choose().product
    assert product.source == "manual"
    recorded = GroceryEstimator.price_line("flour", "flour", 300, "g", 0.0, 300, product, None)

    (checked,) = service.refresh_selected([recorded])

    assert all(provider.calls == [] for provider in providers.values())
    assert checked.product == recorded.product and checked.evidence == recorded.evidence
