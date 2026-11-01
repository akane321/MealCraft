"""RedMart, the third retailer (docs/design/redmart.md): FairPrice, then Cold Storage, then RedMart, never by price."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.planning import grocery_estimator, retailers
from app.planning.grocery_estimator import GroceryEstimator, ProductMatcher, choose_product, priceable_ingredients
from app.planning.retailers import SECOND_STORES, fairprice_only, retailer_of, store_products
from app.products.provider import ProductProviderError
from app.retrieval.evidence import grocery_packet
from app.schemas.product import ProductResponse
from app.services.product import LIVE_LOOKUP_BUDGET, REDMART_FAILURE_LIMIT, ProductSearchService

FETCHED = "2026-11-01T00:00:00+00:00"


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
    """The three mappings, all fake and swappable; the curated matcher is off."""
    fairprice: dict[str, dict] = {}
    cold_storage: dict[str, dict] = {}
    redmart: dict[str, dict] = {}
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset())
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: fairprice)
    monkeypatch.setattr(retailers, "cold_storage_snapshot", lambda: cold_storage)
    monkeypatch.setattr(retailers, "redmart_snapshot", lambda: redmart)
    monkeypatch.setattr(retailers, "overrides", lambda kind: {})
    return fairprice, cold_storage, redmart


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


def test_the_fill_order_is_fairprice_then_cold_storage_then_redmart_then_the_hand_recorded_prices() -> None:
    assert SECOND_STORES == ("cold_storage", "redmart", "manual")


def test_a_fairprice_product_in_stock_wins_even_when_redmart_is_far_cheaper(stores) -> None:
    fairprice, cold_storage, redmart = stores
    fairprice["flour"] = entry("1001", 9.0)
    cold_storage["flour"] = entry("cs-1", 8.0)
    redmart["flour"] = entry("rm-1", 0.5)

    choice = choose()

    assert (choice.product.external_id, retailer_of(choice.product)) == ("1001", "fairprice")


def test_cold_storage_beats_a_cheaper_redmart(stores) -> None:
    _, cold_storage, redmart = stores
    cold_storage["flour"] = entry("cs-1", 8.0)
    redmart["flour"] = entry("rm-1", 0.5)

    assert choose().product.external_id == "cs-1"


@pytest.mark.parametrize(
    "cold_entry",
    [None, entry("cs-1", 8.0, status="unavailable"), entry("cs-1", 8.0, in_stock=False)],
    ids=["no Cold Storage mapping", "mapping not mapped", "none in stock"],
)
def test_redmart_fills_what_neither_fairprice_nor_cold_storage_prices(stores, cold_entry) -> None:
    fairprice, cold_storage, redmart = stores
    fairprice["flour"] = entry("1001", 9.0, in_stock=False)
    if cold_entry is not None:
        cold_storage["flour"] = cold_entry
    redmart["flour"] = entry("rm-1", 4.0)

    choice = choose()

    assert choice.product.external_id == "rm-1"
    assert (choice.product.source, retailer_of(choice.product)) == ("redmart", "redmart")
    assert choice.product.halal_certified is None
    assert (choice.evidence.source, choice.evidence.mode) == ("redmart", "snapshot")
    assert choice.evidence.parser_version == "redmart-capture-v1"


def test_redmart_takes_the_cheapest_in_stock_product_for_the_quantity(stores) -> None:
    _, _, redmart = stores
    redmart["flour"] = entry("rm-1", 4.0)
    redmart["flour"]["products"] += [
        entry("rm-2", 2.5, grams=1000)["products"][0],
        entry("rm-3", 0.5, in_stock=False)["products"][0],
    ]

    assert choose(quantity=300).product.external_id == "rm-2"


def test_an_ingredient_no_store_maps_stays_unpriced(stores) -> None:
    _, _, redmart = stores
    redmart["chervil"] = entry("rm-9", 3.0, status="unavailable")

    assert choose("chervil").product is None
    assert choose("sage").product is None


def test_halal_is_never_taken_from_a_second_store(stores) -> None:
    _, cold_storage, redmart = stores
    redmart["beef"] = entry("rm-5", 12.0)
    redmart["flour"] = entry("rm-1", 4.0)

    assert choose("beef", halal=True).product is None
    assert choose("beef", halal=False).product.external_id == "rm-5"
    # A line that needs no certification is still bought there.
    assert choose("flour", halal=True).product.external_id == "rm-1"


def test_fairprice_only_hides_redmart_as_well(stores) -> None:
    _, _, redmart = stores
    redmart["flour"] = entry("rm-1", 4.0)

    assert "flour" in priceable_ingredients()
    assert choose().product is not None
    with fairprice_only():
        assert store_products("redmart") == {} and store_products("cold_storage") == {}
        assert "flour" not in priceable_ingredients()
        assert choose().product is None
    assert "flour" in priceable_ingredients()


def test_redmart_entries_are_mapped_removed_or_overridden_like_the_others(stores, monkeypatch) -> None:
    _, _, redmart = stores
    redmart["flour"] = entry("rm-1", 4.0)
    redmart["sugar"] = entry("rm-2", 2.0, status="unavailable")
    redmart["rice"] = entry("rm-3", 3.0)
    monkeypatch.setattr(
        retailers,
        "overrides",
        lambda kind: {"rice": {"status": "removed"}} if kind == "product_mapping:redmart" else {},
    )

    assert set(store_products("redmart")) == {"flour", "sugar"}
    assert "sugar" not in priceable_ingredients() and "flour" in priceable_ingredients()


def test_the_grocery_line_names_its_store_and_a_redmart_line_says_why(stores) -> None:
    fairprice, cold_storage, redmart = stores
    fairprice["flour"] = entry("1001", 3.0)
    cold_storage["rice"] = entry("cs-3", 3.0)
    redmart["sugar"] = entry("rm-2", 2.0)

    def line(name: str):
        return GroceryEstimator.price_line(name, name, 300, "g", 0.0, 300, choose(name).product, None)

    assert (line("flour").retailer, line("flour").note) == ("fairprice", None)
    assert line("rice").retailer == "cold_storage"
    sugar = line("sugar")
    assert sugar.retailer == "redmart"
    assert sugar.note == "FairPrice and Cold Storage have no product for this; bought at RedMart."
    assert sugar.packages_required == 1


def test_the_evidence_packet_names_the_store_of_each_line(stores) -> None:
    fairprice, _, redmart = stores
    fairprice["flour"] = entry("1001", 3.0)
    redmart["sugar"] = entry("rm-2", 2.0)
    lines = []
    for name in ("flour", "sugar"):
        choice = choose(name)
        line = GroceryEstimator.price_line(name, name, 300, "g", 0.0, 300, choice.product, None)
        lines.append(line.model_copy(update={"evidence": choice.evidence}))

    packet = grocery_packet(SimpleNamespace(items=lines, pricing_mode="snapshot"))

    assert [(item.source, item.external_id) for item in packet.items] == [("fairprice", "1001"), ("redmart", "rm-2")]


class Provider:
    PREFIX = {"fairprice": "", "cold": "cs-", "redmart": "rm-"}
    SOURCE = {"fairprice": "fairprice", "cold": "cold_storage", "redmart": "redmart"}

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name, self.fail, self.calls, self.limits = name, fail, [], []

    def search(self, query: str, *, limit: int, timeout_seconds=None):
        self.calls.append(query)
        self.limits.append(limit)
        if self.fail:
            raise ProductProviderError("down")
        return [
            ProductResponse(
                external_id=f"{self.PREFIX[self.name]}{number}",
                name=f"{self.name} {query} {number}",
                brand=None,
                category=None,
                package_size=500,
                package_unit="g",
                price_sgd=1.5 * number,
                product_url="https://example.test/p",
                image_url=None,
                in_stock=True,
                source=self.SOURCE[self.name],
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


def live_service(*, redmart_fails: bool = False):
    providers = {name: Provider(name) for name in ("fairprice", "cold")}
    providers["redmart"] = Provider("redmart", fail=redmart_fails)
    repository = Repository()
    service = ProductSearchService(
        fixture_provider=None,
        live_provider=providers["fairprice"],
        repository=repository,
        cache_ttl_minutes=15,
        cold_storage_provider=providers["cold"],
        cold_storage_cache_ttl_minutes=30,
        redmart_provider=providers["redmart"],
        redmart_cache_ttl_minutes=45,
    )
    return service, providers, repository


def test_a_live_redmart_search_uses_its_own_provider_cache_source_and_parser() -> None:
    service, providers, repository = live_service()

    response = service.search("Chervil", live=True, retailer="redmart")

    assert providers["redmart"].calls == ["chervil"]
    assert providers["fairprice"].calls == providers["cold"].calls == []
    assert response.provider_used == "redmart"
    assert [item.external_id for item in response.items] == ["rm-1", "rm-2"]
    assert repository.writes[0]["source"] == "redmart"
    assert (response.retrieval.requested_source, response.retrieval.parser_version) == ("redmart", "redmart-ajax-v1")
    # The same query again is RedMart's cache, without another request; the other stores' caches stay apart.
    assert service.search("chervil", live=True, retailer="redmart").cached
    assert providers["redmart"].calls == ["chervil"]
    assert service.search("chervil", live=True).provider_used == "fairprice"
    assert [write["source"] for write in repository.writes] == ["redmart", "fairprice"]


def test_redmart_has_its_own_lookup_budget_and_failure_count() -> None:
    service, providers, _ = live_service()
    for number in range(LIVE_LOOKUP_BUDGET + 3):
        service.search(f"query {number}", live=True, retailer="redmart")
    assert len(providers["redmart"].calls) == LIVE_LOOKUP_BUDGET
    assert service.search("fresh query", live=True).provider_used == "fairprice"
    assert service.search("fresh query", live=True, retailer="cold_storage").items

    # RedMart is asked nothing more after its first failure (ADR-0110 item 2), where the other stores allow three.
    failing, providers, _ = live_service(redmart_fails=True)
    responses = [failing.search(f"query {number}", live=True, retailer="redmart") for number in range(6)]
    assert len(providers["redmart"].calls) == REDMART_FAILURE_LIMIT == 1
    assert all(response.items == [] and response.fallback_used for response in responses)
    assert "not asked again" in responses[-1].warning
    assert failing.search("other query", live=True, retailer="cold_storage").items


def test_redmart_degrades_to_the_cache_and_then_to_nothing_never_to_fixtures() -> None:
    service, providers, _ = live_service()
    service.search("chervil", live=True, retailer="redmart")
    providers["redmart"].fail = True

    stale = service.search("chervil", live=True, refresh=True, retailer="redmart")
    assert stale.cached and stale.fallback_used and stale.retrieval.status == "degraded"
    nothing = service.search("tarragon", live=True, retailer="redmart")
    assert (nothing.items, nothing.provider_used, nothing.retrieval.status) == ([], "redmart", "unavailable")
    offline = service.search("chervil", live=False, retailer="redmart")
    assert offline.items == [] and offline.provider_used == "redmart"


def test_a_live_choice_refreshes_the_reviewed_redmart_products_with_a_limit_of_40(stores) -> None:
    _, _, redmart = stores
    redmart["flour"] = entry("rm-2", 9.0)  # the snapshot says 9.00; the shelf now says 3.00
    service, providers, _ = live_service()

    choice = choose(service=service, live=True)

    assert providers["redmart"].calls == ["query rm 2"] and providers["redmart"].limits == [40]
    assert providers["fairprice"].calls == []
    assert choice.product.external_id == "rm-2" and choice.product.price_sgd == 3.0
    assert (choice.evidence.source, choice.evidence.mode) == ("redmart", "live")

    # A live search that does not return the reviewed id leaves the line unpriced, with a warning.
    redmart["flour"] = entry("rm-77", 9.0)
    missing = choose(service=live_service()[0], live=True)
    assert missing.product is None
    assert any("RedMart search did not return a reviewed product" in warning for warning in missing.warnings)


def test_a_live_choice_searches_each_query_the_reviewed_products_were_captured_with(stores) -> None:
    """Gochugaru's products came from "gochugaru" (page 2) and "korean chili powder": the first query's page alone
    returned none of them, and the line went to a later store although RedMart stocks it."""
    _, _, redmart = stores
    first, second = entry("rm-7", 9.0)["products"][0], entry("rm-2", 9.0)["products"][0]
    redmart["flour"] = {"status": "mapped", "products": [first, {**second, "query": "korean chili powder"}]}
    service, providers, _ = live_service()

    choice = choose(service=service, live=True)

    assert providers["redmart"].calls == ["query rm 7", "korean chili powder"]
    assert choice.product.external_id == "rm-2" and choice.product.price_sgd == 3.0
    assert choice.evidence.mode == "live"


def test_a_failed_live_search_keeps_the_reviewed_snapshot_price_and_no_later_store_fills_it(stores) -> None:
    """A store that cannot be read is not a store that has nothing: its reviewed prices of the snapshot date stand in
    (ADR-0110: live RedMart prices fail closed to the snapshot price)."""
    _, _, redmart = stores
    redmart["flour"] = entry("rm-2", 9.0)
    service, providers, _ = live_service(redmart_fails=True)

    choice = choose(service=service, live=True)

    assert providers["redmart"].calls == ["query rm 2"]
    assert (choice.product.external_id, choice.product.price_sgd, choice.evidence.mode) == ("rm-2", 9.0, "snapshot")
    assert any("could not be read live" in warning for warning in choice.warnings)


def test_a_live_choice_tries_redmart_after_cold_storage_found_nothing_reviewed(stores) -> None:
    _, cold_storage, redmart = stores
    cold_storage["flour"] = entry("cs-77", 1.0)  # the shelf does not return this id
    redmart["flour"] = entry("rm-1", 9.0)
    service, providers, _ = live_service()

    choice = choose(service=service, live=True)

    assert choice.product.external_id == "rm-1"
    assert providers["cold"].calls == ["query cs 77"] and providers["redmart"].calls == ["query rm 1"]


def test_a_redmart_line_is_never_rechecked_before_the_cart(stores) -> None:
    _, _, redmart = stores
    redmart["sugar"] = entry("rm-2", 2.0)
    service, providers, _ = live_service()
    product = choose("sugar").product
    line = GroceryEstimator.price_line("sugar", "sugar", 300, "g", 0.0, 300, product, None)

    (checked,) = service.refresh_selected([line])

    assert providers["fairprice"].calls == providers["redmart"].calls == []
    assert checked.product == line.product


def test_the_budget_half_ranks_any_second_store_line_after_fairprice_only_dishes() -> None:
    from app.planning.product_path import cheap_first

    def dish(cost, *retailers):
        estimate = SimpleNamespace(
            consumed_total_sgd=cost,
            purchase_total_sgd=cost,
            items=[SimpleNamespace(retailer=retailer) for retailer in retailers],
        )
        return SimpleNamespace(grocery_estimate=estimate)

    redmart_soup, cold_soup = dish(1.0, "fairprice", "redmart"), dish(2.0, "fairprice", "cold_storage")
    fairprice_soup, plain = dish(3.0, "fairprice"), dish(4.0)

    ranked = sorted([redmart_soup, cold_soup, plain, fairprice_soup], key=cheap_first)

    assert ranked == [fairprice_soup, plain, redmart_soup, cold_soup]
