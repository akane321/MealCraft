from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from time import monotonic

from app.products.provider import (
    FairPriceProductProvider,
    FixtureProductProvider,
    ProductProviderError,
    normalize_search_text,
)
from app.repositories.product import ProductSnapshotRepository
from app.schemas.product import GroceryLineEstimate, PriceEvidence, ProductSearchResponse
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
FINAL_PRICE_SECONDS = 3.0
FINAL_PRICE_CONCURRENCY = 8
# Shared per server process, including overlapping requests and late provider calls.
_price_workers = ThreadPoolExecutor(max_workers=FINAL_PRICE_CONCURRENCY, thread_name_prefix="basket-price")


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

    def refresh_selected(self, lines: list[GroceryLineEstimate]) -> list[GroceryLineEstimate]:
        """Only observe the already chosen SKUs; worker threads never access the database.

        A socket timeout cannot cancel a running thread. Stop waiting at the shared deadline,
        cancel queued work, and never apply/cache a late response. The shared executor caps
        actual provider concurrency even if a preceding basket has lingering requests.
        """
        deadline = monotonic() + FINAL_PRICE_SECONDS
        refreshed = [line.model_copy(deep=True) for line in lines]
        queries: dict[str, list[int]] = {}
        for index, line in enumerate(refreshed):
            product = line.product
            if product is None or line.packages_required == 0:
                continue
            query = normalize_search_text(
                (line.evidence.query if line.evidence else None) or line.ingredient_display_name
            )
            evidence = line.evidence or PriceEvidence(
                fact_id=f"{product.external_id}@{product.fetched_at.isoformat()}",
                source=product.source,
                mode="fixture" if product.source == "fixture" else "snapshot",
                query=query,
                parser_version=None,
                fetched_at=product.fetched_at,
            )
            line.evidence = evidence.model_copy(
                update={
                    "price_source": "fixture" if evidence.mode == "fixture" else "snapshot",
                    "lookup_status": "timeout",
                    "checked_at": None,
                }
            )
            if product.external_id.startswith("fixture-"):
                line.evidence = line.evidence.model_copy(
                    update={
                        "price_source": "no_external_product",
                        "lookup_status": "no_external_id",
                    }
                )
                continue
            queries.setdefault(query, []).append(index)

        def apply(query, items, mode):
            by_id = {item.external_id: item for item in items}
            observed = {}
            for index in queries[query]:
                line = refreshed[index]
                matched = by_id.get(line.product.external_id)
                checked_at = datetime.now(UTC)
                if matched is None:
                    line.evidence = line.evidence.model_copy(
                        update={
                            "lookup_status": "selected_product_not_returned",
                            "checked_at": checked_at,
                        }
                    )
                    continue
                try:
                    price = Decimal(str(matched.price_sgd))
                    valid = price.is_finite() and price >= 0 and not price % Decimal("0.01")
                except InvalidOperation:
                    valid = False
                if not valid:
                    line.evidence = line.evidence.model_copy(
                        update={
                            "lookup_status": "invalid_price",
                            "checked_at": checked_at,
                        }
                    )
                    continue
                observed[matched.external_id] = matched
                # Keep reviewed packaging (including density-normalized mass) and identity.
                line.product = line.product.model_copy(
                    update={
                        key: getattr(matched, key)
                        for key in ("price_sgd", "regular_price_sgd", "in_stock", "source", "fetched_at")
                    }
                )
                line.evidence = PriceEvidence(
                    fact_id=f"{matched.external_id}@{matched.fetched_at.isoformat()}",
                    source="fairprice",
                    mode=mode,
                    price_source=mode,
                    query=query,
                    parser_version="fairprice-next-data-v1",
                    fetched_at=matched.fetched_at,
                    lookup_status="success" if matched.in_stock else "out_of_stock",
                    checked_at=checked_at,
                )
            if mode == "live" and observed:
                # Same transaction as the confirmed plan; never commit from a worker.
                self.repository.replace_query_results(
                    source="fairprice",
                    search_query=query,
                    products=list(observed.values()),
                    commit=False,
                )

        needed = []
        for query, indices in queries.items():
            cached = self.repository.get_fresh(
                source="fairprice",
                search_query=query,
                fetched_after=datetime.now(UTC) - timedelta(minutes=self.cache_ttl_minutes),
                limit=20,
            )
            ids = {item.external_id for item in cached}
            if all(refreshed[index].product.external_id in ids for index in indices):
                apply(query, cached, "cache")
            else:
                needed.append(query)

        def fetch(query):
            remaining = deadline - monotonic()
            if remaining <= 0:
                return deadline + 1, []
            items = self.live_provider.search(query, limit=20, timeout_seconds=remaining)
            return monotonic(), items

        queue = iter(needed)
        pending = {}
        while monotonic() < deadline:
            while len(pending) < FINAL_PRICE_CONCURRENCY:
                query = next(queue, None)
                if query is None:
                    break
                pending[_price_workers.submit(fetch, query)] = query
            if not pending:
                break
            done, _ = wait(pending, timeout=max(0, deadline - monotonic()), return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                query = pending.pop(future)
                try:
                    completed_at, items = future.result()
                except (ProductProviderError, ValueError, OverflowError) as error:
                    status = (
                        "schema_drift"
                        if isinstance(error, ProductProviderError) and error.kind == "schema_drift"
                        else "provider_error"
                        if isinstance(error, ProductProviderError)
                        else "invalid_price"
                    )
                    if isinstance(error.__cause__, TimeoutError):
                        status = "timeout"
                    for index in queries[query]:
                        refreshed[index].evidence = refreshed[index].evidence.model_copy(
                            update={
                                "lookup_status": status,
                                "checked_at": datetime.now(UTC),
                            }
                        )
                else:
                    if completed_at <= deadline:
                        apply(query, items, "live")
        for future in pending:
            future.cancel()
        for line in refreshed:
            if line.evidence and line.evidence.lookup_status == "timeout":
                line.evidence = line.evidence.model_copy(update={"checked_at": datetime.now(UTC)})
        return refreshed

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
