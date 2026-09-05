from pathlib import Path

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
