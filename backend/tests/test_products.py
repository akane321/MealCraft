from pathlib import Path

import pytest

from app.core.paths import repository_root
from app.products.provider import FixtureProductProvider, ProductProviderError, parse_package_size
from app.services.product import ProductSearchService

FIXTURE_PATH = Path("data/fixtures/fairprice-products.json")


class FailingLiveProvider:
    def search(self, query: str, *, limit: int):
        raise ProductProviderError("simulated network failure")


class EmptyProductRepository:
    def get_fresh(self, **kwargs):
        return []

    def replace_query_results(self, **kwargs):
        raise AssertionError("fallback products must not be cached as live FairPrice data")


def test_parse_package_size_normalizes_mass_volume_and_multipacks() -> None:
    assert parse_package_size("1kg") == (1000.0, "g")
    assert parse_package_size("1.5 L") == (1500.0, "ml")
    assert parse_package_size("6 x 200ml") == (1200.0, "ml")
    assert parse_package_size("3 S") == (3.0, "whole")


def test_fixture_provider_maps_normalized_ingredient_queries() -> None:
    provider = FixtureProductProvider(str(FIXTURE_PATH))

    products = provider.search("cherry_tomatoes", limit=5)

    assert [product.external_id for product in products] == ["10762156"]
    assert products[0].package_size == 500
    assert products[0].package_unit == "g"


def test_live_failure_returns_explicit_fixture_fallback() -> None:
    service = ProductSearchService(
        fixture_provider=FixtureProductProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveProvider(),
        repository=EmptyProductRepository(),
        cache_ttl_minutes=15,
    )

    response = service.search("brown rice", live=True)

    assert response.provider_used == "fixture"
    assert response.fallback_used is True
    assert response.items[0].external_id == "fixture-brown-rice-1kg"
    assert "simulated network failure" in response.warning
    assert response.retrieval.requested_source == "fairprice"
    assert response.retrieval.status == "degraded"
    assert response.retrieval.mode == "fixture"
    assert response.retrieval.candidate_count == len(response.items)


class EmptyLiveProvider:
    def search(self, query: str, *, limit: int):
        return []


class StaleProductRepository:
    """Holds one snapshot older than any TTL; returns it only when asked for any age."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        product = FixtureProductProvider(str(FIXTURE_PATH)).search("brown rice", limit=1)[0]
        self.snapshot = product.model_copy(
            update={"source": "fairprice", "fetched_at": datetime(2026, 9, 1, 8, 0, tzinfo=UTC)}
        )

    def get_fresh(self, *, fetched_after, **kwargs):
        return [self.snapshot] if self.snapshot.fetched_at >= fetched_after else []

    def replace_query_results(self, **kwargs):
        raise AssertionError("nothing new was fetched, so nothing may be cached")


def test_an_empty_live_result_is_a_data_gap_not_a_failure() -> None:
    service = ProductSearchService(
        fixture_provider=FixtureProductProvider(str(FIXTURE_PATH)),
        live_provider=EmptyLiveProvider(),
        repository=EmptyProductRepository(),
        cache_ttl_minutes=15,
    )

    response = service.search("brown rice", live=True)

    # No sample prices are borrowed for an item FairPrice does not stock.
    assert response.items == []
    assert response.provider_used == "fairprice"
    assert response.fallback_used is False
    assert response.retrieval.status == "no_match"


def test_a_live_failure_uses_an_expired_cache_before_fixture_prices() -> None:
    service = ProductSearchService(
        fixture_provider=FixtureProductProvider(str(FIXTURE_PATH)),
        live_provider=FailingLiveProvider(),
        repository=StaleProductRepository(),
        cache_ttl_minutes=15,
    )

    response = service.search("brown rice", live=True)

    assert response.provider_used == "fairprice"
    assert response.cached is True
    assert response.fallback_used is True
    assert response.items[0].source == "fairprice"
    assert response.retrieval.mode == "cache"
    assert response.retrieval.status == "degraded"
    assert "saved on 01 Sep 2026" in response.warning


def test_a_search_page_without_a_product_key_parses_as_no_results(monkeypatch) -> None:
    import io
    import json

    from app.products import provider as provider_module

    page = {"props": {"pageProps": {"data": {"data": {"filters": []}}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(page)}</script>'

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(provider_module, "urlopen", lambda request, timeout: Response(html.encode("utf-8")))
    live = provider_module.FairPriceProductProvider(base_url="https://example.invalid", timeout_seconds=1)

    assert live.search("dragonfruit jam", limit=5) == []


PAGES = repository_root() / "data/fixtures/fairprice-pages"


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("ordinary", {"package_size": 500.0, "package_unit": "g", "package_warning": None, "in_stock": True}),
        ("promotion", {"price_sgd": 8.9, "regular_price_sgd": 11.5}),
        ("multipack", {"package_size": 800.0, "package_unit": "ml", "package_text": "4 x 200 ml"}),
        ("count-package", {"package_size": 10.0, "package_unit": "whole", "package_warning": "count_package"}),
        ("unavailable", {"in_stock": False}),
        ("missing-package", {"package_size": None, "package_warning": "unknown_package"}),
        ("empty-search", None),
        ("schema-drift-fields", "schema_drift"),
        ("schema-drift-no-data", "schema_drift"),
    ],
)
def test_every_fairprice_page_mode_has_a_named_outcome(page, expected) -> None:
    from app.products.provider import FairPriceProductProvider, ProductSchemaDriftError

    provider = FairPriceProductProvider(base_url="https://www.fairprice.com.sg", timeout_seconds=1)
    html = (PAGES / f"{page}.html").read_text(encoding="utf-8")
    if expected == "schema_drift":
        with pytest.raises(ProductSchemaDriftError) as raised:
            provider.parse_page(html, limit=5)
        assert raised.value.kind == "schema_drift"
        return
    products = provider.parse_page(html, limit=5)
    if expected is None:
        assert products == []  # FairPrice answered and has nothing: a data gap, not a failure
        return
    (product,) = products
    for field, value in expected.items():
        assert getattr(product, field) == value, field


class CountingLiveProvider:
    def __init__(self, fail: bool) -> None:
        self.calls = 0
        self.fail = fail

    def search(self, query: str, *, limit: int):
        self.calls += 1
        if self.fail:
            raise ProductProviderError("simulated network failure")
        return FixtureProductProvider(str(FIXTURE_PATH)).search("brown rice", limit=1)


class ForgetfulRepository(EmptyProductRepository):
    def replace_query_results(self, **kwargs):
        pass


def test_a_request_stops_asking_fairprice_after_three_failures_in_a_row() -> None:
    from app.services.product import LIVE_FAILURE_LIMIT

    live = CountingLiveProvider(fail=True)
    service = ProductSearchService(
        fixture_provider=FixtureProductProvider(str(FIXTURE_PATH)),
        live_provider=live,
        repository=EmptyProductRepository(),
        cache_ttl_minutes=15,
    )
    responses = [service.search(f"brown rice {n}", live=True) for n in range(8)]
    assert live.calls == LIVE_FAILURE_LIMIT
    assert all(response.provider_used == "fixture" for response in responses)
    assert "not asked again" in responses[-1].warning


def test_a_request_makes_at_most_its_budget_of_live_lookups() -> None:
    from app.services.product import LIVE_LOOKUP_BUDGET

    live = CountingLiveProvider(fail=False)
    service = ProductSearchService(
        fixture_provider=FixtureProductProvider(str(FIXTURE_PATH)),
        live_provider=live,
        repository=ForgetfulRepository(),
        cache_ttl_minutes=15,
    )
    for n in range(LIVE_LOOKUP_BUDGET + 5):
        service.search(f"brown rice {n}", live=True)
    assert live.calls == LIVE_LOOKUP_BUDGET
