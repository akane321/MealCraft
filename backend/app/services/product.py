from datetime import UTC, datetime, timedelta

from app.products.provider import (
    FairPriceProductProvider,
    FixtureProductProvider,
    ProductProviderError,
    normalize_search_text,
)
from app.repositories.product import ProductSnapshotRepository
from app.schemas.product import ProductSearchResponse
from app.schemas.retrieval import RetrievalTrace


def create_product_search_service(repository: ProductSnapshotRepository) -> "ProductSearchService":
    from app.core.config import get_settings

    settings = get_settings()
    return ProductSearchService(
        fixture_provider=FixtureProductProvider(settings.product_fixture_path),
        live_provider=FairPriceProductProvider(
            base_url=settings.fairprice_base_url,
            timeout_seconds=settings.fairprice_timeout_seconds,
        ),
        repository=repository,
        cache_ttl_minutes=settings.fairprice_cache_ttl_minutes,
    )


# One planning request can price hundreds of ingredients. Live FairPrice gets at most this many lookups
# per request, and none after this many failures in a row: the rest use the cache or sample prices, and
# say so, rather than keeping the household waiting 12 s per ingredient.
LIVE_LOOKUP_BUDGET = 60
LIVE_FAILURE_LIMIT = 3


class ProductSearchService:
    def __init__(
        self,
        *,
        fixture_provider: FixtureProductProvider,
        live_provider: FairPriceProductProvider,
        repository: ProductSnapshotRepository,
        cache_ttl_minutes: int,
    ) -> None:
        self.fixture_provider = fixture_provider
        self.live_provider = live_provider
        self.repository = repository
        self.cache_ttl_minutes = cache_ttl_minutes
        self.live_lookups = 0
        self.live_failures_in_a_row = 0

    def search(
        self,
        query: str,
        *,
        live: bool,
        refresh: bool = False,
        limit: int = 10,
    ) -> ProductSearchResponse:
        normalized_query = normalize_search_text(query)
        if not live:
            items = self.fixture_provider.search(normalized_query, limit=limit)
            return ProductSearchResponse(
                query=normalized_query,
                provider_used="fixture",
                fallback_used=False,
                cached=False,
                warning=None,
                items=items,
                retrieval=self._trace(
                    query=normalized_query,
                    provider_used="fixture",
                    mode="fixture",
                    status="success",
                    items=items,
                    parser_version="fairprice-fixture-v1",
                ),
            )

        if not refresh:
            fetched_after = datetime.now(UTC) - timedelta(minutes=self.cache_ttl_minutes)
            cached = self.repository.get_fresh(
                source="fairprice",
                search_query=normalized_query,
                fetched_after=fetched_after,
                limit=limit,
            )
            if cached:
                return ProductSearchResponse(
                    query=normalized_query,
                    provider_used="fairprice",
                    fallback_used=False,
                    cached=True,
                    warning=None,
                    items=cached,
                    retrieval=self._trace(
                        query=normalized_query,
                        provider_used="fairprice",
                        mode="cache",
                        status="success",
                        items=cached,
                        parser_version="fairprice-next-data-v1",
                    ),
                )

        try:
            if self.live_failures_in_a_row >= LIVE_FAILURE_LIMIT:
                raise ProductProviderError(
                    f"FairPrice failed {self.live_failures_in_a_row} times in a row; not asked again this time"
                )
            if self.live_lookups >= LIVE_LOOKUP_BUDGET:
                raise ProductProviderError(f"more than {LIVE_LOOKUP_BUDGET} live lookups in one request")
            self.live_lookups += 1
            try:
                items = self.live_provider.search(normalized_query, limit=limit)
            except ProductProviderError:
                self.live_failures_in_a_row += 1
                raise
            self.live_failures_in_a_row = 0
            if not items:
                # FairPrice answered and stocks nothing for this: a data gap, so the
                # line stays unpriced rather than borrowing sample prices.
                return ProductSearchResponse(
                    query=normalized_query,
                    provider_used="fairprice",
                    fallback_used=False,
                    cached=False,
                    warning=f"FairPrice has no product for '{normalized_query}'.",
                    items=[],
                    retrieval=self._trace(
                        query=normalized_query,
                        provider_used="fairprice",
                        mode="live",
                        status="no_match",
                        items=[],
                        parser_version="fairprice-next-data-v1",
                    ),
                )
            self.repository.replace_query_results(
                source="fairprice",
                search_query=normalized_query,
                products=items,
            )
            return ProductSearchResponse(
                query=normalized_query,
                provider_used="fairprice",
                fallback_used=False,
                cached=False,
                warning=None,
                items=items,
                retrieval=self._trace(
                    query=normalized_query,
                    provider_used="fairprice",
                    mode="live",
                    status="success",
                    items=items,
                    parser_version="fairprice-next-data-v1",
                ),
            )
        except ProductProviderError as error:
            # Live, then cache, then fixture (ADR-0022 section 2): an expired
            # snapshot of real prices is still better than sample prices.
            stale = self.repository.get_fresh(
                source="fairprice",
                search_query=normalized_query,
                fetched_after=datetime.min.replace(tzinfo=UTC),
                limit=limit,
            )
            if stale:
                saved = min(item.fetched_at for item in stale).strftime("%d %b %Y %H:%M UTC")
                return ProductSearchResponse(
                    query=normalized_query,
                    provider_used="fairprice",
                    fallback_used=True,
                    cached=True,
                    warning=f"Live FairPrice lookup was unavailable; prices saved on {saved} were used. ({error})",
                    items=stale,
                    retrieval=self._trace(
                        query=normalized_query,
                        provider_used="fairprice",
                        mode="cache",
                        status="degraded",
                        items=stale,
                        parser_version="fairprice-next-data-v1",
                        warning=f"{error.kind}: {error}",
                    ),
                )
            fallback_items = self.fixture_provider.search(normalized_query, limit=limit)
            return ProductSearchResponse(
                query=normalized_query,
                provider_used="fixture",
                fallback_used=True,
                cached=False,
                warning=f"Live FairPrice lookup was unavailable; stable fixture pricing was used. ({error})",
                items=fallback_items,
                retrieval=self._trace(
                    query=normalized_query,
                    provider_used="fixture",
                    mode="fixture",
                    status="degraded",
                    items=fallback_items,
                    parser_version="fairprice-fixture-v1",
                    warning=f"{error.kind}: {error}",
                ),
            )

    @staticmethod
    def _trace(
        *,
        query: str,
        provider_used: str,
        mode: str,
        status: str,
        items: list,
        parser_version: str,
        warning: str | None = None,
    ) -> RetrievalTrace:
        fetched_at = max((item.fetched_at for item in items), default=datetime.now(UTC))
        return RetrievalTrace(
            requested_source="fairprice",
            provider_used=provider_used,
            mode=mode,
            status=status,
            query=query,
            fetched_at=fetched_at,
            parser_version=parser_version,
            candidate_count=len(items),
            selected_external_id=None,
            warnings=[warning] if warning else [],
        )
