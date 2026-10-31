"""Cold Storage as the second retailer (docs/design/cold-storage.md): FairPrice first, Cold Storage only as the fill."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.planning import grocery_estimator, retailers
from app.planning.grocery_estimator import GroceryEstimator, ProductMatcher, choose_product, priceable_ingredients
from app.planning.retailers import cold_storage_products, fairprice_only, retailer_of
from app.products.provider import ProductProviderError
from app.retrieval.evidence import grocery_packet
from app.schemas.product import ProductResponse
from app.services.product import LIVE_FAILURE_LIMIT, LIVE_LOOKUP_BUDGET, ProductSearchService

FETCHED = "2026-10-31T00:00:00+00:00"


def entry(external_id: str, price: float, *, in_stock: bool = True, grams: float = 500, status: str = "mapped") -> dict:
    return {
        "status": status,
        "review_status": "proposed",
        "products": [
            {
                "external_id": external_id,
                "name": f"Product {external_id}",
                "brand": None,
                "category": None,
                "package_grams": grams,
                "package_grams_basis": "name",
                "price_sgd": price,
                "product_url": f"https://example.test/{external_id}",
                "in_stock": in_stock,
                "query": f"query {external_id}",
                "fetched_at": FETCHED,
            }
        ],
    }


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch):
    """FairPrice's mapping and Cold Storage's, both fake and both swappable; the curated matcher is off."""
    fairprice: dict[str, dict] = {}
    cold_storage: dict[str, dict] = {}
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset())
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: fairprice)
    monkeypatch.setattr(retailers, "cold_storage_snapshot", lambda: cold_storage)
    monkeypatch.setattr(retailers, "overrides", lambda kind: {})
    return fairprice, cold_storage


def offline_service() -> ProductSearchService:
    return ProductSearchService(fixture_provider=None, live_provider=None, repository=None, cache_ttl_minutes=0)


def choose(name: str = "flour", *, quantity: float = 300, halal: bool = False, service=None, live: bool = False):
    return choose_product(
        service or offline_service(),
        ProductMatcher(),
        name,
        name,
        "g",
        live=live,
        quantity=quantity,
        requires_halal=halal,
    )


def test_a_fairprice_product_in_stock_wins_even_when_it_costs_more(stores) -> None:
    fairprice, cold_storage = stores
    fairprice["flour"] = entry("1001", 9.0)
    cold_storage["flour"] = entry("cs-1", 1.0)

    choice = choose()

    assert choice.product.external_id == "1001"
    assert retailer_of(choice.product) == "fairprice"
    assert choice.evidence.source == "release_snapshot"


@pytest.mark.parametrize(
    "fairprice_entry",
    [None, entry("1001", 9.0, status="unavailable"), entry("1001", 9.0, in_stock=False)],
    ids=["no mapping", "mapping not mapped", "none in stock"],
)
def test_cold_storage_fills_what_fairprice_has_no_product_for(stores, fairprice_entry) -> None:
    fairprice, cold_storage = stores
    if fairprice_entry is not None:
        fairprice["flour"] = fairprice_entry
    cold_storage["flour"] = entry("cs-1", 4.0)

    choice = choose()

    assert choice.product.external_id == "cs-1"
    assert choice.product.source == "cold_storage"
    assert retailer_of(choice.product) == "cold_storage"
    assert choice.product.halal_certified is None
    assert choice.evidence.source == "cold_storage"
    assert choice.evidence.mode == "snapshot"
    assert choice.evidence.parser_version == "cold-storage-capture-v1"


def test_cold_storage_takes_the_cheapest_in_stock_product_for_the_quantity(stores) -> None:
    _, cold_storage = stores
    cold_storage["flour"] = entry("cs-1", 4.0)
    cold_storage["flour"]["products"] += [
        {**entry("cs-2", 2.5, grams=1000)["products"][0]},
        {**entry("cs-3", 0.5, in_stock=False)["products"][0]},
    ]

    assert choose(quantity=300).product.external_id == "cs-2"


def test_an_ingredient_neither_store_maps_stays_unpriced(stores) -> None:
    _, cold_storage = stores
    cold_storage["chervil"] = entry("cs-9", 3.0, status="unavailable")

    assert choose("chervil").product is None
    assert choose("sage").product is None


def test_a_halal_household_never_gets_a_cold_storage_line_that_needs_certification(stores) -> None:
    _, cold_storage = stores
    cold_storage["beef"] = entry("cs-5", 12.0)
    cold_storage["flour"] = entry("cs-1", 4.0)

    assert choose("beef", halal=True).product is None
    assert choose("beef", halal=False).product.external_id == "cs-5"
    # A line that needs no certification is still bought there.
    assert choose("flour", halal=True).product.external_id == "cs-1"


def test_fairprice_only_hides_cold_storage(stores) -> None:
    _, cold_storage = stores
    cold_storage["flour"] = entry("cs-1", 4.0)

    assert "flour" in priceable_ingredients()
    assert choose().product is not None
    with fairprice_only():
        assert cold_storage_products() == {}
        assert "flour" not in priceable_ingredients()
        assert choose().product is None
    assert "flour" in priceable_ingredients()


def test_only_mapped_removed_and_override_entries_count(stores, monkeypatch: pytest.MonkeyPatch) -> None:
    _, cold_storage = stores
    cold_storage["flour"] = entry("cs-1", 4.0)
    cold_storage["sugar"] = entry("cs-2", 2.0, status="unavailable")
    cold_storage["rice"] = entry("cs-3", 3.0)
    monkeypatch.setattr(
        retailers,
        "overrides",
        lambda kind: {"rice": {"status": "removed"}} if kind == "product_mapping:cold_storage" else {},
    )

    assert set(cold_storage_products()) == {"flour", "sugar"}
    assert "sugar" not in priceable_ingredients() and "flour" in priceable_ingredients()


def test_the_grocery_line_names_its_store_and_a_cold_storage_line_says_why(stores) -> None:
    fairprice, cold_storage = stores
    fairprice["flour"] = entry("1001", 3.0)
    cold_storage["sugar"] = entry("cs-2", 2.0)

    def line(name: str):
        product = choose(name).product
        return GroceryEstimator.price_line(name, name, 300, "g", 0.0, 300, product, None)

    assert (line("flour").retailer, line("flour").note) == ("fairprice", None)
    cold = line("sugar")
    assert cold.retailer == "cold_storage"
    assert cold.note == "FairPrice has no product for this; bought at Cold Storage."
    assert cold.packages_required == 1


def test_the_evidence_packet_names_the_store_of_each_line(stores) -> None:
    fairprice, cold_storage = stores
    fairprice["flour"] = entry("1001", 3.0)
    cold_storage["sugar"] = entry("cs-2", 2.0)
    lines = []
    for name in ("flour", "sugar"):
        choice = choose(name)
        line = GroceryEstimator.price_line(name, name, 300, "g", 0.0, 300, choice.product, None)
        lines.append(line.model_copy(update={"evidence": choice.evidence}))

    packet = grocery_packet(SimpleNamespace(items=lines, pricing_mode="snapshot"))

    assert [(item.source, item.external_id) for item in packet.items] == [
        ("fairprice", "1001"),
        ("cold_storage", "cs-2"),
    ]


class Provider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name, self.fail, self.calls = name, fail, []

    def search(self, query: str, *, limit: int, timeout_seconds=None):
        self.calls.append(query)
        if self.fail:
            raise ProductProviderError("down")
        source = "cold_storage" if self.name == "cold" else "fairprice"
        prefix = "cs-" if source == "cold_storage" else ""
        return [
            ProductResponse(
                external_id=f"{prefix}{number}",
                name=f"{self.name} {query} {number}",
                brand=None,
                category=None,
                package_size=500,
                package_unit="g",
                price_sgd=1.5 * number,
                product_url="https://example.test/p",
                image_url=None,
                in_stock=True,
                source=source,
                fetched_at=datetime.now(UTC),
            )
            for number in (1, 2)
        ]


class Repository:
    def __init__(self) -> None:
        self.writes: list[dict] = []

    def get_fresh(self, *, source, search_query, **kwargs):
        return [
            item
            for write in self.writes
            if write["source"] == source and write["search_query"] == search_query
            for item in write["products"]
        ]

    def replace_query_results(self, **kwargs) -> None:
        self.writes.append(kwargs)


def live_service(*, cold_fails: bool = False) -> tuple[ProductSearchService, Provider, Provider, Repository]:
    fairprice, cold, repository = Provider("fairprice"), Provider("cold", fail=cold_fails), Repository()
    service = ProductSearchService(
        fixture_provider=None,
        live_provider=fairprice,
        repository=repository,
        cache_ttl_minutes=15,
        cold_storage_provider=cold,
        cold_storage_cache_ttl_minutes=30,
    )
    return service, fairprice, cold, repository


def test_a_live_cold_storage_search_uses_its_own_provider_and_cache_source() -> None:
    service, fairprice, cold, repository = live_service()

    response = service.search("Chervil", live=True, retailer="cold_storage")

    assert cold.calls == ["chervil"] and fairprice.calls == []
    assert response.provider_used == "cold_storage"
    assert [item.external_id for item in response.items] == ["cs-1", "cs-2"]
    assert repository.writes[0]["source"] == "cold_storage"
    assert response.retrieval.requested_source == "cold_storage"
    assert response.retrieval.parser_version == "cold-storage-flight-v1"
    # The same query again is the cache, under the same source, without another request.
    again = service.search("chervil", live=True, retailer="cold_storage")
    assert again.cached and cold.calls == ["chervil"]
    # FairPrice's cache for the same words is separate.
    assert service.search("chervil", live=True).provider_used == "fairprice"
    assert [write["source"] for write in repository.writes] == ["cold_storage", "fairprice"]


def test_cold_storage_has_its_own_lookup_budget_and_failure_count() -> None:
    service, fairprice, cold, _ = live_service()
    for number in range(LIVE_LOOKUP_BUDGET + 3):
        service.search(f"query {number}", live=True, retailer="cold_storage")
    assert len(cold.calls) == LIVE_LOOKUP_BUDGET and fairprice.calls == []
    assert service.search("fresh query", live=True).provider_used == "fairprice"

    failing, fairprice, cold, _ = live_service(cold_fails=True)
    responses = [failing.search(f"query {number}", live=True, retailer="cold_storage") for number in range(6)]
    assert len(cold.calls) == LIVE_FAILURE_LIMIT
    assert all(response.items == [] and response.fallback_used for response in responses)
    assert "not asked again" in responses[-1].warning
    assert failing.search("fairprice query", live=True).provider_used == "fairprice"


def test_cold_storage_degrades_to_the_cache_and_then_to_nothing_never_to_fixtures() -> None:
    service, _, cold, repository = live_service()
    service.search("chervil", live=True, retailer="cold_storage")
    cold.fail = True

    stale = service.search("chervil", live=True, refresh=True, retailer="cold_storage")
    assert stale.cached and stale.fallback_used and stale.retrieval.status == "degraded"

    nothing = service.search("tarragon", live=True, retailer="cold_storage")
    assert (nothing.items, nothing.provider_used, nothing.retrieval.status) == ([], "cold_storage", "unavailable")
    # Offline there are no Cold Storage fixtures: its products come from the snapshot.
    offline = service.search("chervil", live=False, retailer="cold_storage")
    assert offline.items == [] and offline.provider_used == "cold_storage"
    assert repository.writes  # only the one successful live lookup was ever saved


def test_a_live_choice_refreshes_the_reviewed_cold_storage_products_and_keeps_only_those(stores) -> None:
    _, cold_storage = stores
    cold_storage["flour"] = entry("cs-2", 9.0)  # the snapshot says 9.00; the shelf now says 3.00
    service, fairprice, cold, _ = live_service()

    choice = choose(service=service, live=True)

    assert cold.calls == ["query cs 2"] and fairprice.calls == []
    assert choice.product.external_id == "cs-2"
    assert choice.product.price_sgd == 3.0
    assert (choice.evidence.source, choice.evidence.mode) == ("cold_storage", "live")

    # A live search that does not return the reviewed id leaves the line unpriced, with a warning.
    cold_storage["flour"] = entry("cs-77", 9.0)
    missing = choose(service=live_service()[0], live=True)
    assert missing.product is None
    assert any("did not return a reviewed product" in warning for warning in missing.warnings)


def test_the_budget_half_takes_dishes_fairprice_alone_supplies_before_cheaper_ones_that_need_cold_storage():
    """A soup whose broth comes from Cold Storage is cheap as used and dear in whole packages; FairPrice stays the
    main store, so the budget half orders the dishes FairPrice alone supplies first (docs/design/cold-storage.md)."""
    from types import SimpleNamespace

    from app.planning.product_path import cheap_first

    def dish(cost, *retailers):
        items = [SimpleNamespace(retailer=r) for r in retailers]
        estimate = SimpleNamespace(consumed_total_sgd=cost, purchase_total_sgd=cost, items=items)
        return SimpleNamespace(grocery_estimate=estimate)

    cold_soup, fairprice_soup, plain = dish(2.0, "fairprice", "cold_storage"), dish(3.0, "fairprice"), dish(4.0)
    assert sorted([cold_soup, plain, fairprice_soup], key=cheap_first) == [fairprice_soup, plain, cold_soup]
    # An estimate without lines (a stand-in in other tests) keeps the plain cost order.
    assert cheap_first(SimpleNamespace(grocery_estimate=SimpleNamespace(consumed_total_sgd=1.0))) == (False, 1.0)
